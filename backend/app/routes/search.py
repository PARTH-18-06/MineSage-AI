from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.db import get_db
from app.models import User, UserRole
from app.services.embeddings import embed_text, to_vector_literal

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/semantic")
def semantic_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=25),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> list[dict]:
    query_vector = to_vector_literal(embed_text(q))
    rows = db.execute(
        text(
            """
            SELECT
                chunks.id AS chunk_id,
                chunks.document_id,
                documents.original_filename AS filename,
                chunks.chunk_index,
                chunks.page_number,
                chunks.source_reference,
                (chunks.embedding <=> CAST(:query_embedding AS vector))::float AS distance,
                (1 - (chunks.embedding <=> CAST(:query_embedding AS vector)))::float AS similarity,
                LEFT(chunks.text, 500) AS text_snippet
            FROM chunks
            JOIN documents ON documents.id = chunks.document_id
            WHERE chunks.embedding IS NOT NULL
            ORDER BY chunks.embedding <=> CAST(:query_embedding AS vector)
            LIMIT :limit
            """
        ),
        {"query_embedding": query_vector, "limit": limit},
    ).mappings().all()
    return [dict(row) for row in rows]
