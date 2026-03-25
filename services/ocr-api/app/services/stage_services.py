from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from app.engines.factory import get_visual_ocr_engine
from app.schemas import LayoutKeyValueCandidate, ProcessPageInfo, QualityAssessment, SplitSegmentInfo
from app.services.quality_analysis import build_quality_assessment
from app.services.document_classifier import classify_document
from app.services.document_packs import normalize_requested_country, normalize_requested_family
from app.services.document_splitter import split_document_pages
from app.services.heuristic_normalizer import normalize_text_with_heuristics
from app.services.layout_extraction import extract_layout_from_page_texts
from app.services.page_preprocessing import prepare_document_pages
from app.services.rule_packs import evaluate_normalized_fields
from app.services.text_extraction import extract_document_text
from app.services.visual_pages import render_pdf_pages_to_png_bytes


@dataclass(frozen=True)
class PreprocessStageResult:
    blur_score: float
    glare_score: float
    orientation: int
    page_count: int
    has_embedded_text: bool
    extraction_source: str
    warnings: list[str]
    pages: list[ProcessPageInfo]
    quality_assessment: QualityAssessment


@dataclass(frozen=True)
class ExtractStageResult:
    document_family: str
    country: str
    variant: str | None
    pack_id: str | None
    supported: bool
    fields_detected: int
    candidate_sections: list[str]
    engine: str
    layout_engine: str
    line_count: int
    key_value_pairs: list[LayoutKeyValueCandidate]
    table_candidate_rows: list[str]


@dataclass(frozen=True)
class NormalizeStageResult:
    normalized_fields: dict[str, str]
    inferred_fields: list[str]
    warnings: list[str]
    variant: str | None
    engine: str


@dataclass(frozen=True)
class SplitStageResult:
    page_count: int
    mixed_detected: bool
    assumptions: list[str]
    segments: list[SplitSegmentInfo]


def _flatten_report_sections(report_sections) -> dict[str, str]:
    values: dict[str, str] = {}
    for section in report_sections:
        if section.variant == "pairs" and section.rows:
            for row in section.rows:
                if not row:
                    continue
                values[row[0]] = row[1] if len(row) > 1 else ""
        if section.variant == "table" and section.columns and section.rows:
            if len(section.columns) == 2 and section.columns[0].lower() == "campo":
                for row in section.rows:
                    if not row:
                        continue
                    values[row[0]] = row[1] if len(row) > 1 else ""
        if section.variant == "text" and section.body:
            values[section.title] = section.body
    return values


