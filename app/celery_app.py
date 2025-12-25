"""
Celery configuration for background task processing.
Handles long-running scraping operations asynchronously.
"""
from celery import Celery
from app.config import settings

# Initialize Celery app
celery_app = Celery("proven_demand")

# Configure Celery
celery_app.conf.update(
    broker=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND_URL,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes hard limit
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit
)

# Import tasks to register them
from app.services import tasks  # noqa: F401, E402
