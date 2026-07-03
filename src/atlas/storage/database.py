"""Database connection and session management."""

import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from atlas.core.config import get_settings
from atlas.core.exceptions import DatabaseError
from atlas.core.logging import get_logger
from atlas.core.secrets import get_secret
from atlas.storage.models import Base

logger = get_logger(__name__)


class Database:
    """Database connection manager."""

    def __init__(
        self,
        connection_string: Optional[str] = None,
        echo: bool = False,
    ) -> None:
        """
        Initialize database connection.
        
        Args:
            connection_string: Database connection string. If not provided,
                              will attempt to load from environment/Key Vault.
            echo: Whether to echo SQL statements (for debugging)
        """
        self._connection_string = connection_string or self._get_connection_string()
        self._echo = echo
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker[Session]] = None

    def _get_connection_string(self) -> str:
        """Get connection string from environment or Key Vault."""
        settings = get_settings()

        # First try environment variable
        conn_str = os.getenv("ATLAS_DB_CONNECTION")
        if conn_str:
            return conn_str

        # Try to load from Key Vault (for Azure deployment)
        try:
            conn_str = get_secret(settings.database.connection_string_key)
            if conn_str:
                return conn_str
        except Exception as e:
            logger.warning("Could not load connection string from Key Vault", error=str(e))

        if settings.environment.lower() not in {"development", "dev", "local", "test", "testing"}:
            raise DatabaseError(
                "Database connection string is required outside development",
                operation="connect",
                details={
                    "environment": settings.environment,
                    "secret_name": settings.database.connection_string_key,
                },
            )

        # Fall back to local SQLite for development
        logger.warning("Using local SQLite database (development mode)")
        return "sqlite:///atlas_dev.db"

    @property
    def engine(self) -> Engine:
        """Get or create the SQLAlchemy engine."""
        if self._engine is None:
            settings = get_settings()
            
            # Determine pool settings based on driver
            is_sqlite = self._connection_string.startswith("sqlite")
            
            pool_kwargs = {}
            if not is_sqlite:
                pool_kwargs = {
                    "poolclass": QueuePool,
                    "pool_size": settings.database.pool_size,
                    "max_overflow": settings.database.max_overflow,
                    "pool_timeout": settings.database.pool_timeout,
                    "pool_recycle": settings.database.pool_recycle,
                }

            self._engine = create_engine(
                self._connection_string,
                echo=self._echo,
                **pool_kwargs,
            )

            # Add event listeners for connection lifecycle
            @event.listens_for(self._engine, "connect")
            def on_connect(dbapi_conn, connection_record):
                logger.debug("Database connection established")

            @event.listens_for(self._engine, "checkout")
            def on_checkout(dbapi_conn, connection_record, connection_proxy):
                logger.debug("Database connection checked out from pool")

            logger.info(
                "Database engine created",
                driver=self._engine.dialect.name,
                pool_size=pool_kwargs.get("pool_size", "N/A"),
            )

        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        """Get or create the session factory."""
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
            )
        return self._session_factory

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """
        Create a database session context manager.
        
        Usage:
            with db.session() as session:
                # Use session
                session.add(obj)
                session.commit()
        """
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Database session error", error=str(e))
            raise DatabaseError(
                "Database operation failed",
                cause=e,
            ) from e
        finally:
            session.close()

    def create_tables(self) -> None:
        """Create all tables defined in models."""
        logger.info("Creating database tables")
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created successfully")

    def drop_tables(self) -> None:
        """Drop all tables (use with caution!)."""
        logger.warning("Dropping all database tables")
        Base.metadata.drop_all(self.engine)
        logger.info("Database tables dropped")

    def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return False

    def close(self) -> None:
        """Close the database engine."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database connection closed")


# Global database instance (lazy initialization)
_database: Optional[Database] = None


def get_database(
    connection_string: Optional[str] = None,
    echo: bool = False,
) -> Database:
    """
    Get the global database instance.
    
    Args:
        connection_string: Optional override for connection string
        echo: Whether to echo SQL (for debugging)
        
    Returns:
        Database instance
    """
    global _database
    
    if _database is None:
        _database = Database(connection_string=connection_string, echo=echo)
    
    return _database


def reset_database() -> None:
    """Reset the global database instance."""
    global _database
    if _database:
        _database.close()
    _database = None
