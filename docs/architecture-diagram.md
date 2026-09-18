# SIH CMPDI/CIL AI Reporting Platform Architecture

This document explains the implemented demo architecture represented in `architecture-diagram.svg` and `architecture-diagram.png`.

## Legend

- Solid boundary: implemented Docker Compose demo environment.
- Dashed production-extension box: future deployment options, not implemented in the current demo.
- Blue arrows: document upload, ingestion, extraction, chunking, and embedding flow.
- Teal arrows: semantic search and Q&A retrieval flow.
- Slate arrows: reporting, governance, analytics, and supporting data movement.

## Implemented In Demo

The Docker Compose demo environment contains these services: `frontend`, `api`, `worker`, `postgres` with `pgvector`, `redis`, and `minio`.

The implemented application includes:

- React + Tailwind frontend screens for Dashboard, Documents, Intelligence/Q&A, Reports, Search, and Analytics.
- FastAPI REST API with JWT authentication and RBAC for `admin`, `analyst`, and `viewer`.
- MinIO S3-compatible storage for uploaded documents.
- PostgreSQL metadata, job tracking, report governance, Q&A history, audit logs, and chunk embeddings through `pgvector`.
- Redis as the Celery broker.
- Celery worker for asynchronous document ingestion and embedding.
- PyMuPDF digital-PDF extraction, Tesseract OCR for scanned PDFs/images, and DOCX/XLSX/CSV/TXT extraction.
- Semantic search, citation-backed Q&A, default local extractive Q&A, optional Groq LLM mode using `openai/gpt-oss-20b`, and automatic fallback to local extractive mode on provider failure or rate limit.
- Automated reports, report lifecycle governance, approval/version history, topic modeling, word cloud, Data Quality metrics, and Workflow Metrics.

## Main Flows

1. Upload and ingestion: Users upload documents through the React frontend. FastAPI stores the file in MinIO, records document and job metadata in PostgreSQL, sends the job through Redis, and the Celery worker extracts text, OCRs scanned content when needed, chunks the text, and stores embeddings in PostgreSQL/pgvector.

2. Search and Q&A: Search or Q&A requests go through FastAPI to pgvector retrieval. The system answers with citations using local extractive Q&A by default. When LLM mode is enabled, Groq is called through the OpenAI-compatible API using `openai/gpt-oss-20b`; provider errors or rate limits fall back to local extractive mode with citations.

3. Report generation and governance: Report generation uses selected source documents and stored chunks. Generated reports are drafts, can be submitted for review by analyst/admin users, approved only by admins, and revised through version history. Report lifecycle actions are written to audit logs.

4. Analytics and evaluation: Analytics reads chunks, reports, validation fixtures, and benchmark artifacts to produce dashboard metrics, topics, word cloud, Data Quality evaluation, and controlled Workflow Metrics.

## Production Extension

The diagram includes a dashed Production Extension note for possible future deployment on AWS EC2, RDS, and S3, plus a self-hosted LLM option. These are extension options only and are not presented as currently implemented in the demo.
