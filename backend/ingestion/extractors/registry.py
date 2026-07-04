import csv
import io
from pathlib import Path

from core.exceptions import IngestionError
from ingestion.extractors.base import ExtractedDocument


class PdfExtractor:
    suffixes = (".pdf",)

    def extract(self, path: Path) -> ExtractedDocument:
        from pypdf import PdfReader

        reader = PdfReader(path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return ExtractedDocument(
            text="\n\n".join(pages).strip(), metadata={"page_count": len(pages)}
        )


class DocxExtractor:
    suffixes = (".docx",)

    def extract(self, path: Path) -> ExtractedDocument:
        import docx

        document = docx.Document(str(path))
        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
        return ExtractedDocument(
            text="\n\n".join(paragraphs), metadata={"paragraph_count": len(paragraphs)}
        )


class MarkdownExtractor:
    suffixes = (".md",)

    def extract(self, path: Path) -> ExtractedDocument:
        text = path.read_text(encoding="utf-8", errors="replace")
        headings = [
            line.lstrip("# ").strip()
            for line in text.splitlines()
            if line.startswith("#")
        ]
        return ExtractedDocument(text=text, metadata={"headings": headings[:50], "format": "markdown"})


class PlainTextExtractor:
    suffixes = (".txt",)

    def extract(self, path: Path) -> ExtractedDocument:
        return ExtractedDocument(text=path.read_text(encoding="utf-8", errors="replace"))


class CsvExtractor:
    suffixes = (".csv",)

    def extract(self, path: Path) -> ExtractedDocument:
        raw = path.read_text(encoding="utf-8", errors="replace")
        rows = list(csv.reader(io.StringIO(raw)))
        if not rows:
            return ExtractedDocument(text="", metadata={"row_count": 0})
        header, body = rows[0], rows[1:]
        # row-per-line "column: value" rendering keeps cell/column association
        # visible to both FTS and the LLM
        lines = [
            "; ".join(f"{h}: {v}" for h, v in zip(header, row, strict=False))
            for row in body
        ]
        return ExtractedDocument(
            text="\n".join(lines), metadata={"row_count": len(body), "columns": header}
        )


class HtmlExtractor:
    suffixes = (".html", ".htm")

    def extract(self, path: Path) -> ExtractedDocument:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        title = soup.title.string.strip() if soup.title and soup.title.string else None
        return ExtractedDocument(
            text=soup.get_text(separator="\n", strip=True), metadata={"html_title": title}
        )


_EXTRACTORS = [
    PdfExtractor(),
    DocxExtractor(),
    MarkdownExtractor(),
    PlainTextExtractor(),
    CsvExtractor(),
    HtmlExtractor(),
]

SUPPORTED_SUFFIXES: frozenset[str] = frozenset(
    s for e in _EXTRACTORS for s in e.suffixes
)


def extract_text(path: Path) -> ExtractedDocument:
    suffix = path.suffix.lower()
    for extractor in _EXTRACTORS:
        if suffix in extractor.suffixes:
            doc = extractor.extract(path)
            if not doc.text.strip():
                raise IngestionError(f"No extractable text in {path.name}")
            return doc
    raise IngestionError(f"Unsupported file type: {suffix}")
