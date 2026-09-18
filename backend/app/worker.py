from celery import Celery

from app.config import settings

celery_app = Celery(
    "cmpdi_reporting_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(task_track_started=True)


@celery_app.task(name="health.ping")
def ping() -> str:
    return "pong"


import app.tasks.ingestion  # noqa: E402,F401
import app.tasks.embeddings  # noqa: E402,F401
