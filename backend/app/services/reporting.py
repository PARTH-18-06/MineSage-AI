import re
from collections import OrderedDict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Document, DocumentStatus, Report, ReportStatus, User


CONTEXTUAL_FIGURE_KEYWORDS = ("bh-", "borehole", "reserve", "production target", "coal seam", "seam depth", "depth")
MEASUREMENT_PATTERN = re.compile(r"\b(?:BH-\d+|\d+(?:\.\d+)?\s*(?:MT|MTPA|meters?|m)\b)", re.IGNORECASE)


def generate_report(
    db: Session,
    title: str,
    document_ids: list[int] | None,
    report_type: str,
    user: User,
) -> Report:
    documents = _get_source_documents(db, document_ids)
    chunks = db.scalars(
        select(Chunk)
        .where(Chunk.document_id.in_([document.id for document in documents]))
        .order_by(Chunk.document_id, Chunk.chunk_index)
    ).all()
    if not chunks:
        raise ValueError("No chunks found for selected processed documents")

    content = build_local_report(title, report_type, documents, chunks)
    report = Report(
        title=title,
        source_document_ids=[document.id for document in documents],
        generated_content=content,
        created_by_user_id=user.id,
        status=ReportStatus.draft,
        version_number=1,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(report)
    db.flush()
    return report


def _get_source_documents(db: Session, document_ids: list[int] | None) -> list[Document]:
    statement = select(Document).where(Document.processing_status == DocumentStatus.processed)
    if document_ids:
        statement = statement.where(Document.id.in_(document_ids))
    documents = db.scalars(statement.order_by(Document.id)).all()

    if document_ids:
        found_ids = {document.id for document in documents}
        missing_ids = [document_id for document_id in document_ids if document_id not in found_ids]
        if missing_ids:
            raise ValueError(f"No processed documents found for ids: {missing_ids}")
    if not documents:
        raise ValueError("No processed documents are available for report generation")
    return documents


def build_local_report(title: str, report_type: str, documents: list[Document], chunks: list[Chunk]) -> str:
    combined_text = "\n".join(chunk.text for chunk in chunks)
    snippets = _top_snippets(chunks)
    figures = _extract_figures(combined_text)

    source_lines = [
        f"- Document {document.id}: {document.original_filename} ({document.file_type}, status={document.processing_status.value})"
        for document in documents
    ]
    findings = snippets or ["Available chunks contain readable extracted text, but no strong geological keywords were detected."]
    figure_lines = figures or ["No explicit production, reserve, borehole, seam, or depth figures were detected in the selected chunks."]

    return "\n".join(
        [
            f"# {title}",
            "",
            "## Executive Summary",
            f"Generated a {report_type} report from {len(documents)} processed document(s) and {len(chunks)} text chunk(s). "
            f"The report is grounded only in extracted chunk text currently stored in PostgreSQL.",
            "",
            "## Key Geological/Mining Findings",
            *[f"- {finding}" for finding in findings],
            "",
            "## Production/Reserve Figures",
            *[f"- {figure}" for figure in figure_lines],
            "",
            "## Source Documents",
            *source_lines,
            "",
            "## Data Quality Notes",
            "- This report uses local extraction heuristics over stored chunks; no unsupported documents or missing text were used.",
            "- Figures are extracted from explicit terms such as MT, MTPA, meters, boreholes, seam, depth, reserve, and production target.",
            "- Citations are represented by source document ids and original filenames in the Source Documents section.",
        ]
    )


def _top_snippets(chunks: list[Chunk], limit: int = 5) -> list[str]:
    keywords = ("coal", "mine", "mining", "geological", "production", "reserve", "borehole", "seam", "depth", "overburden")
    scored: list[tuple[int, str]] = []
    for chunk in chunks:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", chunk.text):
            sentence = sentence.strip()
            if not sentence:
                continue
            score = sum(1 for keyword in keywords if keyword in sentence.lower())
            if score:
                scored.append((score, sentence))

    scored.sort(key=lambda item: item[0], reverse=True)
    unique = OrderedDict()
    for _score, sentence in scored:
        unique.setdefault(sentence, None)
        if len(unique) >= limit:
            break
    return list(unique.keys())


def _extract_figures(text: str, limit: int = 12) -> list[str]:
    figures = OrderedDict()
    for line in re.split(r"\n+|(?<=[.!?])\s+", text):
        value = re.sub(r"\s+", " ", line).strip(" .,:;")
        if value and any(keyword in value.lower() for keyword in CONTEXTUAL_FIGURE_KEYWORDS):
            figures.setdefault(value, None)
        if len(figures) >= limit:
            return list(figures.keys())

    for match in MEASUREMENT_PATTERN.finditer(text):
        value = re.sub(r"\s+", " ", match.group(0)).strip(" .,:;")
        if value:
            figures.setdefault(value, None)
        if len(figures) >= limit:
            break
    return list(figures.keys())
