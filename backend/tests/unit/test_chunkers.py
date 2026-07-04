from ingestion.chunkers.base import count_tokens
from ingestion.chunkers.code import CodeChunker
from ingestion.chunkers.markdown import MarkdownChunker
from ingestion.chunkers.recursive import RecursiveChunker
from ingestion.chunkers.sliding import SlidingWindowChunker


def test_recursive_respects_chunk_size():
    text = "One sentence here. " * 400
    chunks = RecursiveChunker().chunk(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    assert all(c.token_count <= 130 for c in chunks)  # small tolerance for merge boundaries
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_recursive_short_text_single_chunk():
    chunks = RecursiveChunker().chunk("Short text.", chunk_size=100, overlap=10)
    assert len(chunks) == 1
    assert chunks[0].content == "Short text."


def test_markdown_keeps_heading_metadata():
    md = "# Guide\n\nIntro paragraph.\n\n## Setup\n\nInstall the tool.\n\n## Usage\n\nRun it."
    chunks = MarkdownChunker().chunk(md, chunk_size=200, overlap=20)
    assert len(chunks) >= 3
    setup = next(c for c in chunks if "Install" in c.content)
    assert "Setup" in setup.metadata["headings"]


def test_markdown_without_headings_falls_back():
    chunks = MarkdownChunker().chunk("plain text " * 50, chunk_size=50, overlap=5)
    assert len(chunks) >= 1


def test_code_chunker_splits_on_definitions():
    code = "\n\n".join(f"def func_{i}():\n    return {i}" for i in range(40))
    chunks = CodeChunker().chunk(code, chunk_size=80, overlap=10)
    assert len(chunks) > 1
    assert all(c.metadata.get("kind") == "code" for c in chunks)
    # definitions stay whole: each chunk starts at a def boundary
    assert all(c.content.lstrip().startswith("def ") for c in chunks)


def test_sliding_window_parent_child():
    text = "word " * 2000
    chunks = SlidingWindowChunker().chunk(text, chunk_size=100, overlap=20)
    parents = [c for c in chunks if c.metadata.get("role") == "parent"]
    children = [c for c in chunks if c.metadata.get("role") == "child"]
    assert parents and children
    parent_ordinals = {p.ordinal for p in parents}
    assert all(c.parent_ordinal in parent_ordinals for c in children)


def test_count_tokens_positive():
    assert count_tokens("hello world") >= 2
