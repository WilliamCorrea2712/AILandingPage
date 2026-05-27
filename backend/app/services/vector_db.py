"""
Vector Database abstraction layer.

Supports Qdrant, ChromaDB and Weaviate, selected via VECTOR_DB_PROVIDER env var.

Requirements: 12.3, 12.7
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ("qdrant", "chromadb", "weaviate")


class VectorDBClient(ABC):
    """Abstract interface for vector database operations."""

    @abstractmethod
    def upsert(self, collection: str, id: str, vector: list[float], payload: dict) -> None:
        """Insert or update a vector with associated payload."""

    @abstractmethod
    def search(
        self,
        collection: str,
        query_vector: list[float],
        threshold: float = 0.50,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Search for similar vectors using cosine similarity.
        Returns list of dicts with keys: id, score, payload.
        """

    @abstractmethod
    def delete(self, collection: str, id: str) -> None:
        """Delete a vector by ID."""

    @abstractmethod
    def create_collection(self, collection: str, vector_size: int) -> None:
        """Create a collection if it does not exist."""


class QdrantVectorDBClient(VectorDBClient):
    """Qdrant implementation."""

    def __init__(self, url: str) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        self._client = QdrantClient(url=url)
        self._Distance = Distance
        self._VectorParams = VectorParams

    def create_collection(self, collection: str, vector_size: int) -> None:
        from qdrant_client.models import Distance, VectorParams
        existing = [c.name for c in self._client.get_collections().collections]
        if collection not in existing:
            self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def upsert(self, collection: str, id: str, vector: list[float], payload: dict) -> None:
        from qdrant_client.models import PointStruct
        self._client.upsert(
            collection_name=collection,
            points=[PointStruct(id=id, vector=vector, payload=payload)],
        )

    def search(self, collection: str, query_vector: list[float], threshold: float = 0.50, limit: int = 5) -> list[dict]:
        results = self._client.search(
            collection_name=collection,
            query_vector=query_vector,
            score_threshold=threshold,
            limit=limit,
        )
        return [{"id": r.id, "score": r.score, "payload": r.payload} for r in results]

    def delete(self, collection: str, id: str) -> None:
        from qdrant_client.models import PointIdsList
        self._client.delete(collection_name=collection, points_selector=PointIdsList(points=[id]))


class ChromaDBVectorDBClient(VectorDBClient):
    """ChromaDB implementation."""

    def __init__(self, url: str) -> None:
        import chromadb
        self._client = chromadb.HttpClient(host=url.replace("http://", "").split(":")[0],
                                            port=int(url.split(":")[-1]))

    def create_collection(self, collection: str, vector_size: int) -> None:
        self._client.get_or_create_collection(name=collection)

    def upsert(self, collection: str, id: str, vector: list[float], payload: dict) -> None:
        col = self._client.get_or_create_collection(name=collection)
        col.upsert(ids=[id], embeddings=[vector], metadatas=[payload])

    def search(self, collection: str, query_vector: list[float], threshold: float = 0.50, limit: int = 5) -> list[dict]:
        col = self._client.get_or_create_collection(name=collection)
        results = col.query(query_embeddings=[query_vector], n_results=limit)
        output = []
        for i, doc_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i]
            score = 1.0 - distance  # ChromaDB returns L2 distance; approximate cosine
            if score >= threshold:
                output.append({"id": doc_id, "score": score, "payload": results["metadatas"][0][i]})
        return output

    def delete(self, collection: str, id: str) -> None:
        col = self._client.get_or_create_collection(name=collection)
        col.delete(ids=[id])


class WeaviateVectorDBClient(VectorDBClient):
    """Weaviate implementation."""

    def __init__(self, url: str) -> None:
        import weaviate
        self._client = weaviate.connect_to_custom(http_host=url.replace("http://", "").split(":")[0],
                                                   http_port=int(url.split(":")[-1]),
                                                   http_secure=False,
                                                   grpc_host=url.replace("http://", "").split(":")[0],
                                                   grpc_port=50051,
                                                   grpc_secure=False)

    def create_collection(self, collection: str, vector_size: int) -> None:
        if not self._client.collections.exists(collection):
            self._client.collections.create(collection)

    def upsert(self, collection: str, id: str, vector: list[float], payload: dict) -> None:
        col = self._client.collections.get(collection)
        col.data.insert(properties=payload, vector=vector, uuid=id)

    def search(self, collection: str, query_vector: list[float], threshold: float = 0.50, limit: int = 5) -> list[dict]:
        import weaviate.classes as wvc
        col = self._client.collections.get(collection)
        results = col.query.near_vector(near_vector=query_vector, limit=limit,
                                         return_metadata=wvc.query.MetadataQuery(certainty=True))
        return [
            {"id": str(o.uuid), "score": o.metadata.certainty or 0.0, "payload": o.properties}
            for o in results.objects
            if (o.metadata.certainty or 0.0) >= threshold
        ]

    def delete(self, collection: str, id: str) -> None:
        col = self._client.collections.get(collection)
        col.data.delete_by_id(id)


def get_vector_db_client() -> VectorDBClient:
    """
    Factory that returns the configured VectorDBClient.
    Raises SystemExit with a descriptive message if VECTOR_DB_PROVIDER is invalid.
    """
    provider = settings.VECTOR_DB_PROVIDER.lower().strip()
    url = settings.VECTOR_DB_URL

    if provider not in SUPPORTED_PROVIDERS:
        msg = (
            f"VECTOR_DB_PROVIDER='{provider}' não é suportado. "
            f"Valores aceitos: {', '.join(SUPPORTED_PROVIDERS)}"
        )
        logger.critical(msg)
        raise SystemExit(msg)

    if provider == "qdrant":
        return QdrantVectorDBClient(url)
    if provider == "chromadb":
        return ChromaDBVectorDBClient(url)
    # weaviate
    return WeaviateVectorDBClient(url)
