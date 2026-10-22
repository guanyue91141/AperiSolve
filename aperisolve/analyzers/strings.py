"""Strings Analyzer for Image Submissions."""

import re
from pathlib import Path
from typing import Any

from .base_analyzer import SubprocessAnalyzer


class StringsAnalyzer(SubprocessAnalyzer):
    """Analyzer for strings."""

    name = "strings"
    display_order = 160

    def __init__(self, input_img: Path, output_dir: Path) -> None:
        """Initialize the strings analyzer."""
        super().__init__(input_img, output_dir)
        # GNU strings' hexadecimal offsets let the browser connect each result
        # to its byte position in the simultaneous hex/ASCII view.
        self.cmd = ["strings", "-t", "x", self.img]

    def process_output(self, stdout: str, stderr: str) -> dict[str, Any]:
        """Return extracted strings and a compact WinHex-style byte preview."""
        _ = stderr
        strings: list[dict[str, str]] = []
        for line in stdout.splitlines():
            match = re.match(r"^\s*([0-9a-fA-F]+)\s+(.*)$", line)
            if match:
                strings.append({"offset": match.group(1).upper(), "text": match.group(2)})
            elif line and line != "[output truncated]":
                strings.append({"offset": "", "text": line})

        with self.input_img.open("rb") as file_obj:
            data = file_obj.read(4096)
        rows = []
        for start in range(0, len(data), 16):
            row = data[start : start + 16]
            rows.append(
                {
                    "offset": start,
                    "offset_hex": f"{start:08X}",
                    "hex": " ".join(f"{value:02X}" for value in row),
                    "ascii": "".join(chr(value) if 32 <= value <= 126 else "." for value in row),
                },
            )

        size = self.input_img.stat().st_size
        return {
            "file_size": size,
            "preview_bytes": len(data),
            "preview_truncated": size > len(data),
            "strings_truncated": "[output truncated]" in stdout,
            "hex_rows": rows,
            "strings": strings,
        }
