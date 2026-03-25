# pyright: reportMissingImports=false

from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "services" / "ocr-api"))

from app.core_env import load_runtime_env
from app.services.processing_pipeline import run_processing_pipeline


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".pdf", ".heic", ".heif", ".tif", ".tiff", ".webp", ".avif"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local OCR batch over a folder of real documents.")
    parser.add_argument("folder", help="Folder with images/PDFs to process")
    parser.add_argument("--pattern", default="*", help="Optional glob pattern inside folder, e.g. 'IMG_08*.HEIC'")
    parser.add_argument("--limit", type=int, default=None, help="Optional file limit after filtering")
    parser.add_argument("--output-json", help="Path to write JSON results")
    parser.add_argument("--output-csv", help="Path to write CSV results")
    parser.add_argument("--visual-engine", default="rapidocr", help="rapidocr|paddleocr|doctr|azure-document-intelligence|google-documentai|auto")
    parser.add_argument("--structured-mode", default="heuristic", help="heuristic|auto|openai")
    parser.add_argument("--ensemble-mode", default=None, help="single|auto|always")
    parser.add_argument("--ensemble-engines", default=None, help="Comma-separated OCR engines for ensemble mode")
    parser.add_argument("--field-adjudication-mode", default=None, help="off|deterministic|openai|auto")
    return parser.parse_args()


def detect_mime_type(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    return mime_type or "application/octet-stream"


def summarize_issue_types(response) -> list[str]:
    return [issue.type for issue in response.issues[:5]]


def run_file(path: Path) -> dict[str, object]:
    mime_type = detect_mime_type(path)
    response = run_processing_pipeline(
        path.read_bytes(),
        path.name,
        mime_type,
        "auto",
        "AUTO",
        "json",
        ocr_visual_engine=os.getenv("OCR_VISUAL_ENGINE", "rapidocr"),
        decision_profile=os.getenv("OCR_DEFAULT_DECISION_PROFILE", "balanced"),
        ocr_ensemble_mode=os.getenv("OCR_ENSEMBLE_MODE") or None,
        ocr_ensemble_engines=os.getenv("OCR_ENSEMBLE_ENGINES") or None,
        field_adjudication_mode=os.getenv("OCR_FIELD_ADJUDICATION_MODE") or None,
    )
    return {
        "file": str(path.name),
        "mime_type": mime_type,
        "status": "ok",
        "document_family": response.document_family,
        "country": response.country,
        "variant": response.variant,
        "decision": response.decision,
        "global_confidence": response.global_confidence,
        "review_required": response.review_required,
        "page_count": response.page_count,
        "processing_engine": response.processing.engine if response.processing else None,
        "extraction_source": response.processing.extraction_source if response.processing else None,
        "issue_types": summarize_issue_types(response),
    }


def aggregate(results: list[dict[str, object]]) -> dict[str, object]:
    ok_results = [result for result in results if result["status"] == "ok"]
    by_decision = Counter(result["decision"] for result in ok_results)
    by_family = Counter(result["document_family"] for result in ok_results)
    by_country = Counter(result["country"] for result in ok_results)
    average_confidence = (
        sum(float(result["global_confidence"]) if isinstance(result["global_confidence"], (int, float)) else 0.0 for result in ok_results) / len(ok_results)
        if ok_results
        else 0.0
    )
    return {
        "total_files": len(results),
        "processed_ok": len(ok_results),
        "failed": len(results) - len(ok_results),
        "average_confidence": round(average_confidence, 4),
        "by_decision": dict(by_decision),
        "by_family": dict(by_family),
        "by_country": dict(by_country),
        "unsupported_or_review": sum(1 for result in ok_results if result["decision"] in {"human_review", "reject"}),
    }


def _issue_types_to_csv(value: object) -> object:
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    return value


def write_csv(path: Path, results: list[dict[str, object]]) -> None:
    fieldnames = [
        "file",
        "mime_type",
        "status",
        "document_family",
        "country",
        "variant",
        "decision",
        "global_confidence",
        "review_required",
        "page_count",
        "processing_engine",
        "extraction_source",
        "issue_types",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow({**result, "issue_types": _issue_types_to_csv(result.get("issue_types"))})


def main() -> None:
    args = parse_args()
    load_runtime_env()
    os.environ["OCR_VISUAL_ENGINE"] = args.visual_engine
    os.environ["OCR_STRUCTURED_NORMALIZER_MODE"] = args.structured_mode
    if args.ensemble_mode:
        os.environ["OCR_ENSEMBLE_MODE"] = args.ensemble_mode
    if args.ensemble_engines:
        os.environ["OCR_ENSEMBLE_ENGINES"] = args.ensemble_engines
    if args.field_adjudication_mode:
        os.environ["OCR_FIELD_ADJUDICATION_MODE"] = args.field_adjudication_mode

    folder = Path(args.folder)
    files = sorted(path for path in folder.rglob(args.pattern) if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES and not path.name.startswith("_batch_results"))
    if args.limit:
        files = files[: args.limit]
    results: list[dict[str, object]] = []

    for path in files:
        try:
            results.append(run_file(path))
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "file": str(path.name),
                    "mime_type": detect_mime_type(path),
                    "status": "error",
                    "document_family": None,
                    "country": None,
                    "variant": None,
                    "decision": None,
                    "global_confidence": None,
                    "review_required": None,
                    "page_count": None,
                    "processing_engine": None,
                    "extraction_source": None,
                    "issue_types": [],
                    "error": str(exc),
                }
            )

    payload = {
        "config": {
            "folder": str(folder),
            "pattern": args.pattern,
            "limit": args.limit,
            "visual_engine": args.visual_engine,
            "structured_mode": args.structured_mode,
            "ensemble_mode": args.ensemble_mode,
            "ensemble_engines": args.ensemble_engines,
            "field_adjudication_mode": args.field_adjudication_mode,
        },
        "summary": aggregate(results),
        "results": results,
    }

    output_json = Path(args.output_json) if args.output_json else folder / "_batch_results.json"
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    output_csv = Path(args.output_csv) if args.output_csv else folder / "_batch_results.csv"
    write_csv(output_csv, results)

    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))
    print(f"JSON: {output_json}")
    print(f"CSV: {output_csv}")


if __name__ == "__main__":
    main()
