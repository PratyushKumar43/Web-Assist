"""Qdrant hybrid vector indexing and retrieval engine."""

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid5, NAMESPACE_URL

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Fusion,
    FusionQuery,
    PointStruct,
    Prefetch,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from app.config import settings

logger = logging.getLogger(__name__)


class QdrantHybridIndexer:
    """Manages collection creation, dual-vector generation, upserting, and RRF retrieval."""

    def __init__(
        self,
        collection_name: Optional[str] = None,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.collection_name = collection_name or settings.QDRANT_COLLECTION
        self.url = url or settings.QDRANT_URL
        self.api_key = api_key or settings.QDRANT_API_KEY

        # Initialize Qdrant Client (Cloud if credentials present, otherwise local path)
        if self.url and self.api_key:
            logger.info("Connecting to Qdrant Cloud at: %s", self.url)
            self.client = QdrantClient(url=self.url, api_key=self.api_key, timeout=30.0)
        else:
            logger.info("Using local embedded Qdrant at: %s", settings.QDRANT_LOCAL_PATH)
            self.client = QdrantClient(path=settings.QDRANT_LOCAL_PATH)

        # Initialize dense and sparse encoders (FastEmbed)
        logger.info("Initializing FastEmbed dense model (BAAI/bge-small-en-v1.5)...")
        self.dense_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        self.dense_dim = 384  # bge-small output dimension

        logger.info("Initializing FastEmbed sparse model (Qdrant/bm25)...")
        self.sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")

    def ensure_collection(self, recreate: bool = False) -> None:
        """Create or recreate the hybrid collection with dense and sparse configs."""
        exists = self.client.collection_exists(self.collection_name)
        if exists and recreate:
            logger.warning("Recreating collection '%s'...", self.collection_name)
            self.client.delete_collection(self.collection_name)
            exists = False

        if not exists:
            logger.info("Creating Qdrant hybrid collection '%s'...", self.collection_name)
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": VectorParams(size=self.dense_dim, distance=Distance.COSINE)
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams()
                },
            )
            logger.info("Collection '%s' created successfully.", self.collection_name)

    def upsert_chunks(self, chunks: List[Dict[str, Any]], batch_size: int = 32) -> int:
        """Embed and upsert chunks in batches directly into Qdrant."""
        if not chunks:
            return 0

        self.ensure_collection(recreate=False)
        total_chunks = len(chunks)
        logger.info("Upserting %d chunks into '%s'...", total_chunks, self.collection_name)

        for i in range(0, total_chunks, batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c["text"] for c in batch]

            # Generate dense embeddings
            dense_vectors = list(self.dense_model.embed(texts))

            # Generate sparse BM25 embeddings
            sparse_vectors = list(self.sparse_model.embed(texts))

            points: List[PointStruct] = []
            for j, chunk in enumerate(batch):
                dense_vec = dense_vectors[j].tolist()
                sparse_vec = sparse_vectors[j]

                # Deterministic UUID from chunk_id
                point_id = str(uuid5(NAMESPACE_URL, f"{chunk['url']}_{chunk['chunk_id']}"))

                points.append(
                    PointStruct(
                        id=point_id,
                        vector={
                            "dense": dense_vec,
                            "sparse": SparseVector(
                                indices=sparse_vec.indices.tolist(),
                                values=sparse_vec.values.tolist(),
                            ),
                        },
                        payload={
                            "chunk_id": chunk["chunk_id"],
                            "chunk_index": chunk.get("chunk_index", 0),
                            "product_id": chunk.get("product_id", ""),
                            "product_name": chunk.get("product_name", ""),
                            "entity_id": chunk.get("entity_id", ""),
                            "parent_id": chunk.get("parent_id", ""),
                            "governing_kfs": chunk.get("governing_kfs", ""),
                            "relations": chunk.get("relations", {}),
                            "category": chunk.get("category", ""),
                            "section_path": chunk.get("section_path", ""),
                            "url": chunk.get("url", ""),
                            "title": chunk.get("title", ""),
                            "crawled_at": chunk.get("crawled_at", ""),
                            "text": chunk["text"],
                        },
                    )
                )

            self.client.upsert(collection_name=self.collection_name, points=points)
            logger.info("Upserted batch %d/%d points.", min(i + batch_size, total_chunks), total_chunks)

        return total_chunks

    def hybrid_search(self, query: str, top_k: int = 6) -> List[Dict[str, Any]]:
        """Perform hybrid search with Reciprocal Rank Fusion (RRF) in Qdrant."""
        # 1. Encode query with dense and sparse models
        dense_q = list(self.dense_model.embed([query]))[0].tolist()
        sparse_q = list(self.sparse_model.embed([query]))[0]

        # 2. Query Qdrant with prefetch on both dense and sparse, fused via RRF
        res = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                Prefetch(query=dense_q, using="dense", limit=top_k * 2),
                Prefetch(
                    query=SparseVector(
                        indices=sparse_q.indices.tolist(),
                        values=sparse_q.values.tolist(),
                    ),
                    using="sparse",
                    limit=top_k * 2,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=top_k,
        )

        results: List[Dict[str, Any]] = []
        for point in res.points:
            item = dict(point.payload)
            item["score"] = point.score
            results.append(item)

        return results


_indexer_instance: Optional[QdrantHybridIndexer] = None


def get_indexer() -> QdrantHybridIndexer:
    """Return a singleton instance of QdrantHybridIndexer."""
    global _indexer_instance
    if _indexer_instance is None:
        _indexer_instance = QdrantHybridIndexer()
    return _indexer_instance

