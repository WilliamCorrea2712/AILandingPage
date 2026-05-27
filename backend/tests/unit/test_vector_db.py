"""
Unit tests for the Vector Database abstraction layer (Task 5.1).

Tests cover:
- Factory function raises RuntimeError for missing/invalid provider
- Factory function selects the correct concrete class
- Abstract interface is properly defined

Requirements: 12.3, 12.7
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(provider: str = "qdrant", url: str = "http://localhost:6333"):
    mock = MagicMock()
    mock.VECTOR_DB_PROVIDER = provider
    mock.VECTOR_DB_URL = url
    return mock


# ---------------------------------------------------------------------------
# Factory function tests
# ---------------------------------------------------------------------------


class TestGetVectorDbClient:
    def test_invalid_provider_raises_runtime_error(self, monkeypatch):
        from app.services import vector_db as vdb_module

        monkeypatch.setattr(vdb_module, "settings", _make_settings("invalid_db"))

        with pytest.raises(RuntimeError, match="não é suportado"):
            vdb_module.get_vector_db_client()

    def test_empty_provider_raises_runtime_error(self, monkeypatch):
        from app.services import vector_db as vdb_module

        monkeypatch.setattr(vdb_module, "settings", _make_settings(""))

        with pytest.raises(RuntimeError, match="não está configurado"):
            vdb_module.get_vector_db_client()

    def test_error_message_lists_accepted_values(self, monkeypatch):
        from app.services import vector_db as vdb_module

        monkeypatch.setattr(vdb_module, "settings", _make_settings("postgres"))

        with pytest.raises(RuntimeError) as exc_info:
            vdb_module.get_vector_db_client()

        msg = str(exc_info.value)
        assert "qdrant" in msg
        assert "chromadb" in msg
        assert "weaviate" in msg

    def test_qdrant_provider_instantiates_qdrant_client(self, monkeypatch):
        from app.services import vector_db as vdb_module

        monkeypatch.setattr(vdb_module, "settings", _make_settings("qdrant"))

        mock_qdrant_instance = MagicMock()
        mock_qdrant_class = MagicMock(return_value=mock_qdrant_instance)

        with patch.dict(vdb_module._PROVIDER_MAP, {"qdrant": mock_qdrant_class}):
            client = vdb_module.get_vector_db_client()

        mock_qdrant_class.assert_called_once_with("http://localhost:6333")
        assert client is mock_qdrant_instance

    def test_chromadb_provider_instantiates_chroma_client(self, monkeypatch):
        from app.services import vector_db as vdb_module

        monkeypatch.setattr(vdb_module, "settings", _make_settings("chromadb", "http://localhost:8000"))

        mock_chroma_instance = MagicMock()
        mock_chroma_class = MagicMock(return_value=mock_chroma_instance)

        with patch.dict(vdb_module._PROVIDER_MAP, {"chromadb": mock_chroma_class}):
            client = vdb_module.get_vector_db_client()

        mock_chroma_class.assert_called_once_with("http://localhost:8000")
        assert client is mock_chroma_instance

    def test_weaviate_provider_instantiates_weaviate_client(self, monkeypatch):
        from app.services import vector_db as vdb_module

        monkeypatch.setattr(vdb_module, "settings", _make_settings("weaviate", "http://localhost:8080"))

        mock_weaviate_instance = MagicMock()
        mock_weaviate_class = MagicMock(return_value=mock_weaviate_instance)

        with patch.dict(vdb_module._PROVIDER_MAP, {"weaviate": mock_weaviate_class}):
            client = vdb_module.get_vector_db_client()

        mock_weaviate_class.assert_called_once_with("http://localhost:8080")
        assert client is mock_weaviate_instance

    def test_provider_value_is_case_insensitive(self, monkeypatch):
        """Provider name should be normalised to lowercase before lookup."""
        from app.services import vector_db as vdb_module

        monkeypatch.setattr(vdb_module, "settings", _make_settings("Qdrant"))

        mock_instance = MagicMock()
        mock_class = MagicMock(return_value=mock_instance)

        with patch.dict(vdb_module._PROVIDER_MAP, {"qdrant": mock_class}):
            client = vdb_module.get_vector_db_client()

        assert client is mock_instance


# ---------------------------------------------------------------------------
# Abstract interface tests
# ---------------------------------------------------------------------------


class TestVectorDBClientInterface:
    def test_abstract_class_cannot_be_instantiated(self):
        from app.services.vector_db import VectorDBClient

        with pytest.raises(TypeError):
            VectorDBClient()  # type: ignore[abstract]

    def test_concrete_class_must_implement_all_methods(self):
        """A partial implementation should raise TypeError on instantiation."""
        from app.services.vector_db import VectorDBClient

        class PartialImpl(VectorDBClient):
            def upsert(self, id, vector, payload=None):
                pass
            # Missing search and delete

        with pytest.raises(TypeError):
            PartialImpl()  # type: ignore[abstract]

    def test_full_implementation_can_be_instantiated(self):
        from app.services.vector_db import VectorDBClient

        class FullImpl(VectorDBClient):
            def upsert(self, id, vector, payload=None):
                pass

            def search(self, query_vector, threshold=0.50, limit=5):
                return []

            def delete(self, id):
                pass

        client = FullImpl()
        assert isinstance(client, VectorDBClient)