def preprocess_document_input(file_bytes: bytes, filename: str, content_type: str | None) -> PreprocessStageResult:
    extraction = extract_document_text(file_bytes, filename, content_type)
    suffix = Path(filename).suffix.lower()
    mime_type = (content_type or "").lower()
    try:
        prepared_pages = prepare_document_pages(file_bytes, filename, content_type, extraction.page_texts)
    except Exception:
        prepared_pages = []
    rendered_pages = [page.image_bytes for page in prepared_pages]

    if not rendered_pages and not extraction.text:
        if mime_type == "application/pdf" or suffix == ".pdf":
            try:
                rendered_pages = render_pdf_pages_to_png_bytes(file_bytes)
            except Exception:
                rendered_pages = []
        elif mime_type.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".heic", ".heif", ".tif", ".tiff"}:
            rendered_pages = [file_bytes]

    enable_visual_probe = os.getenv("OCR_PREPROCESS_VISUAL_PROBE", "false").lower() == "true"
    visual_ocr = get_visual_ocr_engine().run(rendered_pages[:1]) if rendered_pages and enable_visual_probe else None
    avg_ocr_confidence = (
        sum(token.confidence for token in visual_ocr.tokens) / len(visual_ocr.tokens)
        if visual_ocr and visual_ocr.tokens
        else None
    )

    if prepared_pages:
        blur_score = round(sum(page.blur_score for page in prepared_pages) / len(prepared_pages), 3)
        glare_score = round(sum(page.glare_score for page in prepared_pages) / len(prepared_pages), 3)
    elif avg_ocr_confidence is not None:
        blur_score = round(max(0.08, 1 - avg_ocr_confidence), 3)
        glare_score = round(0.12 if avg_ocr_confidence >= 0.7 else 0.26, 3)
    else:
        blur_score = 0.46
        glare_score = 0.34

    warnings: list[str] = []
    if not extraction.text:
        warnings.append("No se detecto texto embebido; se recomienda OCR visual o multimodal.")
    if avg_ocr_confidence is not None and avg_ocr_confidence < 0.72:
        warnings.append("El OCR visual tiene confidence media baja; conviene revisar calidad y recorte.")
    elif prepared_pages and any(page.quality_score < 0.62 for page in prepared_pages):
        warnings.append("La calidad visual estimada es baja; conviene revisar calidad y recorte antes de procesar.")
    if not rendered_pages and not extraction.text:
        warnings.append("No fue posible generar paginas o imagenes derivadas para quality scoring profundo.")
    if any(page.rescue_profiles for page in prepared_pages):
        warnings.append("Se detectaron condiciones de captura movil complejas; se activaron perfiles de rescate de imagen.")
    if any(page.perspective_applied or page.skew_applied for page in prepared_pages):
        warnings.append("Se aplicaron correcciones geometricas (perspective/skew) en al menos una pagina.")

    pages = [
        ProcessPageInfo(
            page_number=page.page_number,
            width=page.width,
            height=page.height,
            orientation=page.orientation,
            quality_score=page.quality_score,
            blur_score=page.blur_score,
            glare_score=page.glare_score,
            crop_ratio=page.crop_ratio,
            document_coverage=page.document_coverage,
            edge_confidence=page.edge_confidence,
            skew_angle=page.skew_angle,
            skew_applied=page.skew_applied,
            perspective_applied=page.perspective_applied,
            capture_conditions=page.capture_conditions,
            rescue_profiles=page.rescue_profiles,
            selected_ocr_profile=None,
            corners=page.corners,
            has_embedded_text=page.has_embedded_text,
        )
        for page in prepared_pages
    ]

    return PreprocessStageResult(
        blur_score=blur_score,
        glare_score=glare_score,
        orientation=prepared_pages[0].orientation if prepared_pages else 0,
        page_count=max(extraction.page_count, len(rendered_pages) or 0, 1),
        has_embedded_text=bool(extraction.text),
        extraction_source=visual_ocr.source if visual_ocr and visual_ocr.text else extraction.source,
        warnings=warnings,
        pages=pages,
        quality_assessment=build_quality_assessment(pages, warnings),
    )


def extract_from_source_text(source_text: str, requested_family: str, requested_country: str, filename: str) -> ExtractStageResult:
    classification = classify_document(source_text, requested_family, requested_country)
    page_texts = [source_text] if source_text.strip() else []
    layout = extract_layout_from_page_texts(page_texts)
    key_value_pairs = [
        LayoutKeyValueCandidate(label=pair.label, value=pair.value, page_number=pair.page_number, raw_line=pair.raw_line)
        for pair in layout.key_value_pairs[:20]
    ]

    if classification.supported and classification.document_family in {"identity", "certificate", "passport", "driver_license"} and source_text.strip():
        normalized = normalize_text_with_heuristics(
            classification.document_family,
            classification.country,
            filename,
            source_text,
            assumptions=[f"Clasificacion automatica: {classification.document_family}/{classification.country}"],
            variant=classification.variant,
            pack_id=classification.pack_id,
            document_side=classification.document_side,
        )
        candidate_sections = [section.id for section in normalized.report_sections]
        if key_value_pairs and "layout-kv" not in candidate_sections:
            candidate_sections.append("layout-kv")
        if layout.table_candidate_rows and "layout-table" not in candidate_sections:
            candidate_sections.append("layout-table")
        fields_detected = max(len(_flatten_report_sections(normalized.report_sections)), len(key_value_pairs))
        engine = "heuristic-extract"
    else:
        candidate_sections = ["summary"] if classification.document_family == "unclassified" else ["summary"]
        if key_value_pairs:
            candidate_sections.append("layout-kv")
        if layout.table_candidate_rows:
            candidate_sections.append("layout-table")
        fields_detected = len(key_value_pairs)
        engine = "classifier-only"

    return ExtractStageResult(
        document_family=classification.document_family,
        country=classification.country,
        variant=classification.variant,
        pack_id=classification.pack_id,
        supported=classification.supported,
        fields_detected=fields_detected,
        candidate_sections=candidate_sections,
        engine=engine,
        layout_engine=layout.engine,
        line_count=len(layout.lines),
        key_value_pairs=key_value_pairs,
        table_candidate_rows=layout.table_candidate_rows[:20],
    )


