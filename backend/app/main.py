from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.routes.auth import router as auth_router
from app.routes.analytics import router as analytics_router
from app.routes.documents import router as documents_router
from app.routes.qa import router as qa_router
from app.routes.reports import router as reports_router
from app.routes.search import router as search_router
from app.services import get_minio_client, get_redis_client

app = FastAPI(title="CMPDI/CIL AI Reporting API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(analytics_router)
app.include_router(documents_router)
app.include_router(qa_router)
app.include_router(reports_router)
app.include_router(search_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "cmpdi-reporting-api"}


@app.get("/health/db")
def health_db() -> dict[str, bool | str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        vector_available = connection.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        ).scalar_one()

    return {"status": "ok", "database": "connected", "pgvector": bool(vector_available)}


@app.get("/health/redis")
def health_redis() -> dict[str, str]:
    redis_client = get_redis_client()
    pong = redis_client.ping()
    return {"status": "ok", "redis": "connected", "response": str(pong)}


@app.get("/health/minio")
def health_minio() -> dict[str, bool | str]:
    minio_client = get_minio_client()
    minio_client.head_bucket(Bucket=settings.minio_bucket)
    return {"status": "ok", "minio": "connected", "bucket": settings.minio_bucket}
