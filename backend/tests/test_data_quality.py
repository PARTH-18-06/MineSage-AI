import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.services.data_quality import FAILED, MATCHED, NEEDS_REVIEW, evaluate_expectation, validate_mineable_reserve


def test_correct_value_is_matched():
    result = evaluate_expectation(
        {
            "field": "august_2026_production_target_mt",
            "expected_value": 1.28,
            "unit": "MT",
            "source_filename": "monthly_production_report_aug_2026.txt",
            "source_document_id": 19,
            "rule": "test rule",
        },
        [
            {
                "chunk_id": 1,
                "document_id": 19,
                "source_filename": "monthly_production_report_aug_2026.txt",
                "chunk_index": 0,
                "source_reference": "monthly_production_report_aug_2026.txt",
                "text": "The August 2026 coal production target was 1.28 MT.",
            }
        ],
    )

    assert result["status"] == MATCHED
    assert result["extracted_value"] == 1.28


def test_deliberately_mismatched_expectation_is_failed():
    result = evaluate_expectation(
        {
            "field": "august_2026_actual_production_mt",
            "expected_value": 2.5,
            "unit": "MT",
            "source_filename": "monthly_production_report_aug_2026.txt",
            "source_document_id": 19,
            "rule": "test rule",
        },
        [
            {
                "chunk_id": 2,
                "document_id": 19,
                "source_filename": "monthly_production_report_aug_2026.txt",
                "chunk_index": 0,
                "source_reference": "monthly_production_report_aug_2026.txt",
                "text": "Actual coal production for August 2026 was 1.16 MT.",
            }
        ],
    )

    assert result["status"] == FAILED
    assert result["expected_value"] == 2.5
    assert result["extracted_value"] == 1.16


def test_missing_value_needs_review():
    result = evaluate_expectation(
        {
            "field": "sump_s2_pumping_capacity_cum_per_hour",
            "expected_value": 1400,
            "unit": "cubic_meters_per_hour",
            "source_filename": "safety_environment_note.docx",
            "source_document_id": 22,
            "rule": "test rule",
        },
        [
            {
                "chunk_id": 3,
                "document_id": 22,
                "source_filename": "safety_environment_note.docx",
                "chunk_index": 0,
                "source_reference": "safety_environment_note.docx",
                "text": "Safety note without the expected pumping capacity value.",
            }
        ],
    )

    assert result["status"] == NEEDS_REVIEW
    assert result["extracted_value"] is None


def test_validation_rule_violation_is_flagged():
    result = validate_mineable_reserve(
        {
            "inferred_geological_reserve_total_mt": 10,
            "mineable_reserve_mt": 12,
        }
    )

    assert result["status"] == FAILED
    assert "exceeds" in result["message"]


def test_data_quality_endpoint_requires_authentication():
    response = TestClient(app).get("/analytics/data-quality")

    assert response.status_code == 401
