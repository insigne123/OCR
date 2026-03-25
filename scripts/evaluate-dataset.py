from __future__ import annotations

import argparse
from collections import defaultdict
import json
import mimetypes
from pathlib import Path
from statistics import mean
import sys

sys.path.append(str((Path(__file__).resolve().parents[1] / "services" / "ocr-api").resolve()))

from app.core_env import load_runtime_env
from app.services.processing_pipeline import run_processing_pipeline


REGISTRY_PATH = Path(".data/dataset-registry.json")
FIELD_LABEL_ALIASES = {
    "numero-de-documento": "document_number",
    "numero": "document_number",
    "titular": "holder_name",
    "nombre-completo": "holder_name",
    "fecha-de-nacimiento": "birth_date",
    "fecha-de-emision": "issue_date",
    "fecha-de-vencimiento": "expiry_date",
    "sexo": "sex",
    "nacionalidad": "nationality",
    "run": "run",
    "rut": "rut",
    "direccion": "address",
    "categorias": "categories",
    "mrz": "mrz",
    "emisor": "issuer",
    "numero-de-certificado": "certificate_number",
    "cuenta": "account",
}
TABLE_COLUMN_ALIASES = {
    "periodo": "period_label",
    "renta-imponible": "renta_amount",
    "fondo-pensiones": "pension_amount",
    "codigo": "cotization_code",
    "empleador": "employer",
    "rut-empleador": "employer_rut",
    "fecha-pago": "date",
    "detalle": "detail",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate OCR pipeline against a dataset manifest.")
    parser.add_argument("manifest", help="Path to manifest.jsonl or registered dataset name")
    parser.add_argument("--output", help="Optional JSON output path")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of manifest entries")
    parser.add_argument("--group-by", default="capture_condition,family,country", help="Comma-separated dimensions to aggregate")
    parser.add_argument("--split", default=None, help="Optional dataset split filter")
    parser.add_argument("--condition", default=None, help="Optional capture condition filter")
    parser.add_argument("--visual-engine", default="auto")
    parser.add_argument("--ensemble-mode", default="always")
    parser.add_argument("--ensemble-engines", default="rapidocr,google-documentai,azure-document-intelligence")
    parser.add_argument("--field-adjudication-mode", default="auto")
    return parser.parse_args()


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _field_map(response) -> dict[str, str | None]:
    mapping: dict[str, str | None] = {}
    for field in response.fields:
        normalized_value = _normalize(field.value)
        mapping[field.field_name] = normalized_value
        alias = FIELD_LABEL_ALIASES.get(field.field_name)
        if alias:
            mapping[alias] = normalized_value
    if response.holder_name:
        mapping["holder_name"] = _normalize(response.holder_name)
    if response.issuer:
        mapping["issuer"] = _normalize(response.issuer)
    return mapping


def _extract_actual_tables(response) -> dict[str, list[dict[str, str | None]]]:
    tables: dict[str, list[dict[str, str | None]]] = {}
    for section in response.report_sections:
        if section.variant != "table" or not section.columns or not section.rows:
            continue
        if section.id != "movements":
            continue
        columns = [TABLE_COLUMN_ALIASES.get(column.strip().lower().replace(" ", "-") , column.strip().lower().replace(" ", "_")) for column in section.columns]
        rows: list[dict[str, str | None]] = []
        for row in section.rows:
            if not row or all(_normalize(cell) in {None, "-"} for cell in row):
                continue
            row_payload = {columns[index]: _normalize(row[index]) if index < len(row) else None for index in range(len(columns))}
            if row_payload.get("detail") == "Sin filas tabulares detectadas":
                continue
            period_value = row_payload.get("period_label")
            if period_value and "-" in period_value and len(period_value) == 8:
                row_payload["period"] = f"{period_value[-4:]}-{['ENE','FEB','MAR','ABR','MAY','JUN','JUL','AGO','SEP','OCT','NOV','DIC'].index(period_value[:3]) + 1:02d}" if period_value[:3] in ['ENE','FEB','MAR','ABR','MAY','JUN','JUL','AGO','SEP','OCT','NOV','DIC'] else None
            rows.append(row_payload)
        tables[section.id] = rows
    return tables


def _rows_match(expected_row: dict[str, object], actual_row: dict[str, str | None]) -> bool:
    comparable_keys = [key for key, value in expected_row.items() if value not in {None, "-", ""} and key != "detail"]
    return all(_normalize(str(expected_row.get(key) or "")) == _normalize(actual_row.get(key)) for key in comparable_keys)


def _compare_tables(expected_tables: dict[str, object], actual_tables: dict[str, list[dict[str, str | None]]]) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    for table_id, raw_rows in expected_tables.items():
        expected_rows = list(raw_rows) if isinstance(raw_rows, list) else []
        actual_rows = actual_tables.get(table_id, [])
        matched_indices: set[int] = set()
        matches = 0
        for expected_row in expected_rows:
            if not isinstance(expected_row, dict):
                continue
            found_index = next((index for index, actual_row in enumerate(actual_rows) if index not in matched_indices and _rows_match(expected_row, actual_row)), None)
            if found_index is not None:
                matched_indices.add(found_index)
                matches += 1
        total_rows = len(expected_rows)
        summary[table_id] = {
            "expected_rows": total_rows,
            "actual_rows": len(actual_rows),
            "matched_rows": matches,
            "missing_rows": max(total_rows - matches, 0),
            "extra_rows": max(len(actual_rows) - matches, 0),
            "row_match_rate": matches / total_rows if total_rows else 0.0,
        }
    return summary


def _load_registry() -> list[dict[str, object]]:
    if not REGISTRY_PATH.exists():
        return []
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _resolve_manifest_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.exists():
        return candidate
    for entry in _load_registry():
        if entry.get("name") == value and entry.get("manifest"):
            return Path(str(entry["manifest"]))
    raise FileNotFoundError(f"Dataset manifest not found: {value}")


def _stratified_limit(entries: list[dict[str, object]], limit: int | None) -> list[dict[str, object]]:
    if not limit or limit >= len(entries):
        return entries
    buckets: dict[str, list[dict[str, object]]] = defaultdict(list)
    for entry in entries:
        bucket = f"{entry.get('family')}|{entry.get('country')}|{entry.get('capture_condition')}|{entry.get('split')}"
        buckets[bucket].append(entry)

    selected: list[dict[str, object]] = []
    while len(selected) < limit and any(buckets.values()):
        for key in list(buckets.keys()):
            if not buckets[key]:
                continue
            selected.append(buckets[key].pop(0))
            if len(selected) >= limit:
                break
    return selected


def _evaluate_entry(entry: dict[str, object], root: Path, args: argparse.Namespace) -> dict[str, object]:
    file_path = root / str(entry["filename"])
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    response = run_processing_pipeline(
        file_path.read_bytes(),
        file_path.name,
        mime_type,
        str(entry.get("family") or "auto"),
        str(entry.get("country") or "AUTO"),
        "json",
        ocr_visual_engine=args.visual_engine,
        ocr_ensemble_mode=args.ensemble_mode,
        ocr_ensemble_engines=args.ensemble_engines,
        field_adjudication_mode=args.field_adjudication_mode,
    )
    actual = _field_map(response)
    expected = {key: _normalize(value if isinstance(value, str) else None) for key, value in dict(entry.get("expected_fields") or {}).items()}
    expected_tables = dict(entry.get("expected_tables") or {})
    actual_tables = _extract_actual_tables(response)
    table_comparisons = _compare_tables(expected_tables, actual_tables)
    comparable_keys = [key for key, value in expected.items() if value not in {None, "-"}]
    matched_fields = sum(1 for key in comparable_keys if actual.get(key) == expected.get(key))
    table_match_rate = (
        sum(float(table_result["row_match_rate"]) for table_result in table_comparisons.values()) / len(table_comparisons)
        if table_comparisons
        else 0.0
    )

    return {
        "filename": entry["filename"],
        "family": entry.get("family"),
        "country": entry.get("country"),
        "pack_id": entry.get("pack_id"),
        "variant": entry.get("variant"),
        "split": entry.get("split"),
        "source_dataset": entry.get("source_dataset"),
        "benchmark_profile": entry.get("benchmark_profile"),
        "capture_condition": entry.get("capture_condition"),
        "condition_tags": entry.get("condition_tags") or [],
        "decision": response.decision,
        "global_confidence": response.global_confidence,
        "matched_fields": matched_fields,
        "total_fields": len(comparable_keys),
        "exact_match_rate": matched_fields / len(comparable_keys) if comparable_keys else 0.0,
        "table_match_rate": table_match_rate,
        "table_comparisons": table_comparisons,
        "issues": [{"type": issue.type, "field": issue.field, "severity": issue.severity} for issue in response.issues],
    }


def _aggregate(results: list[dict[str, object]], key: str) -> list[dict[str, object]]:
    buckets: dict[str, list[dict[str, object]]] = {}
    for result in results:
        bucket = str(result.get(key) or "unknown")
        buckets.setdefault(bucket, []).append(result)
    summary: list[dict[str, object]] = []
    for bucket, items in sorted(buckets.items()):
        summary.append(
            {
                key: bucket,
                "documents": len(items),
                "average_confidence": round(mean(float(item["global_confidence"]) for item in items), 4),
                "exact_match_rate": round(sum(float(item["exact_match_rate"]) for item in items) / len(items), 4),
                "table_match_rate": round(sum(float(item.get("table_match_rate") or 0.0) for item in items) / len(items), 4),
                "accept_with_warning": sum(1 for item in items if item["decision"] == "accept_with_warning"),
                "human_review": sum(1 for item in items if item["decision"] == "human_review"),
                "auto_accept": sum(1 for item in items if item["decision"] == "auto_accept"),
            }
        )
    return summary


def _aggregate_many(results: list[dict[str, object]], keys: list[str]) -> dict[str, list[dict[str, object]]]:
    return {key: _aggregate(results, key) for key in keys if key}


def main() -> None:
    load_runtime_env()
    args = parse_args()
    manifest_path = _resolve_manifest_path(args.manifest)
    root = manifest_path.parent
    entries = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.split:
        entries = [entry for entry in entries if str(entry.get("split") or "") == args.split]
    if args.condition:
        entries = [entry for entry in entries if str(entry.get("capture_condition") or "") == args.condition]
    entries = _stratified_limit(entries, args.limit)

    results = [_evaluate_entry(entry, root, args) for entry in entries]
    group_keys = [part.strip() for part in args.group_by.split(",") if part.strip()]
    summary = {
        "manifest": str(manifest_path).replace("\\", "/"),
        "documents": len(results),
        "average_confidence": round(mean(float(result["global_confidence"]) for result in results), 4) if results else 0.0,
        "average_exact_match_rate": round(sum(float(result["exact_match_rate"]) for result in results) / len(results), 4) if results else 0.0,
        "average_table_match_rate": round(sum(float(result.get("table_match_rate") or 0.0) for result in results) / len(results), 4) if results else 0.0,
        "confidence_exact_gap": round(
            (
                (mean(float(result["global_confidence"]) for result in results) if results else 0.0)
                - (sum(float(result["exact_match_rate"]) for result in results) / len(results) if results else 0.0)
            ),
            4,
        ),
        "by_decision": _aggregate(results, "decision"),
        "by_condition": _aggregate(results, "capture_condition"),
        "by_family": _aggregate(results, "family"),
        "by_country": _aggregate(results, "country"),
        "by_pack": _aggregate(results, "pack_id"),
        "by_variant": _aggregate(results, "variant"),
        "straight_through_rate": round(
            sum(1 for result in results if result["decision"] in {"auto_accept", "accept_with_warning"}) / len(results),
            4,
        )
        if results
        else 0.0,
        "review_rate": round(sum(1 for result in results if result["decision"] == "human_review") / len(results), 4) if results else 0.0,
        "reject_rate": round(sum(1 for result in results if result["decision"] == "reject") / len(results), 4) if results else 0.0,
        "by_group": _aggregate_many(results, group_keys),
        "results": results,
    }
    if args.output:
        Path(args.output).write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
