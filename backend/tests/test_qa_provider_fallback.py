import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.main import app
from app.models import QAAnswer, User, UserRole
from app.services import qa as qa_service


class FakeSession:
    def __init__(self) -> None:
        self.objects = []
        self.next_id = 1000

    def add(self, obj) -> None:
        self.objects.append(obj)

    def flush(self) -> None:
        for obj in self.objects:
            if hasattr(obj, "id") and getattr(obj, "id", None) is None:
                obj.id = self.next_id
                self.next_id += 1

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def refresh(self, _obj) -> None:
        pass


def test_groq_rate_limit_falls_back_to_local_extractive(monkeypatch):
    fake_db = FakeSession()
    fake_user = User(
        id=2,
        email="admin@cmpdi.local",
        hashed_password="unused",
        full_name="Demo Admin",
        role=UserRole.admin,
        is_active=True,
    )
    citations = [
        {
            "chunk_id": 101,
            "document_id": 19,
            "filename": "monthly_production_report_aug_2026.txt",
            "chunk_index": 0,
            "page_number": None,
            "source_reference": "monthly_production_report_aug_2026.txt",
            "distance": 0.1,
            "similarity": 0.9,
            "text_snippet": (
                "The August 2026 coal production target was 1.28 MT. "
                "Actual coal production for August 2026 was 1.16 MT."
            ),
        }
    ]

    monkeypatch.setattr(settings, "qa_mode", "llm")
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(qa_service, "retrieve_relevant_chunks", lambda *_args: citations)

    def raise_rate_limit(_question, _citations):
        raise RuntimeError("429 rate limit")

    monkeypatch.setattr(qa_service, "generate_groq_answer", raise_rate_limit)

    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        response = TestClient(app).post(
            "/qa/ask",
            json={"question": "What was the August 2026 production target versus actual production?", "limit": 5},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "local_extractive"
    assert payload["citations"] == citations
    assert "1.28 MT" in payload["answer"]
    assert "1.16 MT" in payload["answer"]
    assert any(isinstance(obj, QAAnswer) for obj in fake_db.objects)
