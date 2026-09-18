from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Report, ReportStatus, User
from app.services.audit import write_audit_log


def submit_report_for_review(db: Session, report: Report, user: User) -> Report:
    if _status_value(report) != ReportStatus.draft.value:
        raise ValueError("Only draft reports can be submitted for review")

    now = _utcnow()
    report.status = ReportStatus.in_review
    report.submitted_for_review_at = now
    report.submitted_for_review_by_user_id = user.id
    report.updated_at = now
    write_audit_log(
        db,
        action="report_submitted_for_review",
        entity_type="report",
        entity_id=report.id,
        user_id=user.id,
        metadata={"status": ReportStatus.in_review.value, "version_number": report.version_number},
    )
    return report


def approve_report(db: Session, report: Report, user: User, approval_note: str | None = None) -> Report:
    if _status_value(report) != ReportStatus.in_review.value:
        raise ValueError("Only reports in review can be approved")

    now = _utcnow()
    report.status = ReportStatus.approved
    report.approved_at = now
    report.approved_by_user_id = user.id
    report.approval_note = approval_note
    report.updated_at = now
    write_audit_log(
        db,
        action="report_approved",
        entity_type="report",
        entity_id=report.id,
        user_id=user.id,
        metadata={"status": ReportStatus.approved.value, "version_number": report.version_number},
    )

    if report.parent_report_id is not None:
        parent = db.get(Report, report.parent_report_id)
        if parent is not None and _status_value(parent) == ReportStatus.approved.value:
            parent.status = ReportStatus.superseded
            parent.updated_at = now
            write_audit_log(
                db,
                action="report_superseded",
                entity_type="report",
                entity_id=parent.id,
                user_id=user.id,
                metadata={"superseded_by_report_id": report.id, "version_number": parent.version_number},
            )

    return report


def create_report_revision(db: Session, report: Report, user: User) -> Report:
    if _status_value(report) != ReportStatus.approved.value:
        raise ValueError("Only approved reports can be revised")

    revision = Report(
        title=report.title,
        source_document_ids=list(report.source_document_ids or []),
        generated_content=report.generated_content,
        created_by_user_id=user.id,
        parent_report_id=report.id,
        version_number=(report.version_number or 1) + 1,
        status=ReportStatus.draft,
        updated_at=_utcnow(),
    )
    db.add(revision)
    db.flush()
    write_audit_log(
        db,
        action="report_revision_created",
        entity_type="report",
        entity_id=revision.id,
        user_id=user.id,
        metadata={
            "parent_report_id": report.id,
            "version_number": revision.version_number,
            "source_document_ids": revision.source_document_ids,
        },
    )
    return revision


def get_report_versions(db: Session, report: Report) -> list[Report]:
    reports = db.scalars(select(Report).order_by(Report.version_number.asc(), Report.id.asc())).all()
    by_id = {item.id: item for item in reports}
    root = report
    seen: set[int] = set()
    while root.parent_report_id is not None and root.parent_report_id in by_id and root.parent_report_id not in seen:
        seen.add(root.id)
        root = by_id[root.parent_report_id]

    def belongs_to_lineage(candidate: Report) -> bool:
        current = candidate
        visited: set[int] = set()
        while current.parent_report_id is not None and current.parent_report_id in by_id and current.id not in visited:
            visited.add(current.id)
            current = by_id[current.parent_report_id]
        return current.id == root.id

    return [item for item in reports if belongs_to_lineage(item)]


def _status_value(report: Report) -> str:
    status = report.status
    return status.value if isinstance(status, ReportStatus) else str(status)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
