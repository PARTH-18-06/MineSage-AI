import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings

MATCHED = "matched"
FAILED = "failed"
NEEDS_REVIEW = "needs_review"
PASS = "pass"

NUMBER_TOLERANCE = 0.001

FIELD_PATTERNS: dict[str, list[str]] = {
    "seam_ii_depth_min_m": [r"Seam II occurs between\s*(?P<value>[\d.]+)\s*meters"],
    "seam_ii_depth_max_m": [r"Seam II occurs between\s*[\d.]+\s*meters\s*and\s*(?P<value>[\d.]+)\s*meters"],
    "seam_ii_avg_thickness_m": [r"Seam II occurs.*?average seam thickness of\s*(?P<value>[\d.]+)\s*meters"],
    "seam_iii_depth_min_m": [r"Seam III occurs between\s*(?P<value>[\d.]+)\s*meters"],
    "seam_iii_depth_max_m": [r"Seam III occurs between\s*[\d.]+\s*meters\s*and\s*(?P<value>[\d.]+)\s*meters"],
    "seam_iii_avg_thickness_m": [r"Seam III occurs.*?average seam thickness of\s*(?P<value>[\d.]+)\s*meters"],
    "seam_iv_depth_min_m": [r"Seam IV occurs between\s*(?P<value>[\d.]+)\s*meters"],
    "seam_iv_depth_max_m": [r"Seam IV occurs between\s*[\d.]+\s*meters\s*and\s*(?P<value>[\d.]+)\s*meters"],
    "seam_iv_avg_thickness_m": [r"Seam IV occurs.*?average seam thickness of\s*(?P<value>[\d.]+)\s*meters"],
    "inferred_geological_reserve_total_mt": [
        r"inferred geological reserve.*?is\s*(?P<value>[\d.]+)\s*MT",
        r"inferred geological reserve of\s*(?P<value>[\d.]+)\s*MT",
    ],
    "mineable_reserve_mt": [
        r"mineable reserve is estimated at\s*(?P<value>[\d.]+)\s*MT",
        r"mineable reserve estimate of\s*(?P<value>[\d.]+)\s*MT",
    ],
    "august_2026_production_target_mt": [
        r"August 2026 coal production target was\s*(?P<value>[\d.]+)\s*MT",
        r"Production target:\s*(?P<value>[\d.]+)\s*MT for August 2026",
        r"PRODUCTION TARGET:\s*(?P<value>[\d.]+)\s*MT",
    ],
    "august_2026_actual_production_mt": [
        r"Actual coal production for August 2026 was\s*(?P<value>[\d.]+)\s*MT",
        r"Actual production:\s*(?P<value>[\d.]+)\s*MT for August 2026",
    ],
    "august_2026_shortfall_mt": [r"shortfall was\s*(?P<value>[\d.]+)\s*MT"],
    "borehole_bh_a04_inferred_reserve_mt": [r"borehole BH-A04 .*? inferred reserve\s*(?P<value>[\d.]+)\s*MT"],
    "borehole_bh_a01_inferred_reserve_mt": [r"borehole BH-A01 .*? inferred reserve\s*(?P<value>[\d.]+)\s*MT"],
    "sump_s2_pumping_capacity_cum_per_hour": [
        r"Sump S-2 pumping capacity was increased to\s*(?P<value>[\d,]+)\s*cubic meters per hour"
    ],
    "dust_suppression_compliance": [r"DUST SUPPRESSION COMPLIANCE:\s*(?P<value>[A-Z]+)"],
}


def data_quality_report(db: Session) -> dict:
    ground_truth = load_ground_truth()
    chunks = load_chunks(db)
    field_results = evaluate_expectations(ground_truth["expectations"], chunks)
    matched_fields = sum(1 for result in field_results if result["status"] == MATCHED)
    total_fields = len(field_results)
    accuracy = round((matched_fields / total_fields) * 100, 2) if total_fields else 0.0
    rule_results = evaluate_validation_rules(db, field_results, chunks)
    validation_counts = count_statuses(rule_results, [PASS, FAILED, NEEDS_REVIEW])

    return {
        "structured_extraction_accuracy": accuracy,
        "matched_fields": matched_fields,
        "total_expected_fields": total_fields,
        "validation_counts": validation_counts,
        "field_evidence": field_results,
        "rule_results": rule_results,
        "methodology": (
            "Accuracy is measured only against samples/demo/evaluation/ground_truth.json. "
            "The evaluator extracts values from processed chunk text using deterministic regex parsers, "
            "normalizes numeric units, and computes matched_fields / total_expected_fields * 100. "
            "Validation rules inspect the same extracted values plus current report source documents. "
            "This is a reproducible demo metric, not a universal production accuracy claim."
        ),
        "ground_truth": {
            "dataset": ground_truth.get("dataset"),
            "version": ground_truth.get("version"),
            "path": str(resolve_ground_truth_path()),
        },
    }


