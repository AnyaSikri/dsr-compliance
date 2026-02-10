"""Chunk text into overlapping windows of approximately N tokens.

Used by the vectorization layer to split large document sections into
embeddable pieces with overlap for context continuity.
"""

from __future__ import annotations

import tiktoken


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
    encoding_name: str = "cl100k_base",
) -> list[dict]:
    """Split text into overlapping token-based chunks.

    Returns a list of dicts, each with:
        - "text": the chunk text
        - "start_char": character offset of the chunk start
        - "end_char": character offset of the chunk end
        - "token_count": number of tokens in the chunk
    """
    if not text.strip():
        return []

    enc = tiktoken.get_encoding(encoding_name)
    tokens = enc.encode(text)

    if not tokens:
        return []

    chunks: list[dict] = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text_str = enc.decode(chunk_tokens)

        # Calculate character offsets by decoding prefix
        start_char = len(enc.decode(tokens[:start])) if start > 0 else 0
        end_char = start_char + len(chunk_text_str)

        chunks.append({
            "text": chunk_text_str,
            "start_char": start_char,
            "end_char": end_char,
            "token_count": len(chunk_tokens),
        })

        # Advance by (chunk_size - overlap) tokens
        step = chunk_size - overlap
        if step <= 0:
            step = chunk_size  # Prevent infinite loop if overlap >= chunk_size
        start += step

    return chunks
