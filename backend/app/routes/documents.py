from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.db import get_db
from app.models import Document, DocumentStatus, Job, JobStatus, User, UserRole
from app.services.audit import write_audit_log
from app.services.storage import upload_file
from app.tasks.ingestion import ingest_document

router = APIRouter()


@router.post("/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst)),
) -> dict:
    filename = Path(file.filename or "upload.bin").name
    suffix = Path(filename).suffix.lower().lstrip(".") or "unknown"
    object_path = f"documents/{uuid4()}/{filename}"

    try:
        file_size = upload_file(file, object_path)
        document = Document(
            original_filename=filename,
            object_path=object_path,
            file_type=suffix,
            mime_type=file.content_type,
            file_size_bytes=file_size,
            processing_status=DocumentStatus.uploaded,
            uploaded_by_user_id=current_user.id,
        )
        db.add(document)
        db.flush()

        job = Job(document_id=document.id, job_type="document_ingestion", status=JobStatus.queued)
        db.add(job)
        db.flush()

        document.processing_status = DocumentStatus.queued
        document.updated_at = datetime.now(timezone.utc)
        write_audit_log(
            db,
            action="document_upload_requested",
            entity_type="document",
            entity_id=document.id,
            user_id=current_user.id,
            metadata={"filename": filename, "object_path": object_path, "job_id": job.id},
        )
        db.commit()
        db.refresh(document)
        db.refresh(job)

        task = ingest_document.delay(document.id, job.id)
        job.celery_task_id = task.id
        db.commit()
        db.refresh(document)
        db.refresh(job)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    return {
        "document_id": document.id,
        "job_id": job.id,
        "celery_task_id": job.celery_task_id,
        "filename": document.original_filename,
        "processing_status": document.processing_status.value,
    }


@router.get("/documents")
def list_documents(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> list[dict]:
    documents = db.scalars(select(Document).order_by(Document.created_at.desc())).all()
    return [_serialize_document(document) for document in documents]


@router.get("/documents/{document_id}")
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> dict:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _serialize_document(document)


@router.get("/documents/{document_id}/chunks")
def list_document_chunks(
    document_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst, UserRole.viewer)),
) -> list[dict]:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    rows = db.execute(
        text(
            """
            SELECT id, document_id, chunk_index, page_number, source_reference,
                   embedding IS NOT NULL AS embedding_exists,
                   LEFT(text, 500) AS text
            FROM chunks
            WHERE document_id = :document_id
            ORDER BY chunk_index
            """
        ),
        {"document_id": document_id},
    ).mappings().all()
    return [dict(row) for row in rows]


@router.get("/jobs/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(UserRole.admin, UserRole.analyst)),
) -> dict:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _serialize_job(job)


def _serialize_document(document: Document) -> dict:
    return {
        "id": document.id,
        "filename": document.original_filename,
        "object_path": document.object_path,
        "file_type": document.file_type,
        "mime_type": document.mime_type,
        "file_size_bytes": document.file_size_bytes,
        "processing_status": document.processing_status.value,
        "processing_error": document.processing_error,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def _serialize_job(job: Job) -> dict:
    return {
        "id": job.id,
        "document_id": job.document_id,
        "celery_task_id": job.celery_task_id,
        "job_type": job.job_type,
        "status": job.status.value,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }
