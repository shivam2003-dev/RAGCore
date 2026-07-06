from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class ExtractedDocument:
    text: str
    metadata: dict = field(default_factory=dict)  # page_count, headings, language hints…


class TextExtractor(Protocol):
    suffixes: tuple[str, ...]

    def extract(self, path: Path) -> ExtractedDocument: ...


# Extension → magic-byte prefixes accepted at upload. Empty tuple = text formats
# validated by decodability instead of signature.
MAGIC_BYTES: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF",),
    ".docx": (b"PK\x03\x04",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xFF\xD8\xFF",),
    ".jpeg": (b"\xFF\xD8\xFF",),
    ".gif": (b"GIF8",),
    ".bmp": (b"BM",),
    ".webp": (b"RIFF",),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".md": (),
    ".txt": (),
    ".csv": (),
    ".html": (),
}
