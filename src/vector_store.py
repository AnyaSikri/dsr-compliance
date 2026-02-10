"""FAISS-backed vector store with OpenAI embeddings.

Provides embedding, indexing, and similarity search for document sections
and text chunks. Supports caching to avoid redundant API calls.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

import faiss
import numpy as np

from .config import Config
from .utils import ensure_dir, logger


class VectorStore:
    """Manages embeddings and FAISS index for semantic search."""

    def __init__(self, config: Config, openai_client: object | None = None):
        self.config = config
        self._openai_client = openai_client
        self.dimension = config.embedding_dim
        # Use inner product after L2-normalizing to get cosine similarity
        self.index: faiss.IndexFlatIP = faiss.IndexFlatIP(self.dimension)
        self.metadata: list[dict] = []
        self._cache_dir = ensure_dir(config.vector_index_dir)

    def _get_embeddings(self, texts: list[str]) -> np.ndarray:
        """Get embeddings from OpenAI API, batching in groups of 100."""
        if self.config.dry_run or self._openai_client is None:
            # Return random unit vectors for dry-run / testing
            rng = np.random.default_rng(42)
            vecs = rng.standard_normal((len(texts), self.dimension)).astype("float32")
            faiss.normalize_L2(vecs)
            return vecs

        from openai import OpenAI

        client = OpenAI(api_key=self.config.openai_api_key)
        all_embeddings: list[list[float]] = []
        batch_size = 100

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            # Truncate very long texts to avoid token limits
            batch = [t[:8000] for t in batch]
            response = client.embeddings.create(
                input=batch,
                model=self.config.embedding_model,
            )
            for item in response.data:
                all_embeddings.append(item.embedding)

        vecs = np.array(all_embeddings, dtype="float32")
        faiss.normalize_L2(vecs)
        return vecs

    def add_documents(
        self,
        texts: list[str],
        metadata: list[dict],
        source_type: str,
    ) -> None:
        """Add documents to the index with metadata.

        Each metadata dict is augmented with 'source_type' for filtering.
        """
        if not texts:
            return

        if len(texts) != len(metadata):
            raise ValueError(
                f"texts ({len(texts)}) and metadata ({len(metadata)}) must have same length"
            )

        # Augment metadata with source_type
        enriched = [{**m, "source_type": source_type} for m in metadata]

        embeddings = self._get_embeddings(texts)
        self.index.add(embeddings)
        self.metadata.extend(enriched)
        logger.info(
            "Added %d documents (source_type=%s), total=%d",
            len(texts),
            source_type,
            self.index.ntotal,
        )

    def search(
        self,
        query: str,
        k: int = 5,
        filter_source: Optional[str] = None,
    ) -> list[dict]:
        """Search for similar documents.

        Returns a list of dicts with 'metadata' and 'score' keys,
        sorted by descending score. If filter_source is given, only
        returns results with matching source_type.
        """
        if self.index.ntotal == 0:
            return []

        query_vec = self._get_embeddings([query])

        # Search more than k if filtering, to ensure enough results after filter
        search_k = min(k * 3, self.index.ntotal) if filter_source else min(k, self.index.ntotal)
        scores, indices = self.index.search(query_vec, search_k)

        results: list[dict] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            meta = self.metadata[idx]
            if filter_source and meta.get("source_type") != filter_source:
                continue
            results.append({"metadata": meta, "score": float(score)})
            if len(results) >= k:
                break

        return results

    def save(self, name: str) -> None:
        """Persist index and metadata to disk."""
        index_path = self._cache_dir / f"{name}.faiss"
        meta_path = self._cache_dir / f"{name}.meta.json"

        faiss.write_index(self.index, str(index_path))
        meta_path.write_text(
            json.dumps(self.metadata, indent=2), encoding="utf-8"
        )
        logger.info("Saved vector index '%s' (%d vectors)", name, self.index.ntotal)

    def load(self, name: str) -> bool:
        """Load index from disk. Returns True if loaded successfully."""
        index_path = self._cache_dir / f"{name}.faiss"
        meta_path = self._cache_dir / f"{name}.meta.json"

        if not index_path.exists() or not meta_path.exists():
            return False

        try:
            self.index = faiss.read_index(str(index_path))
            self.metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            logger.info(
                "Loaded vector index '%s' (%d vectors)", name, self.index.ntotal
            )
            return True
        except Exception as e:
            logger.warning("Failed to load vector index '%s': %s", name, e)
            return False

    @staticmethod
    def content_hash(texts: list[str]) -> str:
        """SHA256 hash of all texts for cache invalidation."""
        combined = "\n".join(texts)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
