"""Internationalization helpers: locale selection, JS catalog, hreflang."""

from flask import Blueprint, g, request
from flask_babel import gettext as _

DEFAULT_LANG = "en"
# Languages served under a URL prefix (/fr/, /es/, ...). English is at the root.
PREFIX_LANGS = ["fr", "es", "de", "ru", "zh", "pt"]
SUPPORTED_LANGS = [DEFAULT_LANG, *PREFIX_LANGS]
LANG_PREFIX_RULE = f"/<any({','.join(PREFIX_LANGS)}):lang_code>"

# Open Graph locale identifiers (og:locale / og:locale:alternate).
OG_LOCALES = {
    "en": "en_US",
    "fr": "fr_FR",
    "es": "es_ES",
    "de": "de_DE",
    "ru": "ru_RU",
    "zh": "zh_CN",
    "pt": "pt_BR",
}


def select_locale() -> str:
    """Locale precedence: URL prefix, then cookie, then Accept-Language."""
    lang = g.get("lang_code")
    if lang in SUPPORTED_LANGS:
        return lang
    cookie = request.cookies.get("lang")
    if cookie in SUPPORTED_LANGS:
        return cookie
    return request.accept_languages.best_match(SUPPORTED_LANGS) or DEFAULT_LANG


def register_lang_handling(blueprint: Blueprint) -> None:
    """Make a blueprint language-aware for its prefixed registration.

    The ``lang_code`` URL value is popped into ``g`` before views run, and
    re-injected by ``url_for`` so in-language navigation stays in-language.
    """

    @blueprint.url_value_preprocessor
    def pull_lang_code(_endpoint: str | None, values: dict | None) -> None:
        g.lang_code = values.pop("lang_code", None) if values else None

    @blueprint.url_defaults
    def add_lang_code(_endpoint: str, values: dict) -> None:
        if "lang_code" not in values and g.get("lang_code"):
            values["lang_code"] = g.lang_code


def lang_prefix() -> str:
    """URL prefix of the active language ("" for English)."""
    lang = g.get("lang_code")
    return f"/{lang}" if lang else ""


def alternates_for(bare_path: str, langs: list[str] | None = None) -> list[tuple[str, str]]:
    """Build hreflang (code, href) pairs for an unprefixed path."""
    pairs = [
        (lang, bare_path if lang == DEFAULT_LANG else f"/{lang}{bare_path}")
        for lang in (langs or SUPPORTED_LANGS)
    ]
    pairs.append(("x-default", bare_path))
    return pairs


