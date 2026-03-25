from __future__ import annotations

import os

from app.core.feature_flags import feature_flags_snapshot
from app.core.contracts import NormalizerEngine, VisualOCREngine
from app.engines.azure_document_intelligence import AzureDocumentIntelligenceOCREngine, has_azure_document_intelligence_config
from app.engines.doctr_ocr import DocTRVisualOCREngine
from app.engines.google_documentai import GoogleDocumentAIOCREngine, has_google_documentai_config
from app.engines.normalizers import HeuristicNormalizerEngine, OpenAINormalizerEngine
from app.engines.ocr import CompositeVisualOCREngine, RapidVisualOCREngine
from app.engines.paddle_ocr import PaddleVisualOCREngine
from app.services.openai_normalizer import has_openai_config


def get_visual_ocr_engine(selected_engine: str | None = None) -> VisualOCREngine:
    configured = (selected_engine or os.getenv("OCR_VISUAL_ENGINE", "rapidocr")).strip().lower()

    if configured == "rapidocr":
        return RapidVisualOCREngine()
    if configured == "paddleocr":
        return PaddleVisualOCREngine()
    if configured == "doctr":
        return DocTRVisualOCREngine()
    if configured == "azure-document-intelligence":
        return AzureDocumentIntelligenceOCREngine()
    if configured == "google-documentai":
        return GoogleDocumentAIOCREngine()

    engines: list[VisualOCREngine] = [PaddleVisualOCREngine(), RapidVisualOCREngine(), DocTRVisualOCREngine()]
    if has_azure_document_intelligence_config():
        engines.append(AzureDocumentIntelligenceOCREngine())
    if has_google_documentai_config():
        engines.append(GoogleDocumentAIOCREngine())

    return CompositeVisualOCREngine(engines)


def get_visual_ocr_runtime_details(selected_engine: str | None = None) -> dict[str, object]:
    return {
        "selected": (selected_engine or os.getenv("OCR_VISUAL_ENGINE", "rapidocr")).strip().lower(),
        "structured_normalizer_mode": get_structured_normalizer_mode(),
        "openai_configured": has_openai_config(),
        "azure_document_intelligence_configured": has_azure_document_intelligence_config(),
        "google_documentai_configured": has_google_documentai_config(),
        "feature_flags": feature_flags_snapshot(),
        "available": [
            "rapidocr",
            "paddleocr",
            "doctr",
            "azure-document-intelligence",
            "google-documentai",
            "auto",
        ],
    }


def get_structured_normalizer_mode() -> str:
    mode = os.getenv("OCR_STRUCTURED_NORMALIZER_MODE", "auto").strip().lower()
    return mode if mode in {"heuristic", "openai", "auto"} else "auto"


def get_structured_normalizer_engine() -> NormalizerEngine:
    mode = get_structured_normalizer_mode()
    if mode == "openai" and has_openai_config():
        return OpenAINormalizerEngine()
    if mode == "auto" and has_openai_config():
        return OpenAINormalizerEngine()
    return HeuristicNormalizerEngine()


def get_heuristic_normalizer_engine() -> NormalizerEngine:
    return HeuristicNormalizerEngine()
