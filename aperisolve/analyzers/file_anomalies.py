"""Inspect file signatures, format terminators, and structural anomalies."""

from __future__ import annotations

import zlib
from pathlib import Path
from typing import Any

from .base_analyzer import SubprocessAnalyzer


# Common signatures used by file(1), carving tools, and forensic hex editors.
# The offset is the expected location in a file header; other occurrences are
# also reported as possible embedded-file signatures.
_MAGIC: tuple[tuple[str, bytes, int], ...] = (
    ("PNG 图像", b"\x89PNG\r\n\x1a\n", 0),
    ("JPEG 图像", b"\xff\xd8\xff", 0),
    ("GIF 图像", b"GIF87a", 0),
    ("GIF 图像", b"GIF89a", 0),
    ("PDF 文档", b"%PDF-", 0),
    ("ZIP 压缩包", b"PK\x03\x04", 0),
    ("空 ZIP 压缩包", b"PK\x05\x06", 0),
    ("7-Zip 压缩包", b"7z\xbc\xaf\x27\x1c", 0),
    ("RAR 压缩包", b"Rar!\x1a\x07", 0),
    ("GZIP 压缩包", b"\x1f\x8b\x08", 0),
    ("BMP 图像", b"BM", 0),
    ("TIFF 图像（小端序）", b"II*\x00", 0),
    ("TIFF 图像（大端序）", b"MM\x00*", 0),
    ("WebP 图像", b"WEBP", 8),
    ("WAVE 音频", b"WAVE", 8),
    ("AVI 视频", b"AVI ", 8),
    ("RIFF 容器", b"RIFF", 0),
    ("MP4 / ISO 基础媒体文件", b"ftyp", 4),
    ("ELF 可执行文件", b"\x7fELF", 0),
    ("Windows 可执行文件", b"MZ", 0),
    ("SQLite 数据库", b"SQLite format 3\x00", 0),
    ("Ogg 媒体文件", b"OggS", 0),
    ("FLAC 音频", b"fLaC", 0),
    ("ID3 音频标签", b"ID3", 0),
)


def _hex_offset(offset: int) -> str:
    """Format a byte offset consistently with the browser's hex pane."""
    return f"0x{offset:08X}"


def _record_anomaly(
    anomalies: list[dict[str, Any]],
    *,
    title: str,
    detail: str,
    start: int,
    end: int,
    severity: str = "warning",
) -> None:
    """Add a half-open byte range to the report."""
    anomalies.append(
        {
            "title": title,
            "detail": detail,
            "start_offset": start,
            "end_offset": end,
            "start_hex": _hex_offset(start),
            "end_hex": _hex_offset(end),
            "severity": severity,
        },
    )


def _signature_matches(data: bytes) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for name, signature, expected_offset in _MAGIC:
        header_match = data[expected_offset : expected_offset + len(signature)] == signature
        if expected_offset == 8 and (len(data) < 12 or data[:4] != b"RIFF"):
            header_match = False
        if header_match:
            actual_signature = (
                data[:12]
                if expected_offset == 8
                else signature
            )
            matches.append(
                {
                    "name": name,
                    "offset": 0 if expected_offset == 8 else expected_offset,
                    "offset_hex": _hex_offset(0 if expected_offset == 8 else expected_offset),
                    "signature": actual_signature.hex(" ").upper(),
                    "location": "header",
                },
            )
            seen.add((name, expected_offset))

        # A common signature elsewhere can indicate an embedded file or a
        # polyglot. Keep one occurrence per signature to bound the report.
        position = data.find(signature, max(expected_offset + 1, 1))
        if position >= 0 and (name, position) not in seen:
            matches.append(
                {
                    "name": name,
                    "offset": position,
                    "offset_hex": _hex_offset(position),
                    "signature": signature.hex(" ").upper(),
                    "location": "embedded",
                },
            )
            seen.add((name, position))

    return sorted(matches, key=lambda match: (match["offset"], match["name"]))


