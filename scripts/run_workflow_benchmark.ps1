$ErrorActionPreference = "Stop"

$apiBase = "http://localhost:8000"
$benchmarkRunId = [guid]::NewGuid().ToString()
$demoFiles = @(
  "samples/demo/geological_summary_block_a.txt",
  "samples/demo/monthly_production_report_aug_2026.txt",
  "samples/demo/parliamentary_question_response.txt",
  "samples/demo/safety_environment_note.docx",
  "samples/demo/legacy_archive_note.pdf",
  "samples/demo/scanned_ocr_notice.png",
  "samples/demo/borehole_reserve_table.xlsx",
  "samples/demo/dispatch_summary.csv"
)

$documentIds = @()
$jobIds = @()
$reportId = $null
$objectPaths = @()
$fixturePath = "samples/demo/evaluation/workflow_benchmark.json"

function Get-DbUtcNow {
  $line = docker compose exec postgres psql -U cmpdi -d cmpdi_reports -t -A -c "SELECT replace((clock_timestamp() AT TIME ZONE 'UTC')::text, ' ', 'T') || 'Z';"
  return ($line | Where-Object { $_ -match "Z$" } | Select-Object -First 1).Trim()
}

function Invoke-SqlJson($sql) {
  $json = docker compose exec postgres psql -U cmpdi -d cmpdi_reports -t -A -c "SELECT COALESCE(json_agg(row_to_json(row_data)), '[]'::json) FROM ($sql) row_data;"
  $line = $json | Where-Object { $_ -match "^\[" } | Select-Object -First 1
  return @($line | ConvertFrom-Json)
}

function Parse-UtcTimestamp($value) {
  if ($value -is [datetime]) {
    return [datetimeoffset]::new([datetime]::SpecifyKind($value, [DateTimeKind]::Utc))
  }
  return [datetimeoffset]::Parse([string]$value, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal)
}

function Cleanup-TemporaryData {
  if ($objectPaths.Count -eq 0 -and $documentIds.Count -gt 0) {
    $documentIdCsv = $documentIds -join ","
    $rows = Invoke-SqlJson "SELECT object_path FROM documents WHERE id IN ($documentIdCsv) ORDER BY id"
    foreach ($row in $rows) {
      $objectPaths += $row.object_path
    }
  }

  if ($objectPaths.Count -gt 0) {
    Write-Output "===== DELETE TEMPORARY MINIO OBJECTS ====="
    foreach ($objectPath in $objectPaths) {
      docker compose exec api python -c "from app.config import settings; from app.services import get_minio_client; key='$objectPath'; get_minio_client().delete_object(Bucket=settings.minio_bucket, Key=key); print('minio_object_deleted=True; object_path=' + key)"
    }
  }

  if ($documentIds.Count -gt 0) {
    $documentIdCsv = $documentIds -join ","
    $jobIdCsv = if ($jobIds.Count -gt 0) { $jobIds -join "," } else { "NULL" }
    $reportDelete = if ($reportId -ne $null) { "DELETE FROM reports WHERE id = $reportId RETURNING id, title;" } else { "SELECT 'no temporary report to delete' AS info;" }
    Write-Output "===== DELETE TEMPORARY DATABASE ROWS ====="
    docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "BEGIN; DELETE FROM chunks WHERE document_id IN ($documentIdCsv) RETURNING id, document_id, chunk_index; DELETE FROM jobs WHERE id IN ($jobIdCsv) RETURNING id, document_id, status; $reportDelete DELETE FROM documents WHERE id IN ($documentIdCsv) RETURNING id, original_filename; COMMIT;"
  }
}

$adminPassword = $env:DEFAULT_ADMIN_PASSWORD
if ([string]::IsNullOrWhiteSpace($adminPassword)) {
  throw "DEFAULT_ADMIN_PASSWORD must be supplied through the process environment."
}

