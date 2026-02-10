"""Tests for Config dataclass extensions."""

from __future__ import annotations

from pathlib import Path

from src.config import Config


class TestConfigExtensions:
    def test_default_pbrer_path(self) -> None:
        cfg = Config()
        assert cfg.pbrer_path == Path("data/input/pbrer.pdf")

    def test_default_embedding_model(self) -> None:
        cfg = Config()
        assert cfg.embedding_model == "text-embedding-3-small"

    def test_default_embedding_dim(self) -> None:
        cfg = Config()
        assert cfg.embedding_dim == 1536

    def test_default_vector_index_dir(self) -> None:
        cfg = Config()
        assert cfg.vector_index_dir == Path("data/intermediate/vector_index")

    def test_default_chunk_settings(self) -> None:
        cfg = Config()
        assert cfg.chunk_size == 500
        assert cfg.chunk_overlap == 50

    def test_default_ocr_enabled(self) -> None:
        cfg = Config()
        assert cfg.ocr_enabled is True

    def test_from_env_overrides_pbrer(self) -> None:
        cfg = Config.from_env(
            pbrer_path=Path("/tmp/test.pdf"),
            dry_run=True,
        )
        assert cfg.pbrer_path == Path("/tmp/test.pdf")

    def test_from_env_overrides_embedding_model(self) -> None:
        cfg = Config.from_env(
            embedding_model="text-embedding-3-large",
            dry_run=True,
        )
        assert cfg.embedding_model == "text-embedding-3-large"