def _png_terminator(data: bytes, anomalies: list[dict[str, Any]]) -> dict[str, Any]:
    position = 8
    while position + 12 <= len(data):
        length = int.from_bytes(data[position : position + 4], "big")
        chunk_type = data[position + 4 : position + 8]
        chunk_end = position + 12 + length
        if chunk_end > len(data):
            _record_anomaly(
                anomalies,
                title="PNG 数据块被截断",
                detail=(
                    f"{chunk_type.decode('ascii', errors='replace')} 数据块声明长度为 {length} 字节，"
                    "但文件在数据或 CRC 完整前已结束。"
                ),
                start=position,
                end=len(data),
            )
            return {
                "name": "IEND（PNG 结束块）",
                "status": "missing",
                "offset": None,
                "end_offset": None,
            }

        expected_crc = int.from_bytes(data[position + 8 + length : chunk_end], "big")
        actual_crc = zlib.crc32(data[position + 4 : position + 8 + length]) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            _record_anomaly(
                anomalies,
                title="PNG 数据块 CRC 校验不匹配",
                detail=(
                    f"{chunk_type.decode('ascii', errors='replace')} 数据块的 CRC 校验值与内容不符。"
                ),
                start=position + 8 + length,
                end=chunk_end,
            )

        if chunk_type == b"IEND":
            if length != 0:
                _record_anomaly(
                    anomalies,
                    title="PNG IEND 数据块无效",
                    detail="IEND 数据块的数据长度必须为 0。",
                    start=position,
                    end=chunk_end,
                )
            if chunk_end < len(data):
                _record_anomaly(
                    anomalies,
                    title="PNG 结束标记后存在数据",
                    detail="IEND 数据块后仍有字节，可能包含附加内容。",
                    start=chunk_end,
                    end=len(data),
                )
            return {
                "name": "IEND（PNG 结束块）",
                "status": "found",
                "offset": position + 4,
                "offset_hex": _hex_offset(position + 4),
                "end_offset": chunk_end,
                "end_hex": _hex_offset(chunk_end),
            }
        position = chunk_end

    _record_anomaly(
        anomalies,
        title="PNG 结束标记缺失",
        detail="到达文件末尾前未找到完整的 IEND 数据块。",
        start=len(data),
        end=len(data),
    )
    return {
        "name": "IEND（PNG 结束块）",
        "status": "missing",
        "offset": None,
        "end_offset": None,
    }


def _gif_terminator(data: bytes, anomalies: list[dict[str, Any]]) -> dict[str, Any]:
    """Walk GIF blocks so a 0x3B inside compressed image data is not mistaken for EOF."""
    marker_name = "3B（GIF 文件结束标记）"
    position = 13  # Header plus logical screen descriptor.
    if len(data) < position:
        position = len(data)
    else:
        screen_flags = data[10]
        if screen_flags & 0x80:
            position += 3 * (2 ** ((screen_flags & 0x07) + 1))

    while position < len(data):
        block_start = position
        introducer = data[position]
        if introducer == 0x3B:
            marker_end = position + 1
            if marker_end < len(data):
                _record_anomaly(
                    anomalies,
                    title="GIF 结束标记后存在数据",
                    detail="GIF 文件结束标记后仍有字节，可能包含附加内容。",
                    start=marker_end,
                    end=len(data),
                )
            return {
                "name": marker_name,
                "status": "found",
                "offset": position,
                "offset_hex": _hex_offset(position),
                "end_offset": marker_end,
                "end_hex": _hex_offset(marker_end),
            }

        if introducer == 0x21:  # Extension: label followed by data sub-blocks.
            position += 2
            block_size = 0
        elif introducer == 0x2C:  # Image descriptor and compressed sub-blocks.
            if position + 10 > len(data):
                position = len(data)
                break
            image_flags = data[position + 9]
            position += 10
            if image_flags & 0x80:
                position += 3 * (2 ** ((image_flags & 0x07) + 1))
            if position >= len(data):
                break
            position += 1  # LZW minimum code size.
            block_size = 0
        else:
            _record_anomaly(
                anomalies,
                title="GIF 数据块标记异常",
                detail=f"GIF 结束标记之前出现了未预期的块标记 0x{introducer:02X}。",
                start=block_start,
                end=block_start + 1,
            )
            break

        while position < len(data):
            block_size = data[position]
            position += 1
            if block_size == 0:
                break
            if position + block_size > len(data):
                _record_anomaly(
                    anomalies,
                    title="GIF 数据子块被截断",
                    detail="GIF 子块声明的字节数超过文件剩余长度。",
                    start=position - 1,
                    end=len(data),
                )
                position = len(data)
                break
            position += block_size

    _record_anomaly(
        anomalies,
        title="GIF 结束标记缺失",
        detail="图像和扩展数据之后未找到有效的 GIF 文件结束标记。",
        start=len(data),
        end=len(data),
    )
    return {"name": marker_name, "status": "missing", "offset": None, "end_offset": None}


def _terminator(data: bytes, file_type: str, anomalies: list[dict[str, Any]]) -> dict[str, Any]:
    """Find the format's logical end marker and report any trailing bytes."""
    marker_name: str
    marker_start: int
    marker_end: int
    if file_type == "PNG 图像":
        return _png_terminator(data, anomalies)
    if file_type == "JPEG 图像":
        marker_name = "FFD9（EOI，JPEG 结束标记）"
        marker_start = data.find(b"\xff\xd9")
        marker_end = marker_start + 2 if marker_start >= 0 else -1
    elif file_type == "GIF 图像":
        return _gif_terminator(data, anomalies)
    elif file_type == "PDF 文档":
        marker_name = "%%EOF（PDF 结束标记）"
        marker_start = data.rfind(b"%%EOF")
        marker_end = marker_start + 5 if marker_start >= 0 else -1
    elif "ZIP" in file_type and "压缩包" in file_type:
        marker_name = "PK 05 06（ZIP 中央目录结束记录）"
        marker_start = data.rfind(b"PK\x05\x06")
        if marker_start >= 0 and marker_start + 22 <= len(data):
            comment_length = int.from_bytes(data[marker_start + 20 : marker_start + 22], "little")
            marker_end = marker_start + 22 + comment_length
            if marker_end > len(data):
                _record_anomaly(
                    anomalies,
                    title="ZIP 结束记录被截断",
                    detail="中央目录结束记录中的注释长度超出文件末尾。",
                    start=marker_start,
                    end=len(data),
                )
                marker_end = -1
        else:
            marker_end = -1
    elif data.startswith(b"RIFF") and len(data) >= 8:
        marker_name = "RIFF 声明长度字段"
        declared_end = int.from_bytes(data[4:8], "little") + 8
        if declared_end > len(data):
            _record_anomaly(
                anomalies,
                title="RIFF 容器被截断",
                detail=(
                    f"RIFF 文件头声明的结束位置为 {_hex_offset(declared_end)}，"
                    f"超过实际文件末尾 {_hex_offset(len(data))}。"
                ),
                start=len(data),
                end=len(data),
            )
        elif declared_end < len(data):
            _record_anomaly(
                anomalies,
                title="RIFF 容器结束后存在数据",
                detail=(
                    "RIFF 长度字段指向的位置早于实际文件末尾，尾部可能附加了其他数据。"
                ),
                start=declared_end,
                end=len(data),
            )
        return {
            "name": marker_name,
            "status": "found",
            "offset": 4,
            "offset_hex": _hex_offset(4),
            "end_offset": declared_end,
            "end_hex": _hex_offset(declared_end),
        }
    else:
        return {"name": "不适用", "status": "not_applicable", "offset": None, "end_offset": None}

    if marker_start < 0 or marker_end < 0:
        _record_anomaly(
            anomalies,
            title=f"未找到 {marker_name}",
            detail="文件中未找到预期的结束标记。",
            start=len(data),
            end=len(data),
        )
        return {"name": marker_name, "status": "missing", "offset": None, "end_offset": None}

    # PDF readers allow trailing whitespace after %%EOF; report only non-space
    # content as appended data. Other formats treat all bytes after the marker
    # (or end record) as trailing content.
    trailing_start = marker_end
    if file_type == "PDF 文档":
        while trailing_start < len(data) and data[trailing_start] in b"\t\n\r\x0c\x20":
            trailing_start += 1
    if trailing_start < len(data):
        _record_anomaly(
            anomalies,
            title=f"{marker_name} 后存在附加数据",
            detail="格式结束标记之后仍有字节，可能包含附加内容。",
            start=trailing_start,
            end=len(data),
        )
    return {
        "name": marker_name,
        "status": "found",
        "offset": marker_start,
        "offset_hex": _hex_offset(marker_start),
        "end_offset": marker_end,
        "end_hex": _hex_offset(marker_end),
    }


def inspect_file(data: bytes) -> dict[str, Any]:
    """Return bounded signature, terminator, and anomaly information."""
    matches = _signature_matches(data)
    primary = next((match for match in matches if match["location"] == "header"), None)
    if (
        data.startswith(b"RIFF")
        and primary
        and primary["name"] == "RIFF 容器"
        and len(data) >= 12
    ):
        riff_type = data[8:12]
        primary = {
            **primary,
            "name": {
                b"WAVE": "WAVE 音频",
                b"WEBP": "WebP 图像",
                b"AVI ": "AVI 视频",
            }.get(riff_type, "RIFF 容器"),
        }
    if primary is None and matches:
        primary = matches[0]

    anomalies: list[dict[str, Any]] = []
    if primary is None:
        summary = "文件头未匹配到常见文件魔数。"
        terminator = {
            "name": "不适用",
            "status": "not_applicable",
            "offset": None,
            "end_offset": None,
        }
    else:
        file_type = primary["name"]
        summary = f"文件头匹配：{file_type}，偏移 {primary['offset_hex']}。"
        if primary["location"] == "embedded" and primary["offset"] > 0:
            _record_anomaly(
                anomalies,
                title="嵌入特征之前存在未识别数据",
                detail=(
                    f"偏移 0 未匹配到列表中的魔数；在 {primary['offset_hex']} 发现了 {file_type} "
                    "特征，可能存在封装数据、嵌入文件或多格式文件。"
                ),
                start=0,
                end=primary["offset"],
                severity="info",
            )
        terminator = _terminator(data, file_type, anomalies)

    return {
        "size": len(data),
        "summary": summary,
        "signatures": matches[:64],
        "terminator": terminator,
        "anomalies": anomalies,
    }


class FileAnomaliesAnalyzer(SubprocessAnalyzer):
    """Inspect byte-level file structure without relying on a shell utility."""

    name = "file_anomalies"
    display_order = 35

    def analyze(self, password: str | None = None) -> None:
        """Read the uploaded bytes and persist the structural inspection."""
        _ = password
        try:
            result = inspect_file(self.input_img.read_bytes())
            self.update_result({"status": "ok", "output": result})
        except OSError as exc:
            self.update_result({"status": "error", "error": str(exc)})
