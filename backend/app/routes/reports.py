from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.db import get_db
from app.models import Report, User, UserRole
from app.services.audit import write_audit_log
from app.services.report_governance import approve_report, create_report_revision, get_report_versions, submit_report_for_review
from app.services.reporting import generate_report

router = APIRouter(prefix="/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    title: str = Field(default="Geological and Mining Summary Report", min_length=1)
    document_ids: list[int] | None = None
    report_type: str = Field(default="geological_summary", min_length=1)


class ApproveReportRequest(BaseModel):
    approval_note: str | None = None


@router.post("/generate")
def generate_report_endpoint(
    payload: GenerateReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst)),
) -> dict:
    try:
        report = generate_report(db, payload.title, payload.document_ids, payload.report_type, current_user)
        write_audit_log(
            db,
            action="report_generated",
            entity_type="report",
            entity_id=report.id,
            user_id=current_user.id,
            metadata={"title": report.title, "report_type": payload.report_type, "document_ids": report.source_document_ids},
        )
        db.commit()
        db.refresh(report)
        return _serialize_report(report)
    except ValueError as exc:
        db.rollback()
        write_audit_log(
            db,
            action="report_generation_failed",
            entity_type="report",
            user_id=current_user.id,
            metadata={"title": payload.title, "report_type": payload.report_type, "document_ids": payload.document_ids or [], "error_message": str(exc)},
        )
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_reports(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> list[dict]:
    reports = db.scalars(select(Report).order_by(Report.created_at.desc())).all()
    return [_serialize_report_summary(report) for report in reports]


@router.get("/{report_id}")
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> dict:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return _serialize_report(report)


@router.post("/{report_id}/submit-review")
def submit_report_for_review_endpoint(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst)),
) -> dict:
    report = _get_report_or_404(db, report_id)
    try:
        submit_report_for_review(db, report, current_user)
        db.commit()
        db.refresh(report)
        return _serialize_report(report)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{report_id}/approve")
def approve_report_endpoint(
    report_id: int,
    payload: ApproveReportRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin)),
) -> dict:
    report = _get_report_or_404(db, report_id)
    try:
        approve_report(db, report, current_user, payload.approval_note if payload else None)
        db.commit()
        db.refresh(report)
        return _serialize_report(report)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{report_id}/create-revision")
def create_report_revision_endpoint(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst)),
) -> dict:
    report = _get_report_or_404(db, report_id)
    try:
        revision = create_report_revision(db, report, current_user)
        db.commit()
        db.refresh(revision)
        return _serialize_report(revision)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{report_id}/versions")
def list_report_versions_endpoint(
    report_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> list[dict]:
    report = _get_report_or_404(db, report_id)
    return [_serialize_report_summary(item) for item in get_report_versions(db, report)]


def _get_report_or_404(db: Session, report_id: int) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def _serialize_report_summary(report: Report) -> dict:
    return {
        "id": report.id,
        "title": report.title,
        "source_document_ids": report.source_document_ids,
        "created_by_user_id": report.created_by_user_id,
        "status": report.status.value if hasattr(report.status, "value") else report.status,
        "version_number": report.version_number,
        "parent_report_id": report.parent_report_id,
        "submitted_for_review_at": report.submitted_for_review_at,
        "submitted_for_review_by_user_id": report.submitted_for_review_by_user_id,
        "approved_at": report.approved_at,
        "approved_by_user_id": report.approved_by_user_id,
        "approval_note": report.approval_note,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
    }


def _serialize_report(report: Report) -> dict:
    data = _serialize_report_summary(report)
    data["generated_content"] = report.generated_content
    return data
