# pyright: reportMissingImports=false

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "services" / "ocr-api"))

from app.core_env import load_runtime_env
from app.engines.azure_document_intelligence import AzureDocumentIntelligenceOCREngine, has_azure_document_intelligence_config
from app.engines.google_documentai import GoogleDocumentAIOCREngine, has_google_documentai_config
from app.engines.factory import get_visual_ocr_runtime_details


def _sample_image() -> bytes | None:
    repo_root = Path(__file__).resolve().parents[1]
    explicit = os.getenv("OCR_VALIDATION_SAMPLE")
    candidates = [Path(explicit)] if explicit else []
    candidates.extend(repo_root.glob("*.png"))
    candidates.extend(repo_root.glob("*.jpg"))
    candidates.extend(repo_root.glob("*.jpeg"))

    for candidate in candidates:
        if candidate and candidate.exists() and candidate.is_file():
            return candidate.read_bytes()
    return None


def _validate_engine(name: str, configured: bool, engine) -> dict[str, object]:
    if not configured:
        return {"configured": False, "validated": False}

    sample = _sample_image()
    if not sample:
        return {"configured": True, "validated": False, "reason": "No sample image found"}

    try:
        result = engine.run([sample])
    except Exception as exc:  # noqa: BLE001
        return {"configured": True, "validated": False, "error": str(exc)}

    return {
        "configured": True,
        "validated": bool(result and result.text),
        "page_count": result.page_count if result else 0,
        "source": result.source if result else None,
        "text_preview": (result.text[:120] if result and result.text else None),
    }


def main() -> None:
    load_runtime_env()
    output = {
        "runtime": get_visual_ocr_runtime_details(),
        "azure": _validate_engine("azure", has_azure_document_intelligence_config(), AzureDocumentIntelligenceOCREngine()),
        "google": _validate_engine("google", has_google_documentai_config(), GoogleDocumentAIOCREngine()),
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
