"""Find and preview raster images hidden in Base64 text inside an upload."""

import base64
import binascii
import io
import re
import warnings
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from .base_analyzer import SubprocessAnalyzer


_BASE64_RUN = re.compile(
    rb"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/_-]{64,}={0,2}(?![A-Za-z0-9+/=_-])",
)
_IMAGE_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"BM",
    b"II*\x00",
    b"MM\x00*",
    b"RIFF",  # verified as WebP below
    b"\x00\x00\x01\x00",  # ICO
    b"\x00\x00\x02\x00",  # CUR
)
_MAX_CANDIDATES = 64
_MAX_DECODED_BYTES = 16 * 1024 * 1024
_MAX_IMAGE_PIXELS = 40_000_000
_MAX_PREVIEW_EDGE = 1800


class Base64ImagesAnalyzer(SubprocessAnalyzer):
    """Extract common raster image formats encoded inside an uploaded image."""

    name = "base64_images"
    display_order = 55
    accepts = frozenset({"image"})

    def analyze(self, password: str | None = None) -> None:
        """Run the bounded in-process scanner and persist its result."""
        _ = password
        self.update_result(self.get_results())

    def get_results(self, password: str | None = None) -> dict[str, Any]:
        """Decode Base64 candidates, validate embedded images and save previews."""
        _ = password
        source = self.input_img.read_bytes()
        records: list[dict[str, Any]] = []
        seen: set[tuple[int, int]] = set()

        for candidate_index, match in enumerate(_BASE64_RUN.finditer(source)):
            if candidate_index >= _MAX_CANDIDATES or len(records) >= 24:
                break
            encoded = match.group(0)
            if len(encoded) > (_MAX_DECODED_BYTES * 4 // 3 + 8):
                continue
            try:
                decoded = base64.b64decode(encoded, altchars=b"-_", validate=False)
            except (binascii.Error, ValueError):
                continue
            if not decoded or len(decoded) > _MAX_DECODED_BYTES:
                continue

            for image_offset in self._image_offsets(decoded):
                key = (match.start(), image_offset)
                if key in seen:
                    continue
                seen.add(key)
                record = self._save_image(decoded[image_offset:], match.start(), image_offset)
                if record:
                    records.append(record)

        images: dict[str, list[str]] = {}
        for record in records:
            label = f"{record['format']} · {record['width']}×{record['height']}"
            images.setdefault(label, []).append(record["preview"])

        return {
            "status": "ok",
            "output": {
                "images_found": len(records),
                "formats": ", ".join(sorted({record["format"] for record in records})) or "—",
            },
            "images": images,
            "image_details": records,
        }

    @staticmethod
    def _image_offsets(data: bytes) -> list[int]:
        offsets: set[int] = set()
        for signature in _IMAGE_SIGNATURES:
            start = 0
            while len(offsets) < 32:
                offset = data.find(signature, start)
                if offset < 0:
                    break
                if signature != b"RIFF" or data[offset + 8 : offset + 12] == b"WEBP":
                    offsets.add(offset)
                start = offset + 1
        return sorted(offsets)

    def _save_image(
        self,
        data: bytes,
        base64_offset: int,
        image_offset: int,
    ) -> dict[str, Any] | None:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(io.BytesIO(data))
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > _MAX_IMAGE_PIXELS:
                    return None
                image.load()
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            return None

        image_format = (image.format or "").upper()
        extensions = {
            "JPEG": ".jpg",
            "PNG": ".png",
            "GIF": ".gif",
            "BMP": ".bmp",
            "TIFF": ".tiff",
            "WEBP": ".webp",
            "ICO": ".ico",
            "JP2": ".jp2",
            "JPEG2000": ".jp2",
        }
        extension = extensions.get(image_format)
        if extension is None:
            return None

        base_name = f"base64_image_{base64_offset:08x}_{image_offset:04x}"
        output_path = self.output_dir / f"{base_name}{extension}"
        preview_path = self.output_dir / f"{base_name}_preview.png"
        try:
            preview = image.convert("RGBA")
            preview.thumbnail((_MAX_PREVIEW_EDGE, _MAX_PREVIEW_EDGE))
            preview.save(preview_path, format="PNG", optimize=True)
            # Preserve the exact embedded bytes for forensic download. Saving
            # through Pillow can strip metadata or alter steganographic data.
            output_path.write_bytes(data)
        except (OSError, ValueError):
            return None

        return {
            "format": image_format,
            "width": width,
            "height": height,
            "base64_offset": base64_offset,
            "decoded_image_offset": image_offset,
            "preview": f"/image/{self.output_dir.name}/{preview_path.name}",
            "download": f"/image/{self.output_dir.name}/{output_path.name}",
            "bytes": output_path.stat().st_size,
        }
