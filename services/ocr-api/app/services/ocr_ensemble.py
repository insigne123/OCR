from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import os

from app.engines.azure_document_intelligence import has_azure_document_intelligence_config
from app.engines.factory import get_visual_ocr_engine
from app.engines.google_documentai import has_google_documentai_config
from app.services.document_classifier import DocumentClassification, classify_document
from app.services.layout_extraction import LayoutExtractionResult, extract_layout_from_page_texts, extract_layout_from_tokens
from app.services.visual_ocr import VisualOCRResult


DEFAULT_ENSEMBLE_MODE = "auto"
DEFAULT_LOCAL_ENGINES: tuple[str, ...] = ("rapidocr", "paddleocr", "doctr")
DEFAULT_PREMIUM_ENGINES: tuple[str, ...] = ("rapidocr", "google-documentai", "azure-document-intelligence")


@dataclass(frozen=True)
class VisualOCRRunRecord:
    engine_name: str
    source: str
    preprocess_profile: str
    page_profiles: list[str]
    success: bool
    result: VisualOCRResult | None
    average_confidence: float | None
    classification: DocumentClassification | None
    layout: LayoutExtractionResult
    score: float
    error: str | None = None


@dataclass(frozen=True)
class VisualOCREnsembleResult:
    mode: str
    runs: list[VisualOCRRunRecord]
    selected_run: VisualOCRRunRecord | None
    assumptions: list[str]


def _normalize_engine_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _parse_engine_list(value: str | None) -> list[str]:
    return [item for item in (_normalize_engine_name(part) for part in (value or "").split(",")) if item]


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        deduped.append(value)
        seen.add(value)
    return deduped


def _available_cloud_engines() -> list[str]:
    engines: list[str] = []
    if has_google_documentai_config():
        engines.append("google-documentai")
    if has_azure_document_intelligence_config():
        engines.append("azure-document-intelligence")
    return engines


def resolve_visual_ocr_engine_names(
    selected_engine: str | None = None,
    ensemble_mode: str | None = None,
    ensemble_engines: str | None = None,
) -> tuple[str, list[str]]:
    requested = _normalize_engine_name(selected_engine or os.getenv("OCR_VISUAL_ENGINE", "rapidocr")) or "rapidocr"
    configured_mode = _normalize_engine_name(ensemble_mode or os.getenv("OCR_ENSEMBLE_MODE", DEFAULT_ENSEMBLE_MODE)) or DEFAULT_ENSEMBLE_MODE
    mode = configured_mode if configured_mode in {"single", "auto", "always"} else DEFAULT_ENSEMBLE_MODE
    configured_engines = _parse_engine_list(ensemble_engines if ensemble_engines is not None else os.getenv("OCR_ENSEMBLE_ENGINES"))

    if configured_engines:
        names: list[str] = configured_engines
    elif requested != "auto" and mode != "always":
        names = [requested]
    else:
        cloud_engines = _available_cloud_engines()
        names = list(DEFAULT_PREMIUM_ENGINES if cloud_engines else DEFAULT_LOCAL_ENGINES)
        if not cloud_engines:
            names = list(DEFAULT_LOCAL_ENGINES)
        if requested != "auto":
            names.insert(0, requested)

    resolved_names = _dedupe([name for name in names if name])
    if mode == "single" and resolved_names:
        resolved_names = resolved_names[:1]

    effective_mode = "ensemble" if len(resolved_names) > 1 else "single"
    return effective_mode, resolved_names or [requested]


def _average_confidence(result: VisualOCRResult | None) -> float | None:
    if not result or not result.tokens:
        return None
    return sum(token.confidence for token in result.tokens) / len(result.tokens)


def _empty_layout(engine_name: str) -> LayoutExtractionResult:
    return LayoutExtractionResult(engine=engine_name, lines=[], key_value_pairs=[], table_candidate_rows=[])


def _score_visual_run(run: VisualOCRRunRecord) -> float:
    if not run.success or not run.result or not run.result.text.strip():
        return 0.0

    classification = run.classification
    tokens = run.result.tokens
    text_length = len(run.result.text.strip())
    score = 0.0

    if classification:
        score += classification.confidence * 0.52
        if classification.supported:
            score += 0.32

    if run.average_confidence is not None:
        score += run.average_confidence * 0.1

    score += min(len(tokens), 240) / 240.0 * 0.03
    score += min(text_length, 6000) / 6000.0 * 0.03
    return round(score, 6)


