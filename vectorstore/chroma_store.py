"""ChromaDB persistent vector store for fraud detection knowledge and transactions."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from config.settings import get_settings

logger = logging.getLogger(__name__)


class ChromaVectorStore:
    """Thin wrapper around ChromaDB exposing upsert, query, and delete operations."""

    def __init__(self, persist_dir: str | None = None) -> None:
        cfg = get_settings()
        self._persist_dir = persist_dir or cfg.chroma_persist_dir
        Path(self._persist_dir).mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=self._persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        logger.info("ChromaDB initialised at %s", self._persist_dir)

    # ── collection management ─────────────────────────────────────────────────

    def get_or_create_collection(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> chromadb.Collection:
        return self._client.get_or_create_collection(
            name=name,
            metadata=metadata or {"hnsw:space": "cosine"},
        )

    def delete_collection(self, name: str) -> None:
        try:
            self._client.delete_collection(name)
            logger.info("Deleted collection '%s'", name)
        except Exception:
            logger.warning("Collection '%s' not found for deletion", name)

    def list_collections(self) -> list[str]:
        return [c.name for c in self._client.list_collections()]

    # ── upsert ────────────────────────────────────────────────────────────────

    def upsert(
        self,
        collection_name: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        collection = self.get_or_create_collection(collection_name)
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas or [{} for _ in ids],
        )
        logger.debug("Upserted %d documents into '%s'", len(ids), collection_name)

    # ── query ─────────────────────────────────────────────────────────────────

    def query(
        self,
        collection_name: str,
        query_embeddings: list[list[float]],
        n_results: int = 5,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        collection = self.get_or_create_collection(collection_name)
        kwargs: dict[str, Any] = {
            "query_embeddings": query_embeddings,
            "n_results": n_results,
            "include": include or ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        return collection.query(**kwargs)

    def query_by_text(
        self,
        collection_name: str,
        query_texts: list[str],
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Query using ChromaDB's built-in embedding (useful for quick checks)."""
        collection = self.get_or_create_collection(collection_name)
        kwargs: dict[str, Any] = {
            "query_texts": query_texts,
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        return collection.query(**kwargs)

    # ── count ─────────────────────────────────────────────────────────────────

    def count(self, collection_name: str) -> int:
        try:
            return self.get_or_create_collection(collection_name).count()
        except Exception:
            return 0

    # ── delete ────────────────────────────────────────────────────────────────

    def delete(self, collection_name: str, ids: list[str]) -> None:
        collection = self.get_or_create_collection(collection_name)
        collection.delete(ids=ids)

    # ── health ────────────────────────────────────────────────────────────────

    def health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "persist_dir": self._persist_dir,
            "collections": {
                name: self.count(name) for name in self.list_collections()
            },
        }


@lru_cache(maxsize=1)
def get_vector_store() -> ChromaVectorStore:
    return ChromaVectorStore()
