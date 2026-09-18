import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.services.workflow_metrics import (
    compute_aggregate_compute_seconds,
    compute_automation_percentage,
    compute_time_reduction_percentage,
    compute_validated_aggregate_compute_seconds,
    compute_wall_clock_seconds,
    validate_benchmark_integrity,
)


def test_wall_clock_seconds_uses_real_timestamps():
    seconds = compute_wall_clock_seconds("2026-09-14T10:00:00Z", "2026-09-14T10:02:30.500Z")

    assert seconds == 150.5


def test_aggregate_compute_seconds_is_distinct_from_wall_clock_seconds():
    wall_clock = compute_wall_clock_seconds("2026-09-14T10:00:00Z", "2026-09-14T10:00:10Z")
    aggregate = compute_aggregate_compute_seconds(
        [
            {"event": "ingest_document", "duration_seconds": 8.0},
            {"event": "embed_document", "duration_seconds": 8.0},
        ]
    )

    assert wall_clock == 10.0
    assert aggregate == 16.0
    assert aggregate != wall_clock


def test_time_reduction_percentage_uses_manual_and_automated_inputs():
    result = compute_time_reduction_percentage(1000, 250)

    assert result == 75.0


def test_time_reduction_percentage_is_null_without_manual_baseline():
    result = compute_time_reduction_percentage(None, 250)

    assert result is None


def test_automation_percentage_matches_step_breakdown():
    steps = [
        {"step": "document_intake", "requires_manual_intervention": True},
        {"step": "text_extraction", "requires_manual_intervention": False},
        {"step": "report_storage", "requires_manual_intervention": False},
        {"step": "quality_validation", "requires_manual_intervention": False},
    ]

    assert compute_automation_percentage(steps) == 75.0


def test_benchmark_start_precedes_upload_audit_timestamps():
    benchmark = {
        "benchmark_start_utc": "2026-09-14T10:00:00Z",
        "benchmark_end_utc": "2026-09-14T10:05:00Z",
        "temporary_document_ids": [1, 2, 3, 4, 5, 6, 7, 8],
        "temporary_report_id": 9,
        "upload_audit_events": [
            {"document_id": document_id, "created_at_utc": "2026-09-14T10:00:01Z"}
            for document_id in [1, 2, 3, 4, 5, 6, 7, 8]
        ],
        "report_created_at_utc": "2026-09-14T10:04:59Z",
        "report_audit_events": [{"report_id": 9, "created_at_utc": "2026-09-14T10:04:59Z"}],
    }

    assert validate_benchmark_integrity(benchmark)["valid"] is True


def test_benchmark_end_must_follow_report_timestamp():
    benchmark = {
        "benchmark_start_utc": "2026-09-14T10:00:00Z",
        "benchmark_end_utc": "2026-09-14T10:04:00Z",
        "temporary_document_ids": [1, 2, 3, 4, 5, 6, 7, 8],
        "temporary_report_id": 9,
        "upload_audit_events": [
            {"document_id": document_id, "created_at_utc": "2026-09-14T10:00:01Z"}
            for document_id in [1, 2, 3, 4, 5, 6, 7, 8]
        ],
        "report_created_at_utc": "2026-09-14T10:04:01Z",
        "report_audit_events": [{"report_id": 9, "created_at_utc": "2026-09-14T10:04:01Z"}],
    }

    result = validate_benchmark_integrity(benchmark)

    assert result["valid"] is False
    assert "temporary report created_at is after benchmark_end_utc" in result["errors"]


def test_invalid_benchmark_data_yields_null_time_reduction_inputs():
    benchmark = {
        "benchmark_start_utc": None,
        "benchmark_end_utc": "2026-09-14T10:04:00Z",
        "temporary_document_ids": [],
        "temporary_report_id": None,
        "upload_audit_events": [],
        "report_created_at_utc": None,
    }
    integrity = validate_benchmark_integrity(benchmark)
    automated_seconds = compute_wall_clock_seconds(
        benchmark.get("benchmark_start_utc"),
        benchmark.get("benchmark_end_utc"),
    ) if integrity["valid"] else None

    assert integrity["valid"] is False
    assert compute_time_reduction_percentage(7440, automated_seconds) is None


def test_aggregate_compute_is_suppressed_when_job_outside_benchmark_interval():
    benchmark = {
        "benchmark_start_utc": "2026-09-14T10:00:00Z",
        "benchmark_end_utc": "2026-09-14T10:01:00Z",
        "temporary_job_ids": [1],
        "compute_events": [
            {
                "event": "document_ingestion_job",
                "job_id": 1,
                "document_id": 11,
                "started_at_utc": "2026-09-14T09:59:59Z",
                "finished_at_utc": "2026-09-14T10:00:10Z",
                "ingestion_completed_audit_at_utc": "2026-09-14T10:00:10Z",
                "duration_seconds": 11.0,
            }
        ],
    }

    result = compute_validated_aggregate_compute_seconds(benchmark)

    assert result["value"] is None
    assert result["available"] is False
    assert "timestamp inconsistency" in result["note"]


def test_workflow_metrics_endpoint_requires_authentication():
    response = TestClient(app).get("/analytics/workflow-metrics")

    assert response.status_code == 401
