from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.db import get_db
from app.models import QAAnswer, User, UserRole
from app.services.audit import write_audit_log
from app.services.qa import answer_question

router = APIRouter(prefix="/qa", tags=["qa"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1, le=10)


@router.post("/ask")
def ask_question(
    payload: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> dict:
    try:
        return answer_question(db, payload.question, payload.limit, current_user)
    except Exception as exc:
        db.rollback()
        write_audit_log(
            db,
            action="qa_answer_failed",
            entity_type="qa",
            user_id=current_user.id,
            metadata={"question": payload.question, "error_message": str(exc)},
        )
        db.commit()
        raise HTTPException(status_code=500, detail=f"Q&A failed: {exc}") from exc


@router.get("/history")
def list_history(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> list[dict]:
    statement = select(QAAnswer)
    if current_user.role != UserRole.admin:
        statement = statement.where(QAAnswer.user_id == current_user.id)
    answers = db.scalars(statement.order_by(QAAnswer.created_at.desc()).limit(limit)).all()
    return [_serialize_answer(answer) for answer in answers]


@router.get("/history/{answer_id}")
def get_history_item(
    answer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> dict:
    answer = db.get(QAAnswer, answer_id)
    if answer is None:
        raise HTTPException(status_code=404, detail="Q&A answer not found")
    if current_user.role != UserRole.admin and answer.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Q&A answer not found")
    return _serialize_answer(answer)


def _serialize_answer(answer: QAAnswer) -> dict:
    return {
        "id": answer.id,
        "user_id": answer.user_id,
        "question": answer.question,
        "answer": answer.answer,
        "mode": answer.mode,
        "citations": answer.citations,
        "created_at": answer.created_at,
    }
