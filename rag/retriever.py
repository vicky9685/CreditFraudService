"""Fraud knowledge base retriever — indexes markdown docs into ChromaDB and queries them."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from langchain.text_splitter import RecursiveCharacterTextSplitter

from config.settings import get_settings
from rag.embeddings import EmbeddingService, get_embedding_service
from vectorstore.chroma_store import ChromaVectorStore, get_vector_store

logger = logging.getLogger(__name__)

_KB_DIR = Path(__file__).parent.parent / "data" / "knowledge_base"


class FraudKnowledgeRetriever:
    """
    Indexes the knowledge-base markdown files into ChromaDB and supports
    semantic retrieval with optional metadata filters.
    """

    def __init__(
        self,
        store: ChromaVectorStore | None = None,
        embedder: EmbeddingService | None = None,
    ) -> None:
        self._cfg = get_settings()
        self._store = store or get_vector_store()
        self._embedder = embedder or get_embedding_service()
        self._collection = self._cfg.chroma_collection_fraud_kb
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self._cfg.rag_chunk_size,
            chunk_overlap=self._cfg.rag_chunk_overlap,
            separators=["\n## ", "\n### ", "\n\n", "\n", " "],
        )

    # ── indexing ──────────────────────────────────────────────────────────────

    def index_knowledge_base(self, kb_dir: Path | None = None) -> int:
        """Load all .md files, chunk, embed, and upsert into ChromaDB."""
        kb_path = kb_dir or _KB_DIR
        if not kb_path.exists():
            raise FileNotFoundError(f"Knowledge base directory not found: {kb_path}")

        md_files = list(kb_path.glob("*.md"))
        if not md_files:
            logger.warning("No .md files found in %s", kb_path)
            return 0

        all_ids, all_embeddings, all_docs, all_meta = [], [], [], []

        for md_file in md_files:
            raw_text = md_file.read_text(encoding="utf-8")
            chunks = self._splitter.split_text(raw_text)
            logger.info("File '%s' → %d chunks", md_file.name, len(chunks))

            for i, chunk in enumerate(chunks):
                doc_id = hashlib.md5(
                    f"{md_file.name}:{i}:{chunk[:64]}".encode()
                ).hexdigest()
                all_ids.append(doc_id)
                all_docs.append(chunk)
                all_meta.append({
                    "source": md_file.name,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                })

        embeddings = self._embedder.embed(all_docs)
        self._store.upsert(
            collection_name=self._collection,
            ids=all_ids,
            embeddings=embeddings,
            documents=all_docs,
            metadatas=all_meta,
        )
        total = len(all_ids)
        logger.info("Indexed %d chunks into collection '%s'", total, self._collection)
        return total

    # ── retrieval ─────────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        source_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the top-k most relevant chunks for a natural-language query."""
        k = top_k or self._cfg.rag_top_k
        query_vec = self._embedder.embed_one(query)
        where = {"source": source_filter} if source_filter else None

        results = self._store.query(
            collection_name=self._collection,
            query_embeddings=[query_vec],
            n_results=k,
            where=where,
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        items = []
        for doc, meta, dist in zip(documents, metadatas, distances):
            similarity = 1.0 - dist  # cosine: distance → similarity
            if similarity >= self._cfg.rag_similarity_threshold:
                items.append({
                    "content": doc,
                    "source": meta.get("source", "unknown"),
                    "similarity": round(similarity, 4),
                    "metadata": meta,
                })
        return items

    def retrieve_as_context(self, query: str, top_k: int | None = None) -> str:
        """Return retrieved chunks formatted as a single context string for prompting."""
        items = self.retrieve(query, top_k)
        if not items:
            return "No relevant knowledge base entries found."
        parts = []
        for i, item in enumerate(items, 1):
            parts.append(
                f"[Source {i}: {item['source']} | similarity={item['similarity']}]\n"
                f"{item['content']}"
            )
        return "\n\n---\n\n".join(parts)

    def is_indexed(self) -> bool:
        return self._store.count(self._collection) > 0

    def collection_stats(self) -> dict[str, Any]:
        return {
            "collection": self._collection,
            "document_count": self._store.count(self._collection),
            "embedding_model": self._cfg.embedding_model,
            "embedding_dim": self._embedder.dimension,
        }
