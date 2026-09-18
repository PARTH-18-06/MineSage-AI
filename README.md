# AI-Powered Geological, Mining and Other Reporting Solution

SIH CMPDI/CIL reporting platform with document ingestion, grounded intelligence,
governed reports, analytics, and reproducible evaluation metrics.

Architecture: [SVG](docs/architecture-diagram.svg) | [PNG](docs/architecture-diagram.png) | [Guide](docs/architecture-diagram.md)

## Final Demo Checklist

Start or rebuild the complete demo without deleting its data volumes:

```powershell
docker compose up --build -d
```

Demo URLs:

- Frontend: `http://127.0.0.1:5173`
- FastAPI: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001`

Demo accounts (passwords are supplied separately through the configured environment):

- `admin@cmpdi.local`
- `analyst@cmpdi.local`
- `viewer@cmpdi.local`

Final verification:

```powershell
docker compose ps
docker compose exec api pytest -q
docker compose exec frontend npm run build
docker compose exec api alembic current
curl.exe -s http://localhost:8000/health
curl.exe -s http://localhost:8000/health/db
curl.exe -s http://localhost:8000/health/redis
curl.exe -s http://localhost:8000/health/minio
```

Implemented in the Docker Compose demo: React/Tailwind frontend, FastAPI with JWT/RBAC,
Celery/Redis ingestion, MinIO storage, PostgreSQL/pgvector retrieval, local extractive
Q&A with optional Groq and automatic fallback, governed reports, analytics, Data Quality,
and Workflow Metrics. Production roadmap items are limited to deployment on AWS
EC2/RDS/S3 and an optional self-hosted LLM; they are not presented as implemented.

## Stack

- FastAPI backend
- PostgreSQL with pgvector
- Redis
- MinIO local S3-compatible object storage
- Celery worker
- Alembic migrations
- Docker Compose

## Run

```bash
docker compose up --build -d
```

The API runs at `http://localhost:8000`.

MinIO console runs at `http://localhost:9001`.

Default local credentials are in `.env`.

If port `8000` is already in use, set `API_HOST_PORT=8001` in `.env` and call the API at `http://localhost:8001`.

## Verification Commands

Run these commands after `docker compose up --build -d`.

```powershell
docker compose ps
curl.exe -s http://localhost:8000/health
curl.exe -s http://localhost:8000/health/db
curl.exe -s http://localhost:8000/health/redis
curl.exe -s http://localhost:8000/health/minio
docker compose exec api alembic current
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT extname FROM pg_extension WHERE extname = 'vector';"
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename IN ('users', 'documents', 'jobs', 'chunks', 'reports', 'audit_logs') ORDER BY tablename;"
docker compose exec worker celery -A app.worker.celery_app inspect ping
docker compose logs --tail=80 worker
```

## Database Schema

The first Alembic migration creates:

- `users`
- `documents`
- `jobs`
- `chunks`
- `reports`
- `audit_logs`

The migrations enable the PostgreSQL `vector` extension and use a `vector(384)` embedding column for `chunks`.

## Day 2: Document Ingestion

The API accepts document uploads, stores the original file in MinIO, creates `documents` and `jobs` rows, and dispatches a Celery task to extract and chunk text.

Supported extraction inputs:

- Digital PDFs with PyMuPDF
- Scanned PDFs via page rendering and Tesseract OCR fallback
- Images with Tesseract OCR
- `.xlsx` files with pandas/openpyxl
- `.docx` files with python-docx
- `.txt` files

### Upload Examples

```powershell
curl.exe -s -F "file=@samples/day2-sample.txt" http://localhost:8000/documents/upload
curl.exe -s -F "file=@samples/day2-sample.pdf" http://localhost:8000/documents/upload
curl.exe -s -F "file=@samples/day2-unsupported.bin" http://localhost:8000/documents/upload
```

### Day 2 Verification Commands

