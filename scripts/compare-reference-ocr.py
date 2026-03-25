from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path
import sys

sys.path.append(str((Path(__file__).resolve().parents[1] / "services" / "ocr-api").resolve()))

from app.core_env import load_runtime_env
from app.services.field_value_utils import compact, parse_passport_mrz, strip_accents
from app.services.processing_pipeline import run_processing_pipeline

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".avif", ".pdf"}
CERTIFICATE_TABLE_COLUMNS = {
    "Periodo": "period_label",
    "Renta imponible": "renta_amount",
    "Fondo pensiones": "pension_amount",
    "Codigo": "cotization_code",
    "Empleador": "employer",
    "RUT empleador": "employer_rut",
    "Fecha pago": "date",
    "Detalle": "detail",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare OCR output against reference professional OCR JSON.")
    parser.add_argument("references", nargs="+", help="Reference JSON paths, usually named JSON_<image>.json")
    parser.add_argument("--output", help="Optional JSON report path")
    parser.add_argument("--visual-engine", default="auto")
    parser.add_argument("--ensemble-mode", default="always")
    parser.add_argument("--ensemble-engines", default="rapidocr,google-documentai,azure-document-intelligence")
    parser.add_argument("--field-adjudication-mode", default="auto")
    return parser.parse_args()


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(strip_accents(value).upper().split())
    return cleaned or None


def _normalize_date(value: str | None) -> str | None:
    cleaned = _normalize(value)
    return cleaned


def _field_map(response) -> dict[str, str | None]:
    mapping: dict[str, str | None] = {}
    for field in response.fields:
        mapping[field.label] = field.value
    return mapping


def _derive_holder_parts(holder_name: str | None) -> tuple[str | None, str | None]:
    if not holder_name:
        return None, None
    parts = holder_name.split()
    if len(parts) >= 3:
        return " ".join(parts[:-2]), " ".join(parts[-2:])
    if len(parts) == 2:
        return parts[0], parts[1]
    return holder_name, None


def _extract_reference(reference: dict[str, object]) -> dict[str, str | None]:
    if reference.get("expected_fields"):
        expected_fields = reference.get("expected_fields") if isinstance(reference.get("expected_fields"), dict) else {}
        return {
            "document_family": str(reference.get("family") or expected_fields.get("document_family") or "certificate"),
            **{str(key): (str(value) if value is not None else None) for key, value in expected_fields.items()},
        }

    raw_fields = reference.get("fields")
    fields = raw_fields if isinstance(raw_fields, dict) else {}
    if "document_number" in fields or "document_type" in fields:
        mrz_fields = (((fields.get("mrz") or {}).get("fields") or {}) if isinstance(fields.get("mrz"), dict) else {})
        line_1 = (((mrz_fields.get("line_1") or {}).get("value")) if isinstance(mrz_fields.get("line_1"), dict) else None)
        line_2 = (((mrz_fields.get("line_2") or {}).get("value")) if isinstance(mrz_fields.get("line_2"), dict) else None)
        return {
            "document_family": "passport",
            "document_number": ((fields.get("document_number") or {}).get("value") if isinstance(fields.get("document_number"), dict) else None),
            "surnames": ((fields.get("surnames") or {}).get("value") if isinstance(fields.get("surnames"), dict) else None),
            "given_names": ((fields.get("given_names") or {}).get("value") if isinstance(fields.get("given_names"), dict) else None),
            "holder_name": " ".join(part for part in [((fields.get("given_names") or {}).get("value") if isinstance(fields.get("given_names"), dict) else None), ((fields.get("surnames") or {}).get("value") if isinstance(fields.get("surnames"), dict) else None)] if part) or None,
            "nationality": ((fields.get("nationality") or {}).get("value") if isinstance(fields.get("nationality"), dict) else None),
            "sex": ((fields.get("sex") or {}).get("value") if isinstance(fields.get("sex"), dict) else None),
            "birth_date": ((fields.get("date_of_birth") or {}).get("value") if isinstance(fields.get("date_of_birth"), dict) else None),
            "issue_date": ((fields.get("date_of_issue") or {}).get("value") if isinstance(fields.get("date_of_issue"), dict) else None),
            "expiry_date": ((fields.get("date_of_expiry") or {}).get("value") if isinstance(fields.get("date_of_expiry"), dict) else None),
            "authority": ((fields.get("authority") or {}).get("value") if isinstance(fields.get("authority"), dict) else None),
            "place_of_birth": ((fields.get("place_of_birth") or {}).get("value") if isinstance(fields.get("place_of_birth"), dict) else None),
            "mrz_line_1": line_1,
            "mrz_line_2": line_2,
        }

    address = fields.get("address") if isinstance(fields.get("address"), dict) else {}
    street = ((address.get("fields") or {}).get("street") or {}).get("value") if isinstance(address, dict) else None
    first_name = ((fields.get("first_name") or {}).get("value") if isinstance(fields.get("first_name"), dict) else None)
    last_name = ((fields.get("last_name") or {}).get("value") if isinstance(fields.get("last_name"), dict) else None)
    category = ((fields.get("category") or {}).get("value") if isinstance(fields.get("category"), dict) else None)
    if category or street:
        return {
            "document_family": "driver_license",
            "document_number": ((fields.get("document_id") or {}).get("value") if isinstance(fields.get("document_id"), dict) else None),
            "first_name": first_name,
            "last_name": last_name,
            "holder_name": " ".join(part for part in [first_name, last_name] if part) or None,
            "category": category,
            "expiry_date": ((fields.get("expiry_date") or {}).get("value") if isinstance(fields.get("expiry_date"), dict) else None),
            "issued_date": ((fields.get("issued_date") or {}).get("value") if isinstance(fields.get("issued_date"), dict) else None),
            "issuing_authority": ((fields.get("issuing_authority") or {}).get("value") if isinstance(fields.get("issuing_authority"), dict) else None),
            "address": street,
            "nationality": ((fields.get("nationality") or {}).get("value") if isinstance(fields.get("nationality"), dict) else None),
        }

    return {
        "document_family": "identity",
        "document_number": ((fields.get("document_id") or {}).get("value") if isinstance(fields.get("document_id"), dict) else None),
        "first_name": first_name,
        "last_name": last_name,
        "holder_name": " ".join(part for part in [first_name, last_name] if part) or None,
        "expiry_date": ((fields.get("expiry_date") or {}).get("value") if isinstance(fields.get("expiry_date"), dict) else None),
        "issued_date": ((fields.get("issued_date") or {}).get("value") if isinstance(fields.get("issued_date"), dict) else None),
        "issuing_authority": ((fields.get("issuing_authority") or {}).get("value") if isinstance(fields.get("issuing_authority"), dict) else None),
        "birth_date": ((fields.get("date_of_birth") or {}).get("value") if isinstance(fields.get("date_of_birth"), dict) else None),
        "sex": ((fields.get("sex") or {}).get("value") if isinstance(fields.get("sex"), dict) else None),
        "nationality": ((fields.get("nationality") or {}).get("value") if isinstance(fields.get("nationality"), dict) else None),
    }


def _extract_actual(response) -> dict[str, str | None]:
    values = _field_map(response)
    if response.document_family == "certificate":
        return {
            "document_family": response.document_family,
            "holder_name": response.holder_name or values.get("Titular") or values.get("Nombre completo"),
            "rut": values.get("RUT"),
            "certificate_number": values.get("Numero de certificado"),
            "issue_date": values.get("Fecha de emision"),
            "account": values.get("Cuenta"),
            "issuer": response.issuer or values.get("Emisor"),
        }

    if response.document_family == "passport":
        given_names = values.get("Nombres")
        surnames = values.get("Apellidos")
        if (not given_names or "NO DETECT" in given_names.upper()) and response.holder_name:
            given_names, _ = _derive_holder_parts(response.holder_name)
        if (not surnames or "NO DETECT" in surnames.upper()) and response.holder_name:
            _, surnames = _derive_holder_parts(response.holder_name)
        mrz = values.get("MRZ")
        parsed_mrz = parse_passport_mrz(mrz or "") if mrz else {"mrz": None, "document_number": None}
        mrz_lines = (mrz or "").splitlines()
        return {
            "document_family": response.document_family,
            "document_number": values.get("Numero de documento") or values.get("Numero") or parsed_mrz.get("document_number"),
            "given_names": given_names,
            "surnames": surnames,
            "holder_name": response.holder_name or values.get("Nombre completo") or values.get("Titular"),
            "nationality": values.get("Nacionalidad"),
            "sex": values.get("Sexo"),
            "birth_date": values.get("Fecha de nacimiento"),
            "issue_date": values.get("Fecha de emision"),
            "expiry_date": values.get("Fecha de vencimiento"),
            "authority": response.issuer or values.get("Autoridad"),
            "place_of_birth": values.get("Lugar de nacimiento"),
            "mrz_line_1": mrz_lines[0] if mrz_lines else None,
            "mrz_line_2": mrz_lines[1] if len(mrz_lines) > 1 else None,
        }

    if response.document_family == "driver_license":
        return {
            "document_family": response.document_family,
            "document_number": values.get("Numero de documento") or values.get("Numero"),
            "first_name": values.get("Primer nombre"),
            "last_name": values.get("Apellidos"),
            "holder_name": response.holder_name or values.get("Nombre completo") or values.get("Titular"),
            "category": values.get("Categorias"),
            "expiry_date": values.get("Fecha de vencimiento"),
            "issued_date": values.get("Fecha de emision"),
            "issuing_authority": response.issuer or values.get("Autoridad emisora"),
            "address": values.get("Direccion"),
            "nationality": values.get("Nacionalidad"),
        }

    return {
        "document_family": response.document_family,
        "document_number": values.get("Numero de documento") or values.get("Numero"),
        "first_name": values.get("Nombres"),
        "last_name": values.get("Apellidos"),
        "holder_name": response.holder_name or values.get("Nombre completo") or values.get("Titular"),
        "run": values.get("RUN"),
        "expiry_date": values.get("Fecha de vencimiento"),
        "issued_date": values.get("Fecha de emision"),
        "issuing_authority": response.issuer or values.get("Autoridad emisora") or values.get("Autoridad") or values.get("Emisor"),
        "birth_date": values.get("Fecha de nacimiento"),
        "birth_place": values.get("Lugar de nacimiento"),
        "sex": values.get("Sexo"),
        "nationality": values.get("Nacionalidad"),
    }


def _extract_actual_tables(response) -> dict[str, list[dict[str, str | None]]]:
    tables: dict[str, list[dict[str, str | None]]] = {}
    for section in response.report_sections:
        if section.id != "movements" or section.variant != "table" or not section.columns or not section.rows:
            continue
        rows: list[dict[str, str | None]] = []
        for row in section.rows:
            if not row:
                continue
            row_payload = {
                CERTIFICATE_TABLE_COLUMNS.get(column, column): row[index] if index < len(row) else None
                for index, column in enumerate(section.columns)
            }
            if row_payload.get("detail") == "Sin filas tabulares detectadas":
                continue
            rows.append(row_payload)
        tables[section.id] = rows
    return tables


def _rows_match(expected_row: dict[str, object], actual_row: dict[str, str | None]) -> bool:
    keys = [key for key, value in expected_row.items() if value not in {None, "", "-"} and key != "detail"]
    return all(compact(str(expected_row.get(key) or "")) == compact(actual_row.get(key)) for key in keys)


def _compare_tables(reference_payload: dict[str, object], response) -> dict[str, dict[str, object]]:
    raw_expected_tables = reference_payload.get("expected_tables") if isinstance(reference_payload.get("expected_tables"), dict) else {}
    actual_tables = _extract_actual_tables(response)
    summary: dict[str, dict[str, object]] = {}
    for table_id, raw_rows in raw_expected_tables.items():
        expected_rows = raw_rows if isinstance(raw_rows, list) else []
        actual_rows = actual_tables.get(str(table_id), [])
        matches = 0
        consumed: set[int] = set()
        for expected_row in expected_rows:
            if not isinstance(expected_row, dict):
                continue
            found = next((index for index, actual_row in enumerate(actual_rows) if index not in consumed and _rows_match(expected_row, actual_row)), None)
            if found is not None:
                consumed.add(found)
                matches += 1
        summary[str(table_id)] = {
            "expected_rows": len(expected_rows),
            "actual_rows": len(actual_rows),
            "matched_rows": matches,
            "row_match_rate": matches / len(expected_rows) if expected_rows else 0.0,
        }
    return summary


def _resolve_source_image(reference_path: Path) -> Path | None:
    original_name = reference_path.name.replace("JSON_", "", 1).replace(".json", "")
    if reference_path.name.startswith("response_"):
        original_name = reference_path.name.replace("response_", "", 1).replace(".json", "")
    direct = reference_path.parent / original_name
    if direct.exists():
        return direct

    stem = Path(original_name).stem
    candidates = sorted(
        path for path in reference_path.parent.iterdir() if path.is_file() and path.stem == stem and path.suffix.lower() in IMAGE_SUFFIXES
    )
    return candidates[0] if candidates else None


def _compare(reference_fields: dict[str, str | None], actual_fields: dict[str, str | None]) -> list[dict[str, object]]:
    comparisons: list[dict[str, object]] = []
    all_keys = [key for key in reference_fields.keys() if key != "document_family"]
    for key in all_keys:
        expected = reference_fields.get(key)
        actual = actual_fields.get(key)
        if expected is None and actual is None:
            status = "both_missing"
        elif expected is None:
            status = "extra"
        elif actual is None:
            status = "missing"
        elif compact(expected) == compact(actual):
            status = "match"
        else:
            status = "mismatch"
        comparisons.append({"field": key, "status": status, "expected": expected, "actual": actual})
    return comparisons


def main() -> None:
    load_runtime_env()
    args = parse_args()
    reports: list[dict[str, object]] = []
    for reference_path_str in args.references:
        reference_path = Path(reference_path_str)
        reference_payload = json.loads(reference_path.read_text(encoding="utf-8"))
        image_path = _resolve_source_image(reference_path)
        image_name = image_path.name if image_path else reference_path.name.replace("JSON_", "", 1).replace(".json", "")
        if image_path is None:
            reports.append(
                {
                    "image": image_name,
                    "reference": str(reference_path).replace("\\", "/"),
                    "error": "matching_source_image_not_found",
                }
            )
            continue
        mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        response = run_processing_pipeline(
            image_path.read_bytes(),
            image_path.name,
            mime_type,
            "auto",
            "AUTO",
            "json",
            ocr_visual_engine=args.visual_engine,
            ocr_ensemble_mode=args.ensemble_mode,
            ocr_ensemble_engines=args.ensemble_engines,
            field_adjudication_mode=args.field_adjudication_mode,
        )
        reference_fields = _extract_reference(reference_payload)
        actual_fields = _extract_actual(response)
        comparisons = _compare(reference_fields, actual_fields)
        table_comparisons = _compare_tables(reference_payload, response)
        reports.append(
            {
                "image": image_name,
                "reference": str(reference_path).replace("\\", "/"),
                "document_family": response.document_family,
                "decision": response.decision,
                "global_confidence": response.global_confidence,
                "summary": {
                    "matches": sum(1 for item in comparisons if item["status"] == "match"),
                    "mismatches": sum(1 for item in comparisons if item["status"] == "mismatch"),
                    "missing": sum(1 for item in comparisons if item["status"] == "missing"),
                },
                "table_comparisons": table_comparisons,
                "comparisons": comparisons,
            }
        )

    payload = {"reports": reports}
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
