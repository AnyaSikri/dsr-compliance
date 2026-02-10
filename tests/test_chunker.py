"""Tests for text chunking utility."""

from __future__ import annotations

from src.chunker import chunk_text


class TestChunkText:
    def test_basic_chunking(self) -> None:
        text = "word " * 1000  # ~1000 tokens
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        assert len(chunks) >= 2

    def test_overlap_creates_redundancy(self) -> None:
        text = "word " * 1000
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        # With overlap, chunk 1 start should be before chunk 0 end
        assert len(chunks) >= 2
        assert chunks[1]["start_char"] < chunks[0]["end_char"]

    def test_short_text_single_chunk(self) -> None:
        text = "short text"
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        assert len(chunks) == 1
        assert chunks[0]["text"] == "short text"

    def test_empty_text_no_chunks(self) -> None:
        chunks = chunk_text("", chunk_size=500, overlap=50)
        assert chunks == []

    def test_whitespace_only_no_chunks(self) -> None:
        chunks = chunk_text("   \n\n  ", chunk_size=500, overlap=50)
        assert chunks == []

    def test_chunk_has_expected_keys(self) -> None:
        chunks = chunk_text("hello world", chunk_size=500, overlap=50)
        assert len(chunks) == 1
        chunk = chunks[0]
        assert "text" in chunk
        assert "start_char" in chunk
        assert "end_char" in chunk
        assert "token_count" in chunk

    def test_token_count_within_limit(self) -> None:
        text = "word " * 2000
        chunks = chunk_text(text, chunk_size=100, overlap=10)
        for chunk in chunks:
            assert chunk["token_count"] <= 100

    def test_no_overlap_mode(self) -> None:
        text = "word " * 200
        chunks = chunk_text(text, chunk_size=100, overlap=0)
        assert len(chunks) >= 2
        # With no overlap, chunks should not overlap in character positions
        assert chunks[1]["start_char"] >= chunks[0]["end_char"] - 5  # small tolerance for token boundaries
