"""Integration tests for atlas.storage.database."""

import pytest
from sqlalchemy import text

from atlas.storage.database import Database, get_database, reset_database


class TestDatabase:
    def test_create_with_sqlite(self):
        db = Database(connection_string="sqlite:///:memory:")
        assert db.health_check() is True

    def test_create_tables(self):
        db = Database(connection_string="sqlite:///:memory:")
        db.create_tables()
        with db.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ))
            tables = [row[0] for row in result]
        assert "pipeline_run" in tables
        assert "dim_instrument" in tables
        assert "fact_ohlcv" in tables
        assert "fact_macro" in tables
        assert "fact_feature" in tables

    def test_session_context_manager(self):
        db = Database(connection_string="sqlite:///:memory:")
        db.create_tables()
        from atlas.storage.models import DimSource
        with db.session() as session:
            session.add(DimSource(name="test", provider_type="test"))
        with db.session() as session:
            from sqlalchemy import select
            count = len(list(session.scalars(select(DimSource))))
        assert count == 1

    def test_session_rollback_on_error(self):
        db = Database(connection_string="sqlite:///:memory:")
        db.create_tables()
        from atlas.storage.models import DimSource
        from atlas.core.exceptions import DatabaseError
        with pytest.raises(DatabaseError):
            with db.session() as session:
                session.add(DimSource(name="test", provider_type="test"))
                session.flush()
                session.add(DimSource(name="test", provider_type="test"))
                session.flush()

    def test_health_check_passes(self):
        db = Database(connection_string="sqlite:///:memory:")
        assert db.health_check() is True

    def test_close(self):
        db = Database(connection_string="sqlite:///:memory:")
        db.create_tables()
        db.close()
        assert db._engine is None
        assert db._session_factory is None

    def test_drop_tables(self):
        db = Database(connection_string="sqlite:///:memory:")
        db.create_tables()
        db.drop_tables()
        with db.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ))
            tables = [row[0] for row in result]
        assert "pipeline_run" not in tables


class TestGetDatabase:
    def test_returns_singleton(self, monkeypatch):
        monkeypatch.setenv("ATLAS_DB_CONNECTION", "sqlite:///:memory:")
        reset_database()
        db1 = get_database()
        db2 = get_database()
        assert db1 is db2
        reset_database()

    def test_fallback_to_sqlite(self, monkeypatch):
        monkeypatch.delenv("ATLAS_DB_CONNECTION", raising=False)
        reset_database()
        db = get_database()
        assert db.health_check()
        reset_database()
