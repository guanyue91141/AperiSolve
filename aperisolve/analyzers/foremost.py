"""Foremost Analyzer for Image Submissions."""

from pathlib import Path
from typing import Any

from .base_analyzer import SubprocessAnalyzer

FOREMOST_ERROR_THRESHOLD = 60


class ForemostAnalyzer(SubprocessAnalyzer):
    """Analyzer for foremost."""

    name = "foremost"
    has_archive = True
    display_order = 60

    def __init__(self, input_img: Path, output_dir: Path) -> None:
        """Initialize the foremost analyzer and its extracted-file listing."""
        super().__init__(input_img, output_dir)
        self.cmd = ["foremost", "-o", str(self.get_extracted_dir()), "-i", self.img]
        self.archive_contents: list[str] = []

    def is_error(self, returncode: int, stdout: str, stderr: str, *, zip_exist: bool) -> bool:
        """Check if the result is an error."""
        _ = stdout, returncode, zip_exist
        return len(stderr) > FOREMOST_ERROR_THRESHOLD

    def generate_archive(self, extracted_dir: Path | None = None) -> str:
        """Record carved paths before the base class archives and removes them."""
        if extracted_dir is None:
            extracted_dir = self.get_extracted_dir()
        self.archive_contents = sorted(
            path.relative_to(extracted_dir).as_posix()
            for path in extracted_dir.rglob("*")
            if path.is_file()
        )
        return super().generate_archive(extracted_dir)

    def get_results(self, password: str | None = None) -> dict[str, Any]:
        """Add the archive file list to the persisted analyzer result."""
        self.archive_contents = []
        result = super().get_results(password)
        if self.archive_contents and result.get("status") == "ok":
            result["files"] = self.archive_contents
        return result

    def process_output(self, stdout: str, stderr: str) -> str | list[str] | dict[str, str]:
        """Process the stdout/stderr."""
        _ = stdout
        if "Processing" in stderr and "|*|" in stderr:
            return stderr.strip().replace("\n", "")
        return []
