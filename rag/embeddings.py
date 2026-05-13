"""Embedding service using sentence-transformers (runs fully locally, no API key)."""
from __future__ import annotations

import logging
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from config.settings import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Wraps sentence-transformers to produce float embeddings.

    Default model: all-MiniLM-L6-v2 (22 MB, 384-dim, ~14k tokens/sec on CPU).
    Drop-in replacement: swap model name in settings for a larger model.
    """

    def __init__(self, model_name: str | None = None, device: str | None = None) -> None:
        cfg = get_settings()
        self._model_name = model_name or cfg.embedding_model
        self._device = device or cfg.embedding_device
        logger.info("Loading embedding model '%s' on %s", self._model_name, self._device)
        self._model = SentenceTransformer(self._model_name, device=self._device)
        self._dim = self._model.get_sentence_embedding_dimension()
        logger.info("Embedding model loaded (dim=%d)", self._dim)

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        """Return L2-normalised embeddings as plain Python lists."""
        if not texts:
            return []
        vectors = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