```powershell
docker compose up --build -d
docker compose ps

curl.exe -s http://localhost:8000/health
curl.exe -s http://localhost:8000/health/db
curl.exe -s http://localhost:8000/health/redis
curl.exe -s http://localhost:8000/health/minio

curl.exe -s -F "file=@samples/day2-sample.txt" http://localhost:8000/documents/upload
curl.exe -s -F "file=@samples/day2-sample.pdf" http://localhost:8000/documents/upload
curl.exe -s -F "file=@samples/day2-unsupported.bin" http://localhost:8000/documents/upload

docker compose exec api python -c "import os, boto3; from botocore.config import Config; s3 = boto3.client('s3', endpoint_url=os.environ['MINIO_ENDPOINT'], aws_access_key_id=os.environ['MINIO_ROOT_USER'], aws_secret_access_key=os.environ['MINIO_ROOT_PASSWORD'], config=Config(s3={'addressing_style': 'path'})); print(s3.list_objects_v2(Bucket=os.environ['MINIO_BUCKET'], Prefix='documents/'))"

docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT id, original_filename, object_path, file_type, processing_status, processing_error FROM documents ORDER BY id;"
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT id, document_id, celery_task_id, job_type, status, error_message, started_at, finished_at FROM jobs ORDER BY id;"
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT document_id, chunk_index, page_number, source_reference, LEFT(text, 200) FROM chunks ORDER BY document_id, chunk_index;"

curl.exe -s http://localhost:8000/documents
curl.exe -s http://localhost:8000/documents/1
curl.exe -s http://localhost:8000/jobs/1

docker compose logs worker --tail 80
```

## Day 3: Auth And RBAC

Day 3 adds JWT login, password hashing, seedable demo users, protected document/job APIs, role checks, basic audit logging, and `documents.updated_at` updates during ingestion.

### Seed Users

The default admin comes from `.env`:

```powershell
docker compose exec api python -m app.scripts.seed_admin
```

Create local demo users for role checks:

```powershell
docker compose exec api python -m app.scripts.create_user --email analyst@cmpdi.local --password <password-from-secure-config> --role analyst --full-name "CMPDI Demo Analyst"
docker compose exec api python -m app.scripts.create_user --email viewer@cmpdi.local --password <password-from-secure-config> --role viewer --full-name "CMPDI Demo Viewer"
```

User creation is intentionally not exposed through the public API. Use only `seed_admin` and `create_user` from inside the API container.

### Login

```powershell
$adminLogin = curl.exe -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\":\"admin@cmpdi.local\",\"password\":\"<password-from-secure-config>\"}" | ConvertFrom-Json
$adminToken = $adminLogin.access_token

$analystLogin = curl.exe -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\":\"analyst@cmpdi.local\",\"password\":\"<password-from-secure-config>\"}" | ConvertFrom-Json
$analystToken = $analystLogin.access_token

$viewerLogin = curl.exe -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\":\"viewer@cmpdi.local\",\"password\":\"<password-from-secure-config>\"}" | ConvertFrom-Json
$viewerToken = $viewerLogin.access_token
```

### Authenticated Requests

```powershell
curl.exe -s http://localhost:8000/auth/me -H "Authorization: Bearer $adminToken"
curl.exe -s http://localhost:8000/documents -H "Authorization: Bearer $viewerToken"
curl.exe -s -F "file=@samples/day2-sample.txt" http://localhost:8000/documents/upload -H "Authorization: Bearer $analystToken"
curl.exe -s http://localhost:8000/jobs/1 -H "Authorization: Bearer $adminToken"
```

### Role Verification

```powershell
curl.exe -i -s http://localhost:8000/documents
curl.exe -i -s -F "file=@samples/day2-sample.txt" http://localhost:8000/documents/upload -H "Authorization: Bearer $viewerToken"
curl.exe -i -s http://localhost:8000/jobs/1 -H "Authorization: Bearer $viewerToken"
```

Expected behavior:

- Missing token on protected endpoints returns `401`.
- Viewer can list and view documents.
- Viewer cannot upload documents or view job status and receives `403`.
- Analyst/admin can upload documents and view job status.

### Audit And Timestamp Checks

```powershell
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT id, email, role, is_active FROM users ORDER BY id;"
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT id, user_id, action, entity_type, entity_id, metadata, created_at FROM audit_logs ORDER BY id DESC LIMIT 20;"
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT id, original_filename, processing_status, processing_error, created_at, updated_at FROM documents ORDER BY id DESC LIMIT 10;"
```

## Day 4: Embeddings And Semantic Search

