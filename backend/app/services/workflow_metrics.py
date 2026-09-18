import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import settings


def workflow_metrics_report() -> dict:
    assumptions = load_json_fixture(
        settings.workflow_manual_baseline_path,
        "manual_baseline_assumptions.json",
    )
    benchmark = load_json_fixture(
        settings.workflow_benchmark_path,
        "workflow_benchmark.json",
    )

    manual_baseline = assumptions.get("manual_baseline", {})
    manual_seconds = manual_baseline.get("manual_baseline_time_seconds")
    integrity = validate_benchmark_integrity(benchmark)
    wall_clock_seconds = (
        compute_wall_clock_seconds(
            benchmark.get("benchmark_start_utc"),
            benchmark.get("benchmark_end_utc"),
        )
        if integrity["valid"]
        else None
    )
    aggregate_result = compute_validated_aggregate_compute_seconds(benchmark) if integrity["valid"] else {
        "value": None,
        "available": False,
        "note": "Unavailable because the benchmark fixture failed integrity validation.",
    }
    time_reduction = compute_time_reduction_percentage(manual_seconds, wall_clock_seconds)
    steps = assumptions.get("automation_workflow_steps", [])
    automation_percentage = compute_automation_percentage(steps)

    return {
        "automated_wall_clock_seconds": wall_clock_seconds,
        "automated_wall_clock_measurement": {
            "measurement_type": benchmark.get("measurement_type"),
            "benchmark_type": benchmark.get("benchmark_type"),
            "benchmark_run_id": benchmark.get("benchmark_run_id"),
            "integrity_status": benchmark.get("integrity_status"),
            "integrity_valid": integrity["valid"],
            "integrity_errors": integrity["errors"],
            "benchmark_start_utc": benchmark.get("benchmark_start_utc"),
            "benchmark_end_utc": benchmark.get("benchmark_end_utc"),
            "temporary_document_ids": benchmark.get("temporary_document_ids", []),
            "temporary_job_ids": benchmark.get("temporary_job_ids", []),
            "temporary_report_id": benchmark.get("temporary_report_id"),
            "source_files": benchmark.get("source_files", []),
            "reason": benchmark.get("reason"),
            "upload_audit_events": ensure_list(benchmark.get("upload_audit_events", [])),
            "report_created_at_utc": benchmark.get("report_created_at_utc"),
            "report_audit_events": ensure_list(benchmark.get("report_audit_events", [])),
        },
        "aggregate_compute_seconds": aggregate_result["value"],
        "aggregate_compute_available": aggregate_result["available"],
        "aggregate_compute_note": aggregate_result["note"],
        "compute_events": ensure_list(benchmark.get("compute_events", [])),
        "manual_baseline_time_seconds": manual_seconds,
        "manual_baseline_measurement_type": manual_baseline.get("measurement_type"),
        "manual_baseline_rationale": manual_baseline.get("rationale"),
        "manual_baseline_disclosure": manual_baseline.get("disclosure"),
        "manual_baseline_activities": manual_baseline.get("activities", []),
        "time_reduction_percentage": time_reduction,
        "automation_step_breakdown": steps,
        "automation_percentage": automation_percentage,
        "automation_counts": automation_counts(steps),
        "methodology": (
            "automated_wall_clock_seconds is measured from a continuous real workflow interval: benchmark start "
            "immediately before the first temporary demo document upload, and benchmark finish when the temporary "
            "generated report is saved. manual_baseline_time_seconds is a documented team estimate, not a measured "
            "historical manual process. time_reduction_percentage is computed from automated_wall_clock_seconds and "
            "manual_baseline_time_seconds. aggregate_compute_seconds is shown separately as supporting evidence and "
            "is not used for the percentage because parallel processing can overlap job durations."
        ),
        "fixtures": {
            "manual_baseline": str(resolve_fixture_path(settings.workflow_manual_baseline_path, "manual_baseline_assumptions.json")),
            "benchmark": str(resolve_fixture_path(settings.workflow_benchmark_path, "workflow_benchmark.json")),
        },
    }


def compute_wall_clock_seconds(start_value: str | None, end_value: str | None) -> float | None:
    if not start_value or not end_value:
        return None
    start = parse_timestamp(start_value)
    end = parse_timestamp(end_value)
    return round((end - start).total_seconds(), 3)


def compute_aggregate_compute_seconds(events: list[dict]) -> float:
    total = 0.0
    for event in events:
        duration = event.get("duration_seconds")
        if isinstance(duration, (int, float)):
            total += float(duration)
    return round(total, 3)


