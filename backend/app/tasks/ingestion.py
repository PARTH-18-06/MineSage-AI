from datetime import datetime, timezone

from sqlalchemy import delete

from app.db import SessionLocal
from app.models import Chunk, Document, DocumentStatus, Job, JobStatus
from app.services.audit import write_audit_log
from app.services.chunking import split_sections
from app.services.extraction import extract_text_sections
from app.services.storage import download_file
from app.worker import celery_app


@celery_app.task(name="documents.ingest")
def ingest_document(document_id: int, job_id: int) -> dict[str, int | str]:
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        job = db.get(Job, job_id)
        if document is None or job is None:
            raise ValueError(f"Missing document/job for document_id={document_id}, job_id={job_id}")

        document.processing_status = DocumentStatus.processing
        document.processing_error = None
        document.updated_at = datetime.now(timezone.utc)
        job.status = JobStatus.running
        job.error_message = None
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        content = download_file(document.object_path)
        sections = extract_text_sections(document.original_filename, document.mime_type, content)
        chunks = split_sections(sections)
        if not chunks:
            raise ValueError(f"No text chunks created for '{document.original_filename}'")

        db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        for index, chunk in enumerate(chunks):
            db.add(
                Chunk(
                    document_id=document_id,
                    chunk_index=index,
                    text=chunk.text,
                    page_number=chunk.page_number,
                    source_reference=chunk.source_reference,
                )
            )

        document.processing_status = DocumentStatus.processed
        document.processing_error = None
        document.updated_at = datetime.now(timezone.utc)
        job.status = JobStatus.completed
        job.error_message = None
        job.finished_at = datetime.now(timezone.utc)
        write_audit_log(
            db,
            action="document_ingestion_completed",
            entity_type="document",
            entity_id=document.id,
            user_id=document.uploaded_by_user_id,
            metadata={"job_id": job.id, "chunks": len(chunks)},
        )
        db.commit()
        from app.tasks.embeddings import embed_document

        embed_document.delay(document_id)
        return {"status": "completed", "document_id": document_id, "job_id": job_id, "chunks": len(chunks)}
    except Exception as exc:
        db.rollback()
        message = str(exc)
        document = db.get(Document, document_id)
        job = db.get(Job, job_id)
        if document is not None:
            document.processing_status = DocumentStatus.failed
            document.processing_error = message
            document.updated_at = datetime.now(timezone.utc)
        if job is not None:
            job.status = JobStatus.failed
            job.error_message = message
            job.finished_at = datetime.now(timezone.utc)
        write_audit_log(
            db,
            action="document_ingestion_failed",
            entity_type="document",
            entity_id=document_id,
            user_id=document.uploaded_by_user_id if document is not None else None,
            metadata={"job_id": job_id, "error_message": message},
        )
        db.commit()
        raise
    finally:
        db.close()
