import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import get_current_user
from app.db import get_db
from app.main import app
from app.models import AuditLog, Report, ReportStatus, User, UserRole
from app.services.report_governance import approve_report, create_report_revision, submit_report_for_review


class FakeDb:
    def __init__(self, reports=None):
        self.reports = {report.id: report for report in reports or []}
        self.added = []
        self.next_report_id = max(self.reports.keys(), default=100) + 1

    def add(self, item):
        if isinstance(item, Report) and item.id is None:
            item.id = self.next_report_id
            self.next_report_id += 1
            self.reports[item.id] = item
        self.added.append(item)

    def flush(self):
        return None

    def get(self, model, item_id):
        if model is Report:
            return self.reports.get(item_id)
        return None


def make_user(role=UserRole.admin, user_id=1):
    return User(id=user_id, email=f"{role.value}@cmpdi.local", hashed_password="hash", role=role, is_active=True)


def make_report(status=ReportStatus.draft, report_id=11, version=1):
    return Report(
        id=report_id,
        title="CMPDI/CIL Demo Geological and Production Intelligence Report",
        source_document_ids=[18, 19, 20, 22, 24, 25, 26, 28],
        generated_content="Existing demo report content",
        created_by_user_id=1,
        status=status,
        version_number=version,
    )


def audit_actions(db):
    return [item.action for item in db.added if isinstance(item, AuditLog)]


def test_draft_to_review_to_approved_happy_path_creates_audit_events():
    db = FakeDb()
    admin = make_user(UserRole.admin)
    report = make_report()

    submit_report_for_review(db, report, admin)
    approve_report(db, report, admin, "Approved for final demo")

    assert report.status == ReportStatus.approved
    assert report.submitted_for_review_by_user_id == admin.id
    assert report.approved_by_user_id == admin.id
    assert report.approval_note == "Approved for final demo"
    assert audit_actions(db) == ["report_submitted_for_review", "report_approved"]


def test_analyst_cannot_approve_report():
    report = make_report(ReportStatus.in_review)
    response = call_with_user("post", "/reports/11/approve", make_user(UserRole.analyst, 2), FakeDb([report]), json={})

    assert response.status_code == 403


def test_viewer_receives_403_for_workflow_mutations():
    viewer = make_user(UserRole.viewer, 3)

    for path in ["/reports/11/submit-review", "/reports/11/approve", "/reports/11/create-revision"]:
        response = call_with_user("post", path, viewer, FakeDb([make_report()]), json={})
        assert response.status_code == 403


def test_approved_report_cannot_be_submitted_again():
    db = FakeDb()
    report = make_report(ReportStatus.approved)

    try:
        submit_report_for_review(db, report, make_user(UserRole.admin))
    except ValueError as exc:
        assert "Only draft reports" in str(exc)
    else:
        raise AssertionError("Approved report was allowed to be directly resubmitted")


def test_revision_preserves_parent_version_and_source_provenance():
    db = FakeDb()
    approved = make_report(ReportStatus.approved, report_id=11, version=1)
    admin = make_user(UserRole.admin)

    revision = create_report_revision(db, approved, admin)

    assert revision.parent_report_id == approved.id
    assert revision.version_number == 2
    assert revision.status == ReportStatus.draft
    assert revision.source_document_ids == approved.source_document_ids
    assert approved.status == ReportStatus.approved
    assert "report_revision_created" in audit_actions(db)


def test_approving_revision_supersedes_parent():
    db = FakeDb()
    parent = make_report(ReportStatus.approved, report_id=11, version=1)
    revision = make_report(ReportStatus.in_review, report_id=12, version=2)
    revision.parent_report_id = 11
    db.reports = {11: parent, 12: revision}

    approve_report(db, revision, make_user(UserRole.admin))

    assert revision.status == ReportStatus.approved
    assert parent.status == ReportStatus.superseded
    assert "report_superseded" in audit_actions(db)


def test_existing_report_id_11_remains_readable():
    response = call_with_user("get", "/reports/11", make_user(UserRole.viewer, 4), FakeDb([make_report()]))

    assert response.status_code == 200
    assert response.json()["id"] == 11
    assert response.json()["source_document_ids"] == [18, 19, 20, 22, 24, 25, 26, 28]


def call_with_user(method, path, user, db, **kwargs):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    try:
        return getattr(TestClient(app), method)(path, **kwargs)
    finally:
        app.dependency_overrides.clear()
