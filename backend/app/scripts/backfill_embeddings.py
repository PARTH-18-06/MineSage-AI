from sqlalchemy import text

from app.db import SessionLocal
from app.services.embeddings import embed_texts, to_vector_literal


def main() -> None:
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT id, text
                FROM chunks
                WHERE embedding IS NULL
                ORDER BY id
                """
            )
        ).mappings().all()

        vectors = embed_texts([row["text"] for row in rows])
        for row, vector in zip(rows, vectors, strict=True):
            db.execute(
                text("UPDATE chunks SET embedding = CAST(:embedding AS vector) WHERE id = :chunk_id"),
                {"embedding": to_vector_literal(vector), "chunk_id": row["id"]},
            )

        db.commit()
        print(f"chunks found without embeddings: {len(rows)}")
        print(f"chunks embedded: {len(rows)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