def _build_run_record(
    engine_name: str,
    result: VisualOCRResult | None,
    requested_family: str,
    requested_country: str,
    preprocess_profile: str = "original",
    page_profiles: list[str] | None = None,
    error: str | None = None,
) -> VisualOCRRunRecord:
    average_confidence = _average_confidence(result)
    classification = classify_document(result.text, requested_family, requested_country) if result and result.text.strip() else None

    if result and result.tokens:
        layout = extract_layout_from_tokens(result.tokens, engine=f"{result.source}-layout")
    elif result and any(page_text.strip() for page_text in result.page_texts):
        layout = extract_layout_from_page_texts(result.page_texts, engine=f"{result.source}-layout")
    elif result and result.text.strip():
        layout = extract_layout_from_page_texts([result.text], engine=f"{result.source}-layout")
    else:
        layout = _empty_layout(engine_name)

    draft = VisualOCRRunRecord(
        engine_name=engine_name,
        source=(f"{result.source}@{preprocess_profile}" if result and preprocess_profile != "original" else (result.source if result else engine_name)),
        preprocess_profile=preprocess_profile,
        page_profiles=page_profiles or [],
        success=bool(result and result.text.strip()),
        result=result,
        average_confidence=average_confidence,
        classification=classification,
        layout=layout,
        score=0.0,
        error=error,
    )
    return VisualOCRRunRecord(
        engine_name=draft.engine_name,
        source=draft.source,
        preprocess_profile=draft.preprocess_profile,
        page_profiles=draft.page_profiles,
        success=draft.success,
        result=draft.result,
        average_confidence=draft.average_confidence,
        classification=draft.classification,
        layout=draft.layout,
        score=_score_visual_run(draft),
        error=draft.error,
    )


def _run_single_engine(
    engine_name: str,
    images: list[bytes],
    requested_family: str,
    requested_country: str,
    preprocess_profile: str = "original",
    page_profiles: list[str] | None = None,
) -> VisualOCRRunRecord:
    error: str | None = None
    result = None
    try:
        result = get_visual_ocr_engine(engine_name).run(images)
    except Exception as exc:  # noqa: BLE001
        error = str(exc)

    return _build_run_record(
        engine_name,
        result,
        requested_family,
        requested_country,
        preprocess_profile=preprocess_profile,
        page_profiles=page_profiles,
        error=error,
    )


def _selection_reason(selected_run: VisualOCRRunRecord) -> str:
    if not selected_run.classification:
        return f"Se selecciono {selected_run.source} por mejor score OCR ({selected_run.score:.3f})."

    classification = selected_run.classification
    support_label = "pack soportado" if classification.supported else "pack no soportado"
    return (
        f"Se selecciono {selected_run.source} por mejor score OCR ({selected_run.score:.3f}), "
        f"clasificacion {classification.document_family}/{classification.country} ({classification.confidence:.2f}, {support_label})."
    )


def run_visual_ocr_ensemble(
    images: list[bytes],
    requested_engine: str | None,
    requested_family: str,
    requested_country: str,
    ensemble_mode: str | None = None,
    ensemble_engines: str | None = None,
    preprocess_profile: str = "original",
    page_profiles: list[str] | None = None,
) -> VisualOCREnsembleResult:
    if not images:
        return VisualOCREnsembleResult(mode="single", runs=[], selected_run=None, assumptions=[])

    mode, engine_names = resolve_visual_ocr_engine_names(
        requested_engine,
        ensemble_mode=ensemble_mode,
        ensemble_engines=ensemble_engines,
    )
    runs: list[VisualOCRRunRecord] = []

    if len(engine_names) == 1:
        runs.append(
            _run_single_engine(
                engine_names[0],
                images,
                requested_family,
                requested_country,
                preprocess_profile=preprocess_profile,
                page_profiles=page_profiles,
            )
        )
    else:
        with ThreadPoolExecutor(max_workers=min(len(engine_names), 4)) as executor:
            future_map = {
                executor.submit(
                    _run_single_engine,
                    engine_name,
                    images,
                    requested_family,
                    requested_country,
                    preprocess_profile,
                    page_profiles,
                ): engine_name
                for engine_name in engine_names
            }
            for future in as_completed(future_map):
                runs.append(future.result())

        run_order = {engine_name: index for index, engine_name in enumerate(engine_names)}
        runs.sort(key=lambda run: run_order.get(run.engine_name, len(engine_names)))

    selected_run = max(runs, key=lambda run: (run.score, run.success, len(run.result.tokens) if run.result else 0, len(run.result.text) if run.result else 0), default=None)
    if selected_run and selected_run.score <= 0:
        selected_run = None

    assumptions: list[str] = []
    if len(engine_names) > 1:
        assumptions.append(f"OCR ensemble ejecutado con {', '.join(engine_names)} sobre perfil {preprocess_profile}.")
    elif engine_names:
        assumptions.append(f"OCR visual ejecutado con {engine_names[0]} sobre perfil {preprocess_profile}.")

    if selected_run:
        assumptions.append(_selection_reason(selected_run))
    else:
        assumptions.append("Ningun engine OCR genero evidencia visual suficiente para seleccion automatica.")

    return VisualOCREnsembleResult(mode=mode, runs=runs, selected_run=selected_run, assumptions=assumptions)
