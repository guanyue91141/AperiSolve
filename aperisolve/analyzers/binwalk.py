"""Binwalk Analyzer for Image Submissions."""

from pathlib import Path

from .base_analyzer import SubprocessAnalyzer


class BinwalkAnalyzer(SubprocessAnalyzer):
    """Analyzer for binwalk."""

    name = "binwalk"
    has_archive = True
    display_order = 50

    def __init__(self, input_img: Path, output_dir: Path) -> None:
        """Initialize the binwalk analyzer."""
        super().__init__(input_img, output_dir)
        # Bounded extraction: untrusted input can be a decompression bomb, so
        # cap recursion depth, file count and per-file size. --run-as is
        # deliberately absent: binwalk fails to load its Extractor module when
        # that flag names a user other than the caller and the caller is not
        # root (binwalk/modules/extractor.py, `runas_uid != os.getuid()`).
        # Upstream sets --run-as=root because its container runs as root.
        self.cmd = [
            "binwalk",
            "--matryoshka",
            "--depth=2",
            "--count=100",
            "--size=10485760",
            "-e",
            self.img,
        ]
        self.make_folder = False  # Binwalk already create its own folder

    def get_extracted_dir(self) -> Path:
        """Return the binwalk extraction directory."""
        return self.output_dir / f"_{self.input_img.name}.extracted"

    def is_error(self, returncode: int, stdout: str, stderr: str, *, zip_exist: bool) -> bool:
        """Check whether binwalk execution failed."""
        _ = stdout, stderr
        # binwalk exits 0 but still warns on stderr about signatures it has no
        # helper for, so gating on stderr marks every clean scan as a failure
        # and drops the signature table from the results page.
        _ = stdout, stderr
        return returncode != 0 and not zip_exist
