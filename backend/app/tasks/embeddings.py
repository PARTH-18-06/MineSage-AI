from sqlalchemy import text

from app.db import SessionLocal
from app.models import Document
from app.services.audit import write_audit_log
from app.services.embeddings import embed_texts, to_vector_literal
from app.worker import celery_app


@celery_app.task(name="documents.embed")
def embed_document(document_id: int) -> dict[str, int | str]:
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            raise ValueError(f"Document not found: {document_id}")

        rows = db.execute(
            text(
                """
                SELECT id, text
                FROM chunks
                WHERE document_id = :document_id
                  AND embedding IS NULL
                ORDER BY chunk_index
                """
            ),
            {"document_id": document_id},
        ).mappings().all()

        vectors = embed_texts([row["text"] for row in rows])
        for row, vector in zip(rows, vectors, strict=True):
            db.execute(
                text("UPDATE chunks SET embedding = CAST(:embedding AS vector) WHERE id = :chunk_id"),
                {"embedding": to_vector_literal(vector), "chunk_id": row["id"]},
            )

        write_audit_log(
            db,
            action="document_embedding_completed",
            entity_type="document",
            entity_id=document_id,
            user_id=document.uploaded_by_user_id,
            metadata={"chunks": len(rows), "model": "all-MiniLM-L6-v2"},
        )
        db.commit()
        return {"status": "completed", "document_id": document_id, "chunks": len(rows)}
    except Exception as exc:
        db.rollback()
        document = db.get(Document, document_id)
        write_audit_log(
            db,
            action="document_embedding_failed",
            entity_type="document",
            entity_id=document_id,
            user_id=document.uploaded_by_user_id if document is not None else None,
            metadata={"error_message": str(exc)},
        )
        db.commit()
        raise
    finally:
        db.close()