def normalize_field_map(fields: dict[str, str], document_family: str, country: str, filename: str, variant: str | None = None) -> NormalizeStageResult:
    normalized_family = normalize_requested_family(document_family)
    normalized_country = normalize_requested_country(country)
    synthetic_text = "\n".join(f"{key}: {value}" for key, value in fields.items())

    if normalized_family in {"identity", "certificate", "passport", "driver_license"} and synthetic_text.strip():
        normalized = normalize_text_with_heuristics(
            normalized_family,
            normalized_country,
            filename,
            synthetic_text,
            assumptions=["Se reconstruyo texto a partir de campos planos para normalizarlo heuristica y canonicamente."],
            variant=variant,
            document_side="back" if variant and "-back-" in variant else ("front+back" if variant and "front-back" in variant else None),
        )
        normalized_fields = _flatten_report_sections(normalized.report_sections)
        warnings = [issue.message for issue in normalized.issues]
        inferred_fields = [label for label, value in normalized_fields.items() if value in {"-", "NO DETECTADO", "NO DETECTADA"}]
        return NormalizeStageResult(
            normalized_fields=normalized_fields,
            inferred_fields=inferred_fields,
            warnings=warnings,
            variant=normalized.variant,
            engine="heuristic-normalize",
        )

    stripped = {key: value.strip() for key, value in fields.items()}
    return NormalizeStageResult(
        normalized_fields=stripped,
        inferred_fields=[],
        warnings=["No existe normalizador heuristico para esta familia; se devolvieron campos saneados en plano."],
        variant=variant,
        engine="flat-normalize",
    )


def validate_field_map(
    document_family: str,
    country: str,
    normalized_fields: dict[str, str],
    variant: str | None = None,
    pack_id: str | None = None,
    tenant_id: str | None = None,
    classification_confidence: float | None = None,
    document_side: str | None = None,
    decision_profile: str | None = None,
):
    return evaluate_normalized_fields(
        document_family=document_family,
        country=normalize_requested_country(country),
        variant=variant,
        normalized_fields=normalized_fields,
        pack_id=pack_id,
        tenant_id=tenant_id,
        classification_confidence=classification_confidence,
        document_side=document_side,
        decision_profile=decision_profile,
    )


def split_document_input(file_bytes: bytes, filename: str, content_type: str | None, requested_family: str, requested_country: str) -> SplitStageResult:
    extraction = extract_document_text(file_bytes, filename, content_type)
    page_texts = extraction.page_texts

    if not any((page or "").strip() for page in page_texts):
        try:
            prepared_pages = prepare_document_pages(file_bytes, filename, content_type, extraction.page_texts)
        except Exception:
            prepared_pages = []
        visual_ocr = get_visual_ocr_engine().run([page.image_bytes for page in prepared_pages]) if prepared_pages else None
        page_texts = visual_ocr.page_texts if visual_ocr else []

    split = split_document_pages(page_texts, requested_family, requested_country)
    return SplitStageResult(
        page_count=split.page_count,
        mixed_detected=split.mixed_detected,
        assumptions=split.assumptions,
        segments=[
            SplitSegmentInfo(
                segment_id=segment.segment_id,
                start_page=segment.start_page,
                end_page=segment.end_page,
                page_numbers=segment.page_numbers,
                document_family=segment.document_family,
                country=segment.country,
                variant=segment.variant,
                pack_id=segment.pack_id,
                document_side=segment.document_side,
                supported=segment.supported,
                confidence=segment.confidence,
                summary=segment.summary,
            )
            for segment in split.segments
        ],
    )