def compute_validated_aggregate_compute_seconds(benchmark: dict) -> dict:
    start = parse_optional_timestamp(benchmark.get("benchmark_start_utc"))
    end = parse_optional_timestamp(benchmark.get("benchmark_end_utc"))
    if start is None or end is None:
        return unavailable_aggregate("Unavailable due to missing benchmark start/end timestamps.")

    expected_job_ids = set(benchmark.get("temporary_job_ids", []))
    job_events = [event for event in ensure_list(benchmark.get("compute_events", [])) if event.get("event") == "document_ingestion_job"]
    event_job_ids = {event.get("job_id") for event in job_events}
    if event_job_ids != expected_job_ids:
        return unavailable_aggregate("Unavailable due to job event IDs not matching the benchmark job IDs.")

    for event in job_events:
        started_at = parse_optional_timestamp(event.get("started_at_utc"))
        finished_at = parse_optional_timestamp(event.get("finished_at_utc"))
        audit_at = parse_optional_timestamp(event.get("ingestion_completed_audit_at_utc"))
        if started_at is None or finished_at is None or audit_at is None:
            return unavailable_aggregate("Unavailable due to missing job or ingestion audit timestamps.")
        if started_at < start or finished_at > end or finished_at < started_at:
            return unavailable_aggregate("Unavailable due to timestamp inconsistency: job timing falls outside the benchmark interval.")
        if audit_at < finished_at - timedelta(seconds=2) or audit_at > end:
            return unavailable_aggregate("Unavailable due to timestamp inconsistency: ingestion audit timing does not reconcile with job timing.")
        measured_duration = round((finished_at - started_at).total_seconds(), 3)
        duration = event.get("duration_seconds")
        if not isinstance(duration, (int, float)) or abs(float(duration) - measured_duration) > 0.01:
            return unavailable_aggregate("Unavailable due to timestamp inconsistency: job duration does not match started_at/finished_at.")

    return {
        "value": compute_aggregate_compute_seconds(ensure_list(benchmark.get("compute_events", []))),
        "available": True,
        "note": (
            "Measured supporting technical evidence only. This is not used for time-reduction percentage "
            "because ingestion and embedding work may overlap in parallel."
        ),
    }


def compute_time_reduction_percentage(manual_seconds: int | float | None, automated_seconds: int | float | None) -> float | None:
    if manual_seconds is None or automated_seconds is None or manual_seconds <= 0:
        return None
    return round(((manual_seconds - automated_seconds) / manual_seconds) * 100, 2)


def validate_benchmark_integrity(benchmark: dict) -> dict:
    errors: list[str] = []
    start = parse_optional_timestamp(benchmark.get("benchmark_start_utc"))
    end = parse_optional_timestamp(benchmark.get("benchmark_end_utc"))
    document_ids = benchmark.get("temporary_document_ids", [])
    report_id = benchmark.get("temporary_report_id")

    if start is None:
        errors.append("benchmark_start_utc is missing or invalid")
    if end is None:
        errors.append("benchmark_end_utc is missing or invalid")
    if start is not None and end is not None and end <= start:
        errors.append("benchmark_end_utc must be after benchmark_start_utc")
    if len(document_ids) != 8:
        errors.append("benchmark must contain exactly eight temporary documents")
    if report_id is None:
        errors.append("benchmark must contain one temporary report")

    upload_audits = ensure_list(benchmark.get("upload_audit_events", []))
    audit_doc_ids = {event.get("document_id") for event in upload_audits}
    if len(upload_audits) != 8 or audit_doc_ids != set(document_ids):
        errors.append("upload audit events must cover exactly the eight temporary documents")
    if start is not None:
        minimum_upload_time = start - timedelta(seconds=2)
        for event in upload_audits:
            uploaded_at = parse_optional_timestamp(event.get("created_at_utc"))
            if uploaded_at is None:
                errors.append(f"upload audit for document {event.get('document_id')} is missing a timestamp")
            elif uploaded_at < minimum_upload_time:
                errors.append(f"upload audit for document {event.get('document_id')} precedes benchmark_start_utc beyond tolerance")

    report_created_at = parse_optional_timestamp(benchmark.get("report_created_at_utc"))
    if report_created_at is None:
        errors.append("temporary report created_at timestamp is missing or invalid")
    elif end is not None and report_created_at > end:
        errors.append("temporary report created_at is after benchmark_end_utc")

    for event in ensure_list(benchmark.get("report_audit_events", [])):
        audit_at = parse_optional_timestamp(event.get("created_at_utc"))
        if audit_at is None:
            errors.append("temporary report audit timestamp is missing or invalid")
        elif end is not None and audit_at > end:
            errors.append("temporary report audit timestamp is after benchmark_end_utc")

    return {"valid": not errors, "errors": errors}


def compute_automation_percentage(steps: list[dict]) -> float | None:
    if not steps:
        return None
    counts = automation_counts(steps)
    return round((counts["steps_without_manual_intervention"] / counts["total_steps"]) * 100, 2)


def automation_counts(steps: list[dict]) -> dict:
    total = len(steps)
    automated = sum(1 for step in steps if not step.get("requires_manual_intervention", True))
    manual = total - automated
    return {
        "total_steps": total,
        "steps_without_manual_intervention": automated,
        "steps_requiring_manual_intervention": manual,
    }


def load_json_fixture(configured_path: str, filename: str) -> dict[str, Any]:
    path = resolve_fixture_path(configured_path, filename)
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def resolve_fixture_path(configured_path: str, filename: str) -> Path:
    candidates = [
        Path(configured_path),
        Path(__file__).resolve().parents[3] / "samples" / "demo" / "evaluation" / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Workflow metrics fixture not found. Checked: {', '.join(str(item) for item in candidates)}")


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_optional_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parse_timestamp(value)
    except ValueError:
        return None


def unavailable_aggregate(note: str) -> dict:
    return {"value": None, "available": False, "note": note}


def ensure_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