Day 4 adds local sentence-transformers embeddings with `sentence-transformers/all-MiniLM-L6-v2`, pgvector `vector(384)` storage, embedding backfill, automatic embedding after ingestion, protected chunk inspection, and protected semantic search.

The public API still does not create users. Seed users through CLI scripts only:

```powershell
docker compose exec api python -m app.scripts.seed_admin
docker compose exec api python -m app.scripts.create_user --email analyst@cmpdi.local --password <password-from-secure-config> --role analyst --full-name "CMPDI Demo Analyst"
docker compose exec api python -m app.scripts.create_user --email viewer@cmpdi.local --password <password-from-secure-config> --role viewer --full-name "CMPDI Demo Viewer"
```

Run migrations and confirm the current Alembic revision:

```powershell
docker compose exec api alembic upgrade head
docker compose exec api alembic current
```

Confirm the embedding column is `vector(384)`:

```powershell
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT a.atttypid::regtype AS type, a.atttypmod AS typmod, format_type(a.atttypid, a.atttypmod) AS formatted_type FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid WHERE c.relname = 'chunks' AND a.attname = 'embedding';"
```

Backfill existing chunks:

```powershell
docker compose exec api python -m app.scripts.backfill_embeddings
```

Check embedding counts and dimensions:

```powershell
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT COUNT(*) AS total_chunks, COUNT(embedding) AS chunks_with_embeddings FROM chunks;"
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT id, document_id, vector_dims(embedding) AS embedding_dims FROM chunks WHERE embedding IS NOT NULL ORDER BY id DESC LIMIT 5;"
```

Login and use protected retrieval endpoints:

```powershell
$viewerLogin = curl.exe -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\":\"viewer@cmpdi.local\",\"password\":\"<password-from-secure-config>\"}" | ConvertFrom-Json
$viewerToken = $viewerLogin.access_token

curl.exe -i -s "http://localhost:8000/search/semantic?q=coal%20seam%20reserve&limit=5"
curl.exe -s "http://localhost:8000/search/semantic?q=coal%20seam%20reserve&limit=5" -H "Authorization: Bearer $viewerToken"
curl.exe -s http://localhost:8000/documents/1/chunks -H "Authorization: Bearer $viewerToken"
```

Upload a new document as analyst and confirm automatic embedding:

```powershell
$analystLogin = curl.exe -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\":\"analyst@cmpdi.local\",\"password\":\"<password-from-secure-config>\"}" | ConvertFrom-Json
$analystToken = $analystLogin.access_token
$upload = curl.exe -s -X POST http://localhost:8000/documents/upload -H "Authorization: Bearer $analystToken" -F "file=@samples/day2-sample.txt" | ConvertFrom-Json
curl.exe -s http://localhost:8000/jobs/$($upload.job_id) -H "Authorization: Bearer $analystToken"
curl.exe -s http://localhost:8000/documents/$($upload.document_id)/chunks -H "Authorization: Bearer $viewerToken"
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT document_id, COUNT(*) AS chunks, COUNT(embedding) AS chunks_with_embeddings FROM chunks WHERE document_id = $($upload.document_id) GROUP BY document_id;"
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT id, action, entity_type, entity_id, metadata, created_at FROM audit_logs WHERE action IN ('document_embedding_completed', 'document_embedding_failed') ORDER BY id DESC LIMIT 10;"
docker compose logs worker --tail 120
```

## Day 5: Citation-Backed Q&A

Day 5 adds backend Q&A over embedded document chunks. It uses the existing pgvector retrieval layer and returns citations for every answer.

Modes:

- `local_extractive`: default, works without external API keys by extracting concise answer text from retrieved chunks.
- `llm`: optional provider-backed mode. Set `QA_MODE=llm`; `LLM_PROVIDER=groq` uses Groq's OpenAI-compatible API, while `LLM_PROVIDER=gemini` keeps the Gemini path available as a secondary option.

The API always retrieves chunks first and returns the same citation payload. If the selected LLM provider is missing a key, rate limited, or returns an error, the request automatically falls back to `local_extractive` with citations instead of failing the HTTP request.

Optional `.env` values:

```env
QA_MODE=local_extractive
LLM_PROVIDER=groq
GROQ_MODEL=openai/gpt-oss-20b
GROQ_API_KEY=
GEMINI_MODEL=gemini-flash-latest
GEMINI_API_KEY=
```

Run migrations:

```powershell
docker compose exec api alembic upgrade head
docker compose exec api alembic current
```

Login and ask a question:

```powershell
$viewerLogin = curl.exe -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\":\"viewer@cmpdi.local\",\"password\":\"<password-from-secure-config>\"}" | ConvertFrom-Json
$viewerToken = $viewerLogin.access_token

curl.exe -s -X POST http://localhost:8000/qa/ask -H "Authorization: Bearer $viewerToken" -H "Content-Type: application/json" -d "{\"question\":\"What production target or coal seam information is available?\",\"limit\":5}"
```

Q&A history:

```powershell
curl.exe -s http://localhost:8000/qa/history -H "Authorization: Bearer $viewerToken"
curl.exe -s http://localhost:8000/qa/history/<answer_id> -H "Authorization: Bearer $viewerToken"
```

Verify protected access:

```powershell
curl.exe -i -s -X POST http://localhost:8000/qa/ask -H "Content-Type: application/json" -d "{\"question\":\"What production target or coal seam information is available?\",\"limit\":5}"
```

Verify semantic search still works:

```powershell
curl.exe -s "http://localhost:8000/search/semantic?q=coal%20seam%20reserve&limit=5" -H "Authorization: Bearer $viewerToken"
```

Verify saved Q&A rows and audit logs:

```powershell
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT id, user_id, mode, LEFT(question, 120) AS question, LEFT(answer, 200) AS answer, json_array_length(citations) AS citation_count, created_at FROM qa_answers ORDER BY id DESC LIMIT 10;"
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT id, action, entity_type, entity_id, metadata, created_at FROM audit_logs WHERE action IN ('qa_question_asked', 'qa_answer_generated', 'qa_answer_failed') ORDER BY id DESC LIMIT 20;"
```

Optional LLM verification when a real provider key is configured:

```powershell
docker compose exec -e QA_MODE=llm api python -c "from app.config import settings; print('QA_MODE:', settings.qa_mode); print('LLM_PROVIDER:', settings.llm_provider); print('GROQ_API_KEY present:', bool(settings.groq_api_key)); print('GROQ_MODEL:', settings.groq_model)"
docker compose exec -e QA_MODE=llm api python -m app.scripts.ask_qa_once "What production target or coal seam information is available?"
```

## Day 6: Reports And Analytics

Day 6 adds backend report generation from processed document chunks plus lightweight analytics endpoints. It does not add frontend, topic modeling pipelines, or new RAG features.

Report generation is protected:

- `POST /reports/generate`: admin or analyst only
- `GET /reports`: viewer, analyst, or admin
- `GET /reports/{report_id}`: viewer, analyst, or admin

Analytics endpoints are protected for viewer, analyst, and admin:

- `GET /analytics/summary`
- `GET /analytics/topics?limit=10`
- `GET /analytics/wordcloud?limit=75`

### Day 6 Verification Commands

Start the stack:

```powershell
docker compose up --build -d
docker compose ps
```

Verify Day 1 health checks:

```powershell
curl.exe -s http://localhost:8000/health
curl.exe -s http://localhost:8000/health/db
curl.exe -s http://localhost:8000/health/redis
curl.exe -s http://localhost:8000/health/minio
```

Login as analyst and viewer:

```powershell
$analystLogin = curl.exe -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\":\"analyst@cmpdi.local\",\"password\":\"<password-from-secure-config>\"}" | ConvertFrom-Json
$analystToken = $analystLogin.access_token

$viewerLogin = curl.exe -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\":\"viewer@cmpdi.local\",\"password\":\"<password-from-secure-config>\"}" | ConvertFrom-Json
$viewerToken = $viewerLogin.access_token

curl.exe -s http://localhost:8000/auth/me -H "Authorization: Bearer $analystToken"
```

Verify Day 4 semantic search and Day 5 Q&A still work:

```powershell
curl.exe -s "http://localhost:8000/search/semantic?q=coal%20seam%20reserve&limit=3" -H "Authorization: Bearer $viewerToken"
curl.exe -s -X POST http://localhost:8000/qa/ask -H "Authorization: Bearer $viewerToken" -H "Content-Type: application/json" -d "{\"question\":\"What production target or coal seam information is available?\",\"limit\":3}"
```

