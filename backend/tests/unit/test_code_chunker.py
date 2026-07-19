from ingestion.chunkers.code import CodeChunker


def test_symbol_aware_chunking_preserves_functions_methods_and_lines():
    source = """import os

class Worker:
    def run(self):
        return os.getcwd()

def deploy(name: str):
    return f\"deploy:{name}\"
"""
    chunks = CodeChunker(language="python").chunk(source, chunk_size=200, overlap=10)

    symbols = [(chunk.metadata.get("symbol_kind"), chunk.metadata.get("symbol")) for chunk in chunks]
    assert symbols == [("module", None), ("class", "Worker"), ("function", "run"), ("function", "deploy")]
    assert all(chunk.metadata["language"] == "python" for chunk in chunks)
    assert chunks[-1].metadata["line_start"] == 7


def test_oversized_symbol_uses_bounded_recursive_fallback():
    source = "def huge():\n" + "\n".join(f"    value_{index} = '{'x' * 40}'" for index in range(200))
    chunks = CodeChunker(language="python").chunk(source, chunk_size=80, overlap=10)

    assert len(chunks) > 1
    assert all(chunk.metadata["symbol"] == "huge" for chunk in chunks)
    assert all(chunk.metadata["oversized_symbol_fallback"] is True for chunk in chunks)
    assert max(chunk.token_count for chunk in chunks) <= 100
