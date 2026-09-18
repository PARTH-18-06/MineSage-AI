import re
from collections import Counter

from sqlalchemy import text
from sqlalchemy.orm import Session


STOPWORDS = {
    "and",
    "are",
    "but",
    "for",
    "from",
    "has",
    "have",
    "into",
    "not",
    "that",
    "the",
    "this",
    "with",
    "within",
    "without",
    "document",
    "documents",
    "sample",
    "stored",
    "text",
    "file",
    "api",
}


def dashboard_summary(db: Session) -> dict:
    document_counts = db.execute(
        text(
            """
            SELECT
                COUNT(*) AS total_documents,
                COUNT(*) FILTER (WHERE processing_status = 'processed') AS processed_documents,
                COUNT(*) FILTER (WHERE processing_status = 'failed') AS failed_documents
            FROM documents
            """
        )
    ).mappings().one()
    chunk_counts = db.execute(
        text("SELECT COUNT(*) AS total_chunks, COUNT(embedding) AS chunks_with_embeddings FROM chunks")
    ).mappings().one()
    total_reports = db.execute(text("SELECT COUNT(*) FROM reports")).scalar_one()
    total_qa_answers = db.execute(text("SELECT COUNT(*) FROM qa_answers")).scalar_one()

    return {
        "total_documents": document_counts["total_documents"],
        "processed_documents": document_counts["processed_documents"],
        "failed_documents": document_counts["failed_documents"],
        "total_chunks": chunk_counts["total_chunks"],
        "chunks_with_embeddings": chunk_counts["chunks_with_embeddings"],
        "total_reports": total_reports,
        "total_qa_answers": total_qa_answers,
        "documents_by_file_type": _group_counts(db, "file_type"),
        "documents_by_processing_status": _group_counts(db, "processing_status"),
    }


def top_topics(db: Session, limit: int) -> list[dict]:
    texts = _processed_chunk_texts(db)
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=max(limit * 5, 25))
        matrix = vectorizer.fit_transform(texts)
        scores = matrix.sum(axis=0).A1
        terms = vectorizer.get_feature_names_out()
        ranked = sorted(zip(terms, scores, strict=True), key=lambda item: item[1], reverse=True)[:limit]
        return [{"topic": term, "score": round(float(score), 4)} for term, score in ranked if score > 0]
    except Exception:
        return [{"topic": text, "score": value} for text, value in word_frequencies(db, limit)]


def wordcloud_terms(db: Session, limit: int) -> list[dict]:
    return [{"text": term, "value": value} for term, value in word_frequencies(db, limit)]


def word_frequencies(db: Session, limit: int) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for text_value in _processed_chunk_texts(db):
        for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text_value.lower()):
            if word not in STOPWORDS:
                counter[word] += 1
    return counter.most_common(limit)


def _group_counts(db: Session, column_name: str) -> dict:
    rows = db.execute(
        text(
            f"""
            SELECT {column_name}::text AS key, COUNT(*) AS value
            FROM documents
            GROUP BY {column_name}
            ORDER BY {column_name}
            """
        )
    ).mappings().all()
    return {row["key"]: row["value"] for row in rows}


def _processed_chunk_texts(db: Session) -> list[str]:
    rows = db.execute(
        text(
            """
            SELECT chunks.text
            FROM chunks
            JOIN documents ON documents.id = chunks.document_id
            WHERE documents.processing_status = 'processed'
            """
        )
    ).scalars().all()
    return [row for row in rows if row.strip()]