Generate and read a report:

```powershell
$report = curl.exe -s -X POST http://localhost:8000/reports/generate -H "Authorization: Bearer $analystToken" -H "Content-Type: application/json" -d "{\"title\":\"Geological and Mining Summary Report\",\"report_type\":\"geological_summary\"}" | ConvertFrom-Json
$report
$reportId = $report.id

curl.exe -s http://localhost:8000/reports -H "Authorization: Bearer $viewerToken"
curl.exe -s http://localhost:8000/reports/$reportId -H "Authorization: Bearer $viewerToken"
```

Verify report access control:

```powershell
curl.exe -i -s -X POST http://localhost:8000/reports/generate -H "Content-Type: application/json" -d "{\"title\":\"Unauth Report\",\"report_type\":\"geological_summary\"}"
curl.exe -i -s -X POST http://localhost:8000/reports/generate -H "Authorization: Bearer $viewerToken" -H "Content-Type: application/json" -d "{\"title\":\"Viewer Report\",\"report_type\":\"geological_summary\"}"
curl.exe -i -s http://localhost:8000/reports -H "Authorization: Bearer $viewerToken"
curl.exe -i -s http://localhost:8000/reports/$reportId -H "Authorization: Bearer $viewerToken"
```

Verify report failure audit path:

```powershell
curl.exe -i -s -X POST http://localhost:8000/reports/generate -H "Authorization: Bearer $analystToken" -H "Content-Type: application/json" -d "{\"title\":\"Missing Source Report\",\"document_ids\":[999999],\"report_type\":\"geological_summary\"}"
```

Verify analytics:

```powershell
curl.exe -s http://localhost:8000/analytics/summary -H "Authorization: Bearer $viewerToken"
curl.exe -s "http://localhost:8000/analytics/topics?limit=10" -H "Authorization: Bearer $viewerToken"
curl.exe -s "http://localhost:8000/analytics/wordcloud?limit=20" -H "Authorization: Bearer $viewerToken"
```

## Data Quality, Validation, And Evaluation

The demo data-quality layer exposes:

- `GET /analytics/data-quality`

This endpoint is protected for viewer, analyst, and admin users. It is read-only and does not alter documents, chunks, embeddings, reports, or Q&A history.

The ground-truth fixture is version-controlled at:

```text
samples/demo/evaluation/ground_truth.json
```

Methodology:

- Structured extraction accuracy is measured only against the explicit demo ground-truth fixture.
- It is calculated as `matched_fields / total_expected_fields * 100`.
- Expected values are drawn from the current fictional CMPDI/CIL demo documents.
- Values are extracted from already-processed chunk text using deterministic regex parsers.
- Numeric comparisons normalize commas and numeric units; missing or mismatched values reduce accuracy.
- Validation rules are separate from extraction accuracy and flag pass, failed, or needs_review.
- This is not a claim of universal production accuracy. It is a reproducible demo metric for the curated dataset.
- Validation rules are intended to grow by CIL subsidiary, reporting workflow, and document type.

Current validation rules:

- Mineable reserve must not exceed inferred geological reserve.
- Actual production is compared with production target.
- Monthly production values must match the parliamentary-response values where both are available.
- Every report source document must exist, be processed, and have at least one chunk.

Run the data-quality check:

```powershell
$viewerLogin = curl.exe -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\":\"viewer@cmpdi.local\",\"password\":\"<password-from-secure-config>\"}" | ConvertFrom-Json
$viewerToken = $viewerLogin.access_token
curl.exe -s http://localhost:8000/analytics/data-quality -H "Authorization: Bearer $viewerToken"
```

## Workflow Metrics

The workflow metrics layer exposes:

- `GET /analytics/workflow-metrics`

This endpoint is protected for viewer, analyst, and admin users. It reports two PS-required demo metrics:

- Report-preparation time reduction percentage
- Repetitive-workflow automation percentage

Fixtures:

```text
samples/demo/evaluation/manual_baseline_assumptions.json
samples/demo/evaluation/workflow_benchmark.json
```

