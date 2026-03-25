from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "test-data" / "_triplet_regression_report.json"
REFERENCE_FILES = [
    ROOT / "test-data" / "response_IMG_0841.jpeg.json",
    ROOT / "test-data" / "response_IMG_0842.jpeg.json",
    ROOT / "test-data" / "response_AFP.pdf.json",
]
MIN_CONFIDENCE = {
    "IMG_0841.jpeg": 0.99,
    "IMG_0842.jpeg": 0.99,
    "AFP.pdf": 0.97,
}
EXPECTED_FAMILY = {
    "IMG_0841.jpeg": "identity",
    "IMG_0842.jpeg": "driver_license",
    "AFP.pdf": "certificate",
}


def run_reference_compare() -> dict[str, object]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "compare-reference-ocr.py"),
        *[str(path) for path in REFERENCE_FILES],
        "--output",
        str(REPORT_PATH),
        "--visual-engine",
        "auto",
        "--ensemble-mode",
        "always",
        "--ensemble-engines",
        "rapidocr,google-documentai,azure-document-intelligence",
        "--field-adjudication-mode",
        "auto",
    ]
    subprocess.run(command, check=True, cwd=ROOT)
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def main() -> None:
    payload = run_reference_compare()
    reports = payload.get("reports", []) if isinstance(payload, dict) else []
    failures: list[str] = []

    for report in reports:
        image = str(report.get("image"))
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        table_comparisons = report.get("table_comparisons") if isinstance(report.get("table_comparisons"), dict) else {}
        confidence = float(report.get("global_confidence") or 0.0)
        family = str(report.get("document_family") or "")

        if family != EXPECTED_FAMILY.get(image):
            failures.append(f"{image}: familia inesperada {family!r}")
        if confidence + 1e-9 < MIN_CONFIDENCE.get(image, 0.0):
            failures.append(f"{image}: confianza {confidence:.4f} bajo umbral {MIN_CONFIDENCE[image]:.4f}")
        if int(summary.get("mismatches", 0)) > 0:
            failures.append(f"{image}: hay mismatches contra referencia")
        if int(summary.get("missing", 0)) > 0:
            failures.append(f"{image}: faltan campos respecto a referencia")

        if image == "AFP.pdf":
            movement_summary = table_comparisons.get("movements") if isinstance(table_comparisons.get("movements"), dict) else {}
            if float(movement_summary.get("row_match_rate", 0.0)) < 1.0:
                failures.append("AFP.pdf: las filas de cotizaciones de referencia no coincidieron al 100%")

    result = {
        "report_path": str(REPORT_PATH),
        "reports": reports,
        "failures": failures,
        "ok": len(failures) == 0,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
