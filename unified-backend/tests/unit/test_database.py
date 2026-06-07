"""Unit tests for app/config/database.py — connection lifecycle and accessors."""

import pytest

from app.config.database import (
    get_db,
    profiles_col,
    skill_graph_col,
    sessions_col,
    ingestion_jobs_col,
    embeddings_col,
    immediate_contexts_col,
)


class TestGetDb:
    """Verify get_db raises RuntimeError when not connected."""

    def test_get_db_raises_when_not_connected(self):
        """get_db() raises RuntimeError if database is not connected."""
        import app.config.database as db_mod

        # Ensure disconnected state
        original_db = db_mod._db
        db_mod._db = None
        try:
            with pytest.raises(RuntimeError, match="Database not connected"):
                get_db()
        finally:
            db_mod._db = original_db


class TestCollectionAccessors:
    """Verify collection accessors return correct collection names."""

    def test_collection_accessors_raise_when_not_connected(self):
        """All collection accessors raise RuntimeError if DB not connected."""
        import app.config.database as db_mod

        original_db = db_mod._db
        db_mod._db = None
        try:
            with pytest.raises(RuntimeError):
                profiles_col()
            with pytest.raises(RuntimeError):
                skill_graph_col()
            with pytest.raises(RuntimeError):
                sessions_col()
            with pytest.raises(RuntimeError):
                ingestion_jobs_col()
            with pytest.raises(RuntimeError):
                embeddings_col()
            with pytest.raises(RuntimeError):
                immediate_contexts_col()
        finally:
            db_mod._db = original_db
