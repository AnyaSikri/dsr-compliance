"""Tests for FAISS vector store."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.config import Config
from src.vector_store import VectorStore


@pytest.fixture()
def dry_run_config(tmp_path: Path) -> Config:
    """Config with dry_run=True for deterministic fake embeddings."""
    return Config(
        dry_run=True,
        vector_index_dir=tmp_path / "vectors",
        embedding_dim=64,
    )


@pytest.fixture()
def store(dry_run_config: Config) -> VectorStore:
    return VectorStore(dry_run_config)


class TestVectorStore:
    def test_add_and_search(self, store: VectorStore) -> None:
        store.add_documents(
            texts=["hello world", "foo bar baz"],
            metadata=[{"id": "1"}, {"id": "2"}],
            source_type="test",
        )
        results = store.search("hello", k=2)
        assert len(results) == 2
        assert "metadata" in results[0]
        assert "score" in results[0]

    def test_filter_by_source_type(self, store: VectorStore) -> None:
        store.add_documents(
            texts=["IB content"],
            metadata=[{"id": "ib1"}],
            source_type="ib",
        )
        store.add_documents(
            texts=["template content"],
            metadata=[{"id": "t1"}],
            source_type="template",
        )

        ib_results = store.search("content", k=5, filter_source="ib")
        for r in ib_results:
            assert r["metadata"]["source_type"] == "ib"

        tmpl_results = store.search("content", k=5, filter_source="template")
        for r in tmpl_results:
            assert r["metadata"]["source_type"] == "template"

    def test_empty_index_search(self, store: VectorStore) -> None:
        results = store.search("anything")
        assert results == []

    def test_save_and_load(self, store: VectorStore, dry_run_config: Config) -> None:
        store.add_documents(
            texts=["doc one", "doc two", "doc three"],
            metadata=[{"n": 1}, {"n": 2}, {"n": 3}],
            source_type="test",
        )
        store.save("test_index")

        # Create a new store and load
        store2 = VectorStore(dry_run_config)
        assert store2.index.ntotal == 0
        loaded = store2.load("test_index")
        assert loaded is True
        assert store2.index.ntotal == 3
        assert len(store2.metadata) == 3

    def test_load_nonexistent_returns_false(self, store: VectorStore) -> None:
        assert store.load("nonexistent") is False

    def test_metadata_length_mismatch_raises(self, store: VectorStore) -> None:
        with pytest.raises(ValueError, match="same length"):
            store.add_documents(
                texts=["one", "two"],
                metadata=[{"id": "1"}],
                source_type="test",
            )

    def test_add_empty_texts(self, store: VectorStore) -> None:
        store.add_documents(texts=[], metadata=[], source_type="test")
        assert store.index.ntotal == 0

    def test_content_hash(self) -> None:
        h1 = VectorStore.content_hash(["a", "b"])
        h2 = VectorStore.content_hash(["a", "b"])
        h3 = VectorStore.content_hash(["a", "c"])
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 16