Methodology:

- `automated_wall_clock_seconds` is measured from a real continuous workflow interval.
- For this demo, report id `11` was not used as the timing source because it was created during earlier interactive work and does not provide a clean interval from first upload to saved report.
- A temporary controlled benchmark run was used instead: copies of the eight demo documents were uploaded, processed, embedded, and used to generate a temporary report. The benchmark start is immediately before the first upload, and the benchmark finish is when the generated report is saved.
- Temporary benchmark documents, chunks, jobs, report, and MinIO objects are removed after measurement. Audit logs are preserved.
- `manual_baseline_time_seconds` is a documented team estimate from `manual_baseline_assumptions.json`, not a measured historical fact.
- The manual baseline is a documented estimate, not a measured comparison against an actual manual process — this is disclosed transparently.
- `time_reduction_percentage = (manual_baseline_time_seconds - automated_wall_clock_seconds) / manual_baseline_time_seconds * 100`.
- `aggregate_compute_seconds` is shown separately as supporting technical evidence and is not used for the percentage because ingestion and embedding work may overlap in parallel.
- `automation_percentage = steps_without_manual_intervention / total_steps * 100`, using the auditable step list in `manual_baseline_assumptions.json`.

Run the workflow metrics check:

```powershell
$viewerLogin = curl.exe -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\":\"viewer@cmpdi.local\",\"password\":\"<password-from-secure-config>\"}" | ConvertFrom-Json
$viewerToken = $viewerLogin.access_token
curl.exe -s http://localhost:8000/analytics/workflow-metrics -H "Authorization: Bearer $viewerToken"
```

Verify database rows:

```powershell
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT id, title, source_document_ids, created_by_user_id, LEFT(generated_content, 500) AS generated_content_preview, created_at, updated_at FROM reports ORDER BY id DESC LIMIT 5;"
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT id, user_id, action, entity_type, entity_id, metadata, created_at FROM audit_logs WHERE action IN ('report_generated', 'report_generation_failed') ORDER BY id DESC LIMIT 10;"
docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT c.document_id, c.chunk_index, LEFT(c.text, 200) AS chunk_text FROM chunks c JOIN documents d ON d.id = c.document_id WHERE d.processing_status = 'processed' ORDER BY c.document_id, c.chunk_index LIMIT 10;"
```

## Day 7: React Frontend Shell

Day 7 adds a Vite + React + Tailwind frontend wired to the existing backend APIs.

Screens included:

- Login and logout with JWT storage for local demo
- Dashboard summary with Recharts charts
- Documents upload/list/status and document chunk detail
- Q&A with citations and history
- Semantic search
- Reports list/detail/generate
- Topics and word cloud analytics

The frontend reads the backend URL from:

```env
VITE_API_BASE_URL=http://localhost:8000
```

### Local Frontend Setup

```powershell
cd frontend
npm install
npm run build
npm run dev -- --host 0.0.0.0
```

The frontend runs at `http://localhost:5173`.

### Docker Frontend Setup

Docker Compose starts the frontend with the rest of the demo stack:

```powershell
docker compose up --build -d
docker compose run --rm frontend npm install
docker compose run --rm frontend npm run build
```

### Demo Logins

```text
admin@cmpdi.local / <password-from-secure-config>
analyst@cmpdi.local / <password-from-secure-config>
viewer@cmpdi.local / <password-from-secure-config>
```

### Recommended Demo Flow

1. Login as `analyst@cmpdi.local`.
2. Open Dashboard and confirm analytics counts and charts load.
3. Open Documents, upload `samples/day2-sample.txt`, and poll the job status.
4. Open a document and confirm chunks plus embedding status are shown.
5. Ask the Q&A question: `What production target or coal seam information is available?`
6. Run semantic search for `coal seam reserve`.
7. Generate a geological summary report and open the saved report.
8. Open Analytics and confirm topics and word cloud terms load.
9. Logout and login as `viewer@cmpdi.local`; confirm upload and report generation controls are hidden while read-only screens still work.

### Day 7 Verification Commands

```powershell
docker compose up --build -d
docker compose ps
docker compose run --rm frontend npm install
docker compose run --rm frontend npm run build
docker compose up -d frontend
```