def load_ground_truth(path: str | Path | None = None) -> dict:
    fixture_path = resolve_ground_truth_path(path)
    with fixture_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def resolve_ground_truth_path(path: str | Path | None = None) -> Path:
    candidates = []
    if path:
        candidates.append(Path(path))
    candidates.append(Path(settings.data_quality_ground_truth_path))
    candidates.append(Path(__file__).resolve().parents[3] / "samples" / "demo" / "evaluation" / "ground_truth.json")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Ground-truth fixture not found. Checked: {', '.join(str(item) for item in candidates)}")


def load_chunks(db: Session) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT
                chunks.id AS chunk_id,
                chunks.document_id,
                documents.original_filename AS source_filename,
                chunks.chunk_index,
                chunks.source_reference,
                chunks.text
            FROM chunks
            JOIN documents ON documents.id = chunks.document_id
            WHERE documents.processing_status = 'processed'
            ORDER BY chunks.document_id, chunks.chunk_index
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def evaluate_expectations(expectations: list[dict], chunks: list[dict]) -> list[dict]:
    return [evaluate_expectation(expectation, chunks) for expectation in expectations]


def evaluate_expectation(expectation: dict, chunks: list[dict]) -> dict:
    source_chunks = [
        chunk
        for chunk in chunks
        if chunk["document_id"] == expectation["source_document_id"]
        and chunk["source_filename"] == expectation["source_filename"]
    ]
    extracted = extract_expected_value(expectation["field"], source_chunks)
    expected = expectation["expected_value"]

    if extracted is None:
        status = NEEDS_REVIEW
    elif values_match(expected, extracted["value"]):
        status = MATCHED
    else:
        status = FAILED

    return {
        "field": expectation["field"],
        "expected_value": expected,
        "extracted_value": extracted["value"] if extracted else None,
        "unit": expectation["unit"],
        "status": status,
        "source_filename": expectation["source_filename"],
        "source_document_id": expectation["source_document_id"],
        "chunk_id": extracted["chunk_id"] if extracted else None,
        "chunk_index": extracted["chunk_index"] if extracted else None,
        "source_reference": extracted["source_reference"] if extracted else None,
        "evidence_text": extracted["evidence_text"] if extracted else None,
        "rule": expectation["rule"],
    }


def extract_expected_value(field: str, chunks: list[dict]) -> dict | None:
    patterns = FIELD_PATTERNS.get(field, [])
    for chunk in chunks:
        for pattern in patterns:
            match = re.search(pattern, chunk["text"], flags=re.IGNORECASE | re.DOTALL)
            if match:
                raw_value = match.group("value")
                return {
                    "value": normalize_extracted_value(raw_value),
                    "chunk_id": chunk["chunk_id"],
                    "chunk_index": chunk["chunk_index"],
                    "source_reference": chunk["source_reference"],
                    "evidence_text": compact_evidence(match.group(0)),
                }
    return None


def values_match(expected: Any, extracted: Any) -> bool:
    expected_number = parse_number(expected)
    extracted_number = parse_number(extracted)
    if expected_number is not None and extracted_number is not None:
        return abs(expected_number - extracted_number) <= NUMBER_TOLERANCE
    return str(expected).strip().lower() == str(extracted).strip().lower()


def normalize_extracted_value(raw_value: str) -> int | float | str:
    number = parse_number(raw_value)
    if number is None:
        return raw_value.strip()
    return int(number) if number.is_integer() else number


def parse_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = value.replace(",", "").strip()
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
        return None
    return float(cleaned)


def compact_evidence(text_value: str) -> str:
    return re.sub(r"\s+", " ", text_value).strip()


def evaluate_validation_rules(db: Session, field_results: list[dict], chunks: list[dict]) -> list[dict]:
    extracted = {result["field"]: result["extracted_value"] for result in field_results if result["extracted_value"] is not None}
    return [
        validate_mineable_reserve(extracted),
        validate_actual_vs_target(extracted),
        validate_monthly_parliamentary_consistency(chunks),
        validate_report_sources(db),
    ]


def validate_mineable_reserve(extracted: dict) -> dict:
    inferred = parse_number(extracted.get("inferred_geological_reserve_total_mt"))
    mineable = parse_number(extracted.get("mineable_reserve_mt"))
    if inferred is None or mineable is None:
        return rule_result("mineable_reserve_not_exceed_inferred", NEEDS_REVIEW, "Could not parse inferred and mineable reserve values.")
    if mineable <= inferred:
        return rule_result(
            "mineable_reserve_not_exceed_inferred",
            PASS,
            f"Mineable reserve {mineable:g} MT is not greater than inferred geological reserve {inferred:g} MT.",
            {"inferred_geological_reserve_mt": inferred, "mineable_reserve_mt": mineable},
        )
    return rule_result(
        "mineable_reserve_not_exceed_inferred",
        FAILED,
        f"Mineable reserve {mineable:g} MT exceeds inferred geological reserve {inferred:g} MT.",
        {"inferred_geological_reserve_mt": inferred, "mineable_reserve_mt": mineable},
    )


