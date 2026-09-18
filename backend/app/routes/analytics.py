from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.db import get_db
from app.models import User, UserRole
from app.services.analytics import dashboard_summary, top_topics, wordcloud_terms
from app.services.data_quality import data_quality_report
from app.services.workflow_metrics import workflow_metrics_report

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
def analytics_summary(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> dict:
    return dashboard_summary(db)


@router.get("/topics")
def analytics_topics(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> list[dict]:
    return top_topics(db, limit)


@router.get("/wordcloud")
def analytics_wordcloud(
    limit: int = Query(75, ge=1, le=200),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> list[dict]:
    return wordcloud_terms(db, limit)


@router.get("/data-quality")
def analytics_data_quality(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> dict:
    return data_quality_report(db)


@router.get("/workflow-metrics")
def analytics_workflow_metrics(
    _current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> dict:
    return workflow_metrics_report()
