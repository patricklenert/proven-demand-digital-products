"""
Database connection and session management using SQLModel.
"""
import time
import logging
from typing import Generator
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, create_engine, SQLModel
from app.config import settings


logger = logging.getLogger(__name__)

# Create database engine
engine = create_engine(
    settings.database_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,  # Verify connections before using
)

# Create SessionLocal for background tasks
SessionLocal = lambda: Session(engine)


def init_db() -> None:
    """
    Initialize database by creating all tables.
    Called on application startup.
    Includes retry logic for Docker Compose startup.
    """
    max_retries = 5
    retry_interval = 5
    
    for i in range(max_retries):
        try:
            SQLModel.metadata.create_all(engine)
            logger.info("Database initialized successfully")
            return
        except OperationalError as e:
            if i == max_retries - 1:
                logger.error(f"Failed to connect to database after {max_retries} attempts")
                raise e
            logger.warning(f"Database connection failed (attempt {i+1}/{max_retries}). Retrying in {retry_interval}s...")
            time.sleep(retry_interval)


def get_session() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI routes to get database session.
    Ensures session is properly closed after use.
    """
    with Session(engine) as session:
        yield session