def validate_actual_vs_target(extracted: dict) -> dict:
    target = parse_number(extracted.get("august_2026_production_target_mt"))
    actual = parse_number(extracted.get("august_2026_actual_production_mt"))
    if target is None or actual is None:
        return rule_result("actual_production_compared_with_target", NEEDS_REVIEW, "Could not parse production target and actual production.")
    variance = round(actual - target, 4)
    shortfall = round(max(target - actual, 0), 4)
    return rule_result(
        "actual_production_compared_with_target",
        PASS,
        f"Actual production {actual:g} MT compared with target {target:g} MT; variance is {variance:g} MT.",
        {"target_mt": target, "actual_mt": actual, "variance_mt": variance, "shortfall_mt": shortfall},
    )


def validate_monthly_parliamentary_consistency(chunks: list[dict]) -> dict:
    monthly_chunks = chunks_for_source(chunks, "monthly_production_report_aug_2026.txt", 19)
    parliamentary_chunks = chunks_for_source(chunks, "parliamentary_question_response.txt", 20)
    monthly_target = extract_with_patterns("august_2026_production_target_mt", monthly_chunks)
    monthly_actual = extract_with_patterns("august_2026_actual_production_mt", monthly_chunks)
    parliamentary_target = extract_with_patterns("august_2026_production_target_mt", parliamentary_chunks)
    parliamentary_actual = extract_with_patterns("august_2026_actual_production_mt", parliamentary_chunks)

    values = {
        "monthly_target_mt": monthly_target,
        "monthly_actual_mt": monthly_actual,
        "parliamentary_target_mt": parliamentary_target,
        "parliamentary_actual_mt": parliamentary_actual,
    }
    if any(value is None for value in values.values()):
        return rule_result(
            "monthly_values_match_parliamentary_response",
            NEEDS_REVIEW,
            "One or more monthly/parliamentary production values could not be parsed.",
            values,
        )
    if monthly_target == parliamentary_target and monthly_actual == parliamentary_actual:
        return rule_result(
            "monthly_values_match_parliamentary_response",
            PASS,
            "Monthly production target/actual values match the parliamentary response.",
            values,
        )
    return rule_result(
        "monthly_values_match_parliamentary_response",
        FAILED,
        "Monthly production values conflict with the parliamentary response.",
        values,
    )


def validate_report_sources(db: Session) -> dict:
    reports = db.execute(text("SELECT id, title, source_document_ids FROM reports ORDER BY id")).mappings().all()
    details = []
    for report in reports:
        source_ids = report["source_document_ids"] or []
        for document_id in source_ids:
            row = db.execute(
                text(
                    """
                    SELECT documents.id, documents.original_filename, documents.processing_status::text AS processing_status, COUNT(chunks.id) AS chunk_count
                    FROM documents
                    LEFT JOIN chunks ON chunks.document_id = documents.id
                    WHERE documents.id = :document_id
                    GROUP BY documents.id
                    """
                ),
                {"document_id": document_id},
            ).mappings().one_or_none()
            details.append(
                {
                    "report_id": report["id"],
                    "document_id": document_id,
                    "filename": row["original_filename"] if row else None,
                    "processing_status": row["processing_status"] if row else None,
                    "chunk_count": row["chunk_count"] if row else 0,
                    "exists": row is not None,
                    "valid": bool(row and row["processing_status"] == "processed" and row["chunk_count"] > 0),
                }
            )

    if not details:
        return rule_result("report_sources_exist_processed_chunked", NEEDS_REVIEW, "No report source documents were found.", details)
    invalid = [detail for detail in details if not detail["valid"]]
    if invalid:
        return rule_result(
            "report_sources_exist_processed_chunked",
            NEEDS_REVIEW,
            "One or more report source documents are missing, unprocessed, or have no chunks.",
            details,
        )
    return rule_result("report_sources_exist_processed_chunked", PASS, "Every report source document exists, is processed, and has chunks.", details)


def chunks_for_source(chunks: list[dict], filename: str, document_id: int) -> list[dict]:
    return [chunk for chunk in chunks if chunk["source_filename"] == filename and chunk["document_id"] == document_id]


def extract_with_patterns(field: str, chunks: list[dict]) -> int | float | str | None:
    extracted = extract_expected_value(field, chunks)
    return extracted["value"] if extracted else None


def rule_result(name: str, status: str, message: str, evidence: Any | None = None) -> dict:
    return {"rule": name, "status": status, "message": message, "evidence": evidence if evidence is not None else {}}


def count_statuses(results: list[dict], statuses: list[str]) -> dict:
    return {status: sum(1 for result in results if result["status"] == status) for status in statuses}