try {
  Write-Output "===== WORKFLOW BENCHMARK LOGIN ====="
  $login = Invoke-RestMethod -Method Post -Uri "$apiBase/auth/login" -ContentType "application/json" -Body (@{
    email = "admin@cmpdi.local"
    password = $adminPassword
  } | ConvertTo-Json)
  $headers = @{ Authorization = "Bearer $($login.access_token)" }
  Write-Output "benchmark_run_id=$benchmarkRunId"
  Write-Output "token_present=$([bool]$login.access_token); token_type=$($login.token_type)"

  $benchmarkStart = Get-DbUtcNow
  Write-Output "===== BENCHMARK START UTC ====="
  Write-Output $benchmarkStart

  Write-Output "===== UPLOAD TEMPORARY COPIES ====="
  foreach ($filePath in $demoFiles) {
    $upload = Invoke-RestMethod -Method Post -Uri "$apiBase/documents/upload" -Headers $headers -Form @{
      file = Get-Item $filePath
    }
    $documentIds += [int]$upload.document_id
    $jobIds += [int]$upload.job_id
    $upload | ConvertTo-Json -Depth 8 | Write-Output
  }

  if ($documentIds.Count -ne 8 -or $jobIds.Count -ne 8) {
    throw "Benchmark requires exactly eight temporary documents and eight jobs; got documents=$($documentIds.Count), jobs=$($jobIds.Count)."
  }

  $documentIdCsv = $documentIds -join ","
  $jobIdCsv = $jobIds -join ","
  Write-Output "temporary_document_ids=$documentIdCsv"
  Write-Output "temporary_job_ids=$jobIdCsv"

  Write-Output "===== TEMPORARY DOCUMENT OBJECT PATHS ====="
  $objectRows = Invoke-SqlJson "SELECT id, object_path FROM documents WHERE id IN ($documentIdCsv) ORDER BY id"
  foreach ($row in $objectRows) {
    $objectPaths += $row.object_path
    Write-Output "document_id=$($row.id); object_path=$($row.object_path)"
  }

  Write-Output "===== POLL TEMPORARY JOBS ====="
  $terminal = @("completed", "failed")
  $allDone = $false
  for ($poll = 1; $poll -le 240; $poll++) {
    Start-Sleep -Seconds 1
    $statuses = @()
    foreach ($jobId in $jobIds) {
      $job = Invoke-RestMethod -Method Get -Uri "$apiBase/jobs/$jobId" -Headers $headers
      $statuses += "$($job.id):$($job.status)"
    }
    Write-Output ("poll={0}; statuses={1}" -f $poll, ($statuses -join ","))
    $allDone = $true
    foreach ($statusPair in $statuses) {
      $status = ($statusPair -split ":")[1]
      if ($terminal -notcontains $status) {
        $allDone = $false
      }
      if ($status -eq "failed") {
        throw "Temporary benchmark job failed: $statusPair"
      }
    }
    if ($allDone) {
      break
    }
  }
  if (-not $allDone) {
    throw "Benchmark timed out before all ingestion jobs reached a terminal state."
  }

  Write-Output "===== WAIT FOR TEMPORARY EMBEDDINGS ====="
  $embeddingsDone = $false
  for ($poll = 1; $poll -le 240; $poll++) {
    Start-Sleep -Seconds 1
    $embeddingLine = docker compose exec postgres psql -U cmpdi -d cmpdi_reports -t -A -F "|" -c "SELECT COUNT(*) AS chunks, COUNT(embedding) AS embedded FROM chunks WHERE document_id IN ($documentIdCsv);"
    $parts = ($embeddingLine | Where-Object { $_ -match "^\d+\|" } | Select-Object -First 1) -split "\|"
    $chunks = [int]$parts[0]
    $embedded = [int]$parts[1]
    Write-Output "embedding_poll=$poll; chunks=$chunks; embedded=$embedded"
    if ($chunks -gt 0 -and $chunks -eq $embedded) {
      $embeddingsDone = $true
      break
    }
  }
  if (-not $embeddingsDone) {
    throw "Benchmark timed out before every temporary chunk received an embedding."
  }

  Write-Output "===== GENERATE TEMPORARY REPORT ====="
  $reportPayload = @{
    title = "Workflow Metrics Temporary Benchmark Report $benchmarkRunId"
    report_type = "geological_summary"
    document_ids = $documentIds
  } | ConvertTo-Json -Depth 8
  $reportStart = Get-DbUtcNow
  $report = Invoke-RestMethod -Method Post -Uri "$apiBase/reports/generate" -Headers $headers -ContentType "application/json" -Body $reportPayload
  $reportId = [int]$report.id
  $benchmarkEnd = Get-DbUtcNow
  $report | ConvertTo-Json -Depth 8 | Write-Output
  Write-Output "report_request_start_utc=$reportStart"
  Write-Output "benchmark_end_utc=$benchmarkEnd"

  Write-Output "===== BENCHMARK INTEGRITY QUERIES ====="
  $uploadAuditRows = Invoke-SqlJson "SELECT (metadata->>'job_id')::bigint AS job_id, entity_id::bigint AS document_id, replace((created_at AT TIME ZONE 'UTC')::text, ' ', 'T') || 'Z' AS created_at_utc FROM audit_logs WHERE action = 'document_upload_requested' AND entity_id::bigint IN ($documentIdCsv) ORDER BY entity_id::bigint"
  $reportRows = Invoke-SqlJson "SELECT id, replace((created_at AT TIME ZONE 'UTC')::text, ' ', 'T') || 'Z' AS created_at_utc FROM reports WHERE id = $reportId"
  $reportAuditRows = Invoke-SqlJson "SELECT entity_id::bigint AS report_id, replace((created_at AT TIME ZONE 'UTC')::text, ' ', 'T') || 'Z' AS created_at_utc FROM audit_logs WHERE action = 'report_generated' AND entity_id::bigint = $reportId ORDER BY created_at"
  $jobRows = Invoke-SqlJson "SELECT jobs.id AS job_id, jobs.document_id, replace((jobs.started_at AT TIME ZONE 'UTC')::text, ' ', 'T') || 'Z' AS started_at_utc, replace((jobs.finished_at AT TIME ZONE 'UTC')::text, ' ', 'T') || 'Z' AS finished_at_utc, ROUND(EXTRACT(EPOCH FROM (jobs.finished_at - jobs.started_at))::numeric, 3) AS duration_seconds, replace((audit_logs.created_at AT TIME ZONE 'UTC')::text, ' ', 'T') || 'Z' AS ingestion_completed_audit_at_utc FROM jobs LEFT JOIN audit_logs ON audit_logs.action = 'document_ingestion_completed' AND audit_logs.entity_id::bigint = jobs.document_id WHERE jobs.id IN ($jobIdCsv) ORDER BY jobs.id"

  Write-Output "upload_audit_events=$($uploadAuditRows | ConvertTo-Json -Depth 8 -Compress)"
  Write-Output "report_created_at=$($reportRows | ConvertTo-Json -Depth 8 -Compress)"
  Write-Output "report_audit_events=$($reportAuditRows | ConvertTo-Json -Depth 8 -Compress)"
  Write-Output "job_compute_events=$($jobRows | ConvertTo-Json -Depth 8 -Compress)"

  if ($uploadAuditRows.Count -ne 8) {
    throw "Integrity check failed: expected 8 upload audit events, found $($uploadAuditRows.Count)."
  }
  foreach ($audit in $uploadAuditRows) {
    $uploadTime = Parse-UtcTimestamp $audit.created_at_utc
    $startTime = Parse-UtcTimestamp $benchmarkStart
    if ($uploadTime -lt $startTime.AddSeconds(-2)) {
      throw "Integrity check failed: upload audit for document $($audit.document_id) predates benchmark start beyond 2 seconds."
    }
  }
  if ($reportRows.Count -ne 1) {
    throw "Integrity check failed: expected exactly one temporary report row, found $($reportRows.Count)."
  }
  $reportCreated = Parse-UtcTimestamp $reportRows[0].created_at_utc
  $endTime = Parse-UtcTimestamp $benchmarkEnd
  if ($reportCreated -gt $endTime) {
    throw "Integrity check failed: report created_at is after benchmark end."
  }
  foreach ($audit in $reportAuditRows) {
    $auditTime = Parse-UtcTimestamp $audit.created_at_utc
    if ($auditTime -gt $endTime) {
      throw "Integrity check failed: report audit timestamp is after benchmark end."
    }
  }

  $aggregateAvailable = $true
  $aggregateReason = $null
  $computeEvents = @()
  foreach ($row in $jobRows) {
    $started = Parse-UtcTimestamp $row.started_at_utc
    $finished = Parse-UtcTimestamp $row.finished_at_utc
    $ingestionAudit = Parse-UtcTimestamp $row.ingestion_completed_audit_at_utc
    $startTime = Parse-UtcTimestamp $benchmarkStart
    if ($started -lt $startTime -or $finished -gt $endTime -or $ingestionAudit -lt $finished.AddSeconds(-2) -or $ingestionAudit -gt $endTime) {
      $aggregateAvailable = $false
      $aggregateReason = "unavailable due to timestamp inconsistency"
    }
    $computeEvents += [ordered]@{
      event = "document_ingestion_job"
      job_id = [int]$row.job_id
      document_id = [int]$row.document_id
      started_at_utc = $row.started_at_utc
      finished_at_utc = $row.finished_at_utc
      ingestion_completed_audit_at_utc = $row.ingestion_completed_audit_at_utc
      duration_seconds = [double]$row.duration_seconds
    }
  }

  if ($aggregateAvailable) {
    $reportStartTime = Parse-UtcTimestamp $reportStart
    $reportEndTime = Parse-UtcTimestamp $benchmarkEnd
    $reportDuration = [math]::Round(($reportEndTime - $reportStartTime).TotalSeconds, 3)
    $computeEvents += [ordered]@{
      event = "report_generation_request"
      report_id = $reportId
      started_at_utc = $reportStart
      finished_at_utc = $benchmarkEnd
      duration_seconds = $reportDuration
    }
  }

  Write-Output "===== WRITE VALIDATED BENCHMARK FIXTURE ====="
  $benchmark = [ordered]@{
    dataset = "CMPDI/CIL SIH demo workflow benchmark"
    version = "2026-09-14"
    benchmark_run_id = $benchmarkRunId
    benchmark_type = "temporary_controlled_benchmark"
    measurement_type = "measured_real_wall_clock_interval"
    integrity_status = "validated"
    reason = "Report id=11 was created during earlier interactive work and does not provide a continuous traceable interval from first upload to saved report."
    benchmark_start_utc = $benchmarkStart
    benchmark_end_utc = $benchmarkEnd
    temporary_document_ids = $documentIds
    temporary_job_ids = $jobIds
    temporary_report_id = $reportId
    source_files = @($demoFiles | ForEach-Object { Split-Path $_ -Leaf })
    upload_audit_events = @($uploadAuditRows)
    report_created_at_utc = $reportRows[0].created_at_utc
    report_audit_events = @($reportAuditRows)
    compute_events = @($computeEvents)
    aggregate_compute_available = $aggregateAvailable
    aggregate_compute_unavailable_reason = $aggregateReason
  }
  $benchmark | ConvertTo-Json -Depth 12 | Set-Content -Path $fixturePath -Encoding UTF8
  Get-Content $fixturePath
}
catch {
  Write-Output "BENCHMARK_FAILED=$($_.Exception.Message)"
  throw
}
finally {
  Cleanup-TemporaryData
  Write-Output "===== FINAL CURATED COUNTS ====="
  docker compose exec postgres psql -U cmpdi -d cmpdi_reports -c "SELECT (SELECT COUNT(*) FROM documents) AS documents, (SELECT COUNT(*) FROM reports) AS reports, (SELECT COUNT(*) FROM qa_answers) AS qa_answers, (SELECT COUNT(*) FROM chunks) AS chunks, (SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL) AS chunks_with_embeddings;"
}