API smoke checks used during frontend verification:

```powershell
$analystLogin = curl.exe -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\":\"analyst@cmpdi.local\",\"password\":\"<password-from-secure-config>\"}" | ConvertFrom-Json
$analystToken = $analystLogin.access_token

$viewerLogin = curl.exe -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\":\"viewer@cmpdi.local\",\"password\":\"<password-from-secure-config>\"}" | ConvertFrom-Json
$viewerToken = $viewerLogin.access_token

curl.exe -s http://localhost:8000/auth/me -H "Authorization: Bearer $analystToken"
curl.exe -s http://localhost:8000/analytics/summary -H "Authorization: Bearer $viewerToken"
curl.exe -s http://localhost:8000/documents -H "Authorization: Bearer $viewerToken"
curl.exe -s -X POST http://localhost:8000/documents/upload -H "Authorization: Bearer $analystToken" -F "file=@samples/day2-sample.txt"
curl.exe -s "http://localhost:8000/search/semantic?q=coal%20seam%20reserve&limit=3" -H "Authorization: Bearer $viewerToken"
curl.exe -s -X POST http://localhost:8000/qa/ask -H "Authorization: Bearer $viewerToken" -H "Content-Type: application/json" -d "{\"question\":\"What production target or coal seam information is available?\",\"limit\":3}"
curl.exe -s http://localhost:8000/reports -H "Authorization: Bearer $viewerToken"
curl.exe -s -X POST http://localhost:8000/reports/generate -H "Authorization: Bearer $analystToken" -H "Content-Type: application/json" -d "{\"title\":\"Frontend Demo Report\",\"report_type\":\"geological_summary\"}"
curl.exe -s "http://localhost:8000/analytics/topics?limit=10" -H "Authorization: Bearer $viewerToken"
curl.exe -s "http://localhost:8000/analytics/wordcloud?limit=20" -H "Authorization: Bearer $viewerToken"
```

## Demo Dataset

The `samples/demo/` folder contains fictional but realistic CMPDI/CIL-style documents for a richer judge demo:

- `geological_summary_block_a.txt`
- `monthly_production_report_aug_2026.txt`
- `parliamentary_question_response.txt`
- `borehole_reserve_table.xlsx`
- `safety_environment_note.docx`
- `scanned_ocr_notice.png`
- `dispatch_summary.csv`
- `legacy_archive_note.pdf`

Upload the demo dataset as analyst:

```powershell
$analystLogin = curl.exe -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d "{\"email\":\"analyst@cmpdi.local\",\"password\":\"<password-from-secure-config>\"}" | ConvertFrom-Json
$analystToken = $analystLogin.access_token

$demoFiles = @(
  "samples/demo/geological_summary_block_a.txt",
  "samples/demo/monthly_production_report_aug_2026.txt",
  "samples/demo/parliamentary_question_response.txt",
  "samples/demo/borehole_reserve_table.xlsx",
  "samples/demo/safety_environment_note.docx",
  "samples/demo/scanned_ocr_notice.png",
  "samples/demo/dispatch_summary.csv",
  "samples/demo/legacy_archive_note.pdf"
)

$uploads = foreach ($file in $demoFiles) {
  curl.exe -s -X POST http://localhost:8000/documents/upload -H "Authorization: Bearer $analystToken" -F "file=@$file" | ConvertFrom-Json
}
$uploads | Select-Object document_id, job_id, celery_task_id, filename, processing_status
```

Recommended judge demo Q&A questions:

```text
What are the major coal seam and reserve findings?
What was the August 2026 production target versus actual production?
Which boreholes show the highest inferred reserves?
What safety and environmental compliance issues were reported?
What information is available for a parliamentary response?
```

Recommended semantic search queries:

```text
coal seam reserve
production shortfall
dust suppression
borehole confidence
```

Generate a demo report from only the demo document IDs:

```powershell
curl.exe -s -X POST http://localhost:8000/reports/generate `
  -H "Authorization: Bearer $analystToken" `
  -H "Content-Type: application/json" `
  -d "{\"title\":\"CMPDI/CIL Demo Geological and Production Intelligence Report\",\"document_ids\":[<demo_document_ids>],\"report_type\":\"geological_production_intelligence\"}"
```