def js_catalog() -> dict[str, str]:
    """Strings rendered client-side by aperisolve.js, keyed by English text."""
    return {
        "No results": _("No results"),
        "First upload:": _("First upload:"),
        "Last upload:": _("Last upload:"),
        "Name(s):": _("Name(s):"),
        "Size:": _("Size:"),
        "Upload count:": _("Upload count:"),
        "Common password(s):": _("Common password(s):"),
        "Remove password": _("Remove password"),
        "Remove Image": _("Remove Image"),
        "Available in {s} seconds": _("Available in {s} seconds"),
        "Image successfully removed": _("Image successfully removed"),
        "Network error occurred": _("Network error occurred"),
        "Error:": _("Error:"),
        "Download file": _("Download file"),
        "Superimposed": _("Superimposed"),
        "Red": _("Red"),
        "Green": _("Green"),
        "Blue": _("Blue"),
        "Alpha": _("Alpha"),
        "Spectrogram": _("Spectrogram"),
        "Waveform": _("Waveform"),
        "❌ Error during the analysis.": _("❌ Error during the analysis."),
        "Please select a file.": _("Please select a file."),
        "❌ Invalid server response: missing submission_hash.": _(
            "❌ Invalid server response: missing submission_hash.",
        ),
        "❌ Invalid server response.": _("❌ Invalid server response."),
        "❌ File too large. Please upload a smaller file.": _(
            "❌ File too large. Please upload a smaller file.",
        ),
        "Upload complete": _("Upload complete"),
        "❌ An error occurred during the transfer": _("❌ An error occurred during the transfer"),
        "Analyzing your file…": _("Analyzing your file…"),
        "Success": _("Success"),
        "No result": _("No result"),
        "Learn more": _("Learn more"),
        "Color remapping": _("Color remapping"),
        "ExifTool metadata": _("ExifTool metadata"),
        "Binwalk (embedded file and signature scanning)": _(
            "Binwalk (embedded file and signature scanning)",
        ),
        "Base64 image detection (embedded images)": _(
            "Base64 image detection (embedded images)",
        ),
        "Images found": _("Images found"),
        "Detected formats": _("Detected formats"),
        "Base64 offset": _("Base64 offset"),
        "Decoded image offset": _("Decoded image offset"),
        "Download extracted image": _("Download extracted image"),
        "Decomposer (image bit-plane analysis)": _(
            "Decomposer (image bit-plane analysis)",
        ),
        "File (file type identification)": _("File (file type identification)"),
        "Foremost (file carving and recovery analysis)": _(
            "Foremost (file carving and recovery analysis)",
        ),
        "Identify (image format and properties)": _(
            "Identify (image format and properties)",
        ),
        "JPSeek (JPHide steganography extraction)": _(
            "JPSeek (JPHide steganography extraction)",
        ),
        "JSteg (JPEG coefficient steganography analysis)": _(
            "JSteg (JPEG coefficient steganography analysis)",
        ),
        "OpenStego (image steganography extraction)": _(
            "OpenStego (image steganography extraction)",
        ),
        "OutGuess (JPEG steganography analysis)": _(
            "OutGuess (JPEG steganography analysis)",
        ),
        "PDFiD (PDF suspicious keyword scan)": _(
            "PDFiD (PDF suspicious keyword scan)",
        ),
        "PDFInfo (PDF metadata inspection)": _(
            "PDFInfo (PDF metadata inspection)",
        ),
        "PCRT (PNG repair and trailing data recovery)": _(
            "PCRT (PNG repair and trailing data recovery)",
        ),
        "Pngcheck (PNG chunk and CRC validation)": _(
            "Pngcheck (PNG chunk and CRC validation)",
        ),
        "Spectrogram (audio frequency visualization)": _(
            "Spectrogram (audio frequency visualization)",
        ),
        "Steghide (file steganography extraction)": _(
            "Steghide (file steganography extraction)",
        ),
        "Strings (hexadecimal and text search)": _(
            "Strings (hexadecimal and text search)",
        ),
        "zsteg (PNG/BMP bit-plane steganography analysis)": _(
            "zsteg (PNG/BMP bit-plane steganography analysis)",
        ),
        "Keyword matches": _("Keyword matches"),
        "Original file": _("Original file"),
        "No matches found in the uploaded file or analysis results.": _(
            "No matches found in the uploaded file or analysis results.",
        ),
        "File anomaly inspection (magic number and terminator analysis)": _(
            "File anomaly inspection (magic number and terminator analysis)",
        ),
        "ExifTool Version Number": _("ExifTool Version Number"),
        "File Name": _("File Name"),
        "Directory": _("Directory"),
        "File Size": _("File Size"),
        "File Modification Date/Time": _("File Modification Date/Time"),
        "File Access Date/Time": _("File Access Date/Time"),
        "File Inode Change Date/Time": _("File Inode Change Date/Time"),
        "File Permissions": _("File Permissions"),
        "File Type": _("File Type"),
        "File Type Extension": _("File Type Extension"),
        "MIME Type": _("MIME Type"),
        "BMP Version": _("BMP Version"),
        "Bit Depth": _("Bit Depth"),
        "Compression": _("Compression"),
        "Filter": _("Filter"),
        "Interlace": _("Interlace"),
        "Color Type": _("Color Type"),
        "Planes": _("Planes"),
        "X Resolution": _("X Resolution"),
        "Y Resolution": _("Y Resolution"),
        "Colors Used": _("Colors Used"),
        "Important Colors": _("Important Colors"),
        "Image Width": _("Image Width"),
        "Image Height": _("Image Height"),
        "Image Size": _("Image Size"),
        "Megapixels": _("Megapixels"),
        "Exif Byte Order": _("Exif Byte Order"),
        "Current IPTC Digest": _("Current IPTC Digest"),
        "Encoding Process": _("Encoding Process"),
        "Bits Per Sample": _("Bits Per Sample"),
        "Color Components": _("Color Components"),
        "Y Cb Cr Sub Sampling": _("Y Cb Cr Sub Sampling"),
        "Photometric Interpretation": _("Photometric Interpretation"),
        "Orientation": _("Orientation"),
        "Samples Per Pixel": _("Samples Per Pixel"),
        "Resolution Unit": _("Resolution Unit"),
        "Software": _("Software"),
        "Modify Date": _("Modify Date"),
        "Create Date": _("Create Date"),
        "Metadata Date": _("Metadata Date"),
        "Exif Version": _("Exif Version"),
        "Color Space": _("Color Space"),
        "Exif Image Width": _("Exif Image Width"),
        "Exif Image Height": _("Exif Image Height"),
        "Thumbnail Offset": _("Thumbnail Offset"),
        "Thumbnail Length": _("Thumbnail Length"),
        "Coded Character Set": _("Coded Character Set"),
        "Application Record Version": _("Application Record Version"),
        "IPTC Digest": _("IPTC Digest"),
        "Print Style": _("Print Style"),
        "Displayed Units X": _("Displayed Units X"),
        "Displayed Units Y": _("Displayed Units Y"),
        "Print Position": _("Print Position"),
        "Print Scale": _("Print Scale"),
        "Background Color": _("Background Color"),
        "Global Angle": _("Global Angle"),
        "Global Altitude": _("Global Altitude"),
        "Print Flags": _("Print Flags"),
        "Print Flags Info": _("Print Flags Info"),
        "Color Halftoning Info": _("Color Halftoning Info"),
        "Color Transfer Funcs": _("Color Transfer Funcs"),
        "Grid Guides Info": _("Grid Guides Info"),
        "URL List": _("URL List"),
        "Slices Group Name": _("Slices Group Name"),
        "Num Slices": _("Num Slices"),
        "Pixel Aspect Ratio": _("Pixel Aspect Ratio"),
        "ICC Untagged": _("ICC Untagged"),
        "IDs Base Value": _("IDs Base Value"),
        "Has Real Merged Data": _("Has Real Merged Data"),
        "Writer Name": _("Writer Name"),
        "Reader Name": _("Reader Name"),
        "Photoshop Quality": _("Photoshop Quality"),
        "Photoshop Format": _("Photoshop Format"),
        "XMP Toolkit": _("XMP Toolkit"),
        "Document ID": _("Document ID"),
        "Instance ID": _("Instance ID"),
        "Original Document ID": _("Original Document ID"),
        "History Action": _("History Action"),
        "History Instance ID": _("History Instance ID"),
        "History When": _("History When"),
        "History Software Agent": _("History Software Agent"),
        "History Changed": _("History Changed"),
        "History Parameters": _("History Parameters"),
        "Derived From Instance ID": _("Derived From Instance ID"),
        "Derived From Document ID": _("Derived From Document ID"),
        "Derived From Original Document ID": _("Derived From Original Document ID"),
        "Format": _("Format"),
        "Legacy IPTC Digest": _("Legacy IPTC Digest"),
        "Color Mode": _("Color Mode"),
        "Document Ancestors": _("Document Ancestors"),
        "Creator Tool": _("Creator Tool"),
        "DCT Encode Version": _("DCT Encode Version"),
        "APP14 Flags 0": _("APP14 Flags 0"),
        "APP14 Flags 1": _("APP14 Flags 1"),
        "Color Transform": _("Color Transform"),
        "❌ HTTP error": _("❌ HTTP error"),
        "❌ The analysis is taking too long. Please reload the page to check again.": _(
            "❌ The analysis is taking too long. Please reload the page to check again.",
        ),
        "Analyzed file": _("Analyzed file"),
        "WinHex-style byte and string view": _("WinHex-style byte and string view"),
        "Hex view": _("Hex view"),
        "Extracted strings": _("Extracted strings"),
        "Offset": _("Offset"),
        "Hex bytes": _("Hex bytes"),
        "ASCII": _("ASCII"),
        "Search hex bytes, ASCII, or offset": _("Search hex bytes, ASCII, or offset"),
        "Search extracted strings or offset": _("Search extracted strings or offset"),
        "Previous match": _("Previous match"),
        "Next match": _("Next match"),
        "No matches found.": _("No matches found."),
        "No bytes to display": _("No bytes to display"),
        "Showing the first 4096 bytes": _("Showing the first 4096 bytes"),
        "Unable to load the complete hex view.": _(
            "Unable to load the complete hex view.",
        ),
        "Showing bytes around offset": _("Showing bytes around offset"),
        "Window at offset": _("Window at offset"),
        "String output was truncated": _("String output was truncated"),
        "Select a string to locate its bytes in the hex view.": _(
            "Select a string to locate its bytes in the hex view.",
        ),
        "String starts beyond the visible hex preview.": _(
            "String starts beyond the visible hex preview.",
        ),
        "No printable strings found.": _("No printable strings found."),
        "File size": _("File size"),
        "Signature matches": _("Signature matches"),
        "Match": _("Match"),
        "Signature": _("Signature"),
        "Location": _("Location"),
        "Header": _("Header"),
        "Embedded": _("Embedded"),
        "No common file signatures were detected.": _(
            "No common file signatures were detected.",
        ),
        "End marker": _("End marker"),
        "Found": _("Found"),
        "Missing": _("Missing"),
        "Not applicable": _("Not applicable"),
        "Anomalies": _("Anomalies"),
        "Start": _("Start"),
        "End": _("End"),
        "No structural anomalies detected.": _("No structural anomalies detected."),
        "Data after FFD9 (EOI) end marker": _("Data after FFD9 (EOI) end marker"),
        "Bytes follow the format's logical end marker and may contain appended data.": _(
            "Bytes follow the format's logical end marker and may contain appended data.",
        ),
        "Byte ranges use a zero-based start and an exclusive end.": _(
            "Byte ranges use a zero-based start and an exclusive end.",
        ),
    }
