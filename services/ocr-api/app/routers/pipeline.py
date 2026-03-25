import os
import json

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

from app.engines.factory import get_visual_ocr_engine
from app.engines.factory import get_visual_ocr_runtime_details
from app.schemas import (
    ClassifyResponse,
    ClassifySegment,
    CustomExtractionResponse,
    ExtractRequest,
    ExtractResponse,
    NormalizeRequest,
    NormalizeResponse,
    PreprocessResponse,
    ProcessResponse,
    QualityAnalysisResponse,
    SplitResponse,
    TableExtractionResponse,
    ValidateRequest,
    ValidateResponse,
)
from app.services.custom_extraction import extract_custom_fields
from app.services.document_classifier import classify_document
from app.services.processing_pipeline import run_processing_pipeline
from app.services.heuristic_normalizer import normalize_text_with_heuristics
from app.services.stage_services import extract_from_source_text, normalize_field_map, preprocess_document_input, split_document_input, validate_field_map
from app.services.table_extraction import build_table_extraction_response
from app.services.text_extraction import extract_document_text
from app.services.layout_extraction import LayoutExtractionResult, extract_layout_from_page_texts, extract_layout_from_tokens
from app.services.page_preprocessing import prepare_document_pages
from app.services.document_splitter import split_document_pages


router = APIRouter()


def _extract_source_context(file_bytes: bytes, filename: str, content_type: str | None) -> tuple[str, list[str], LayoutExtractionResult]:
    extraction = extract_document_text(file_bytes, filename, content_type)
    source_text = extraction.text
    page_texts = extraction.page_texts
    layout = extract_layout_from_page_texts(page_texts, engine="embedded-text-layout") if any(page.strip() for page in page_texts) else LayoutExtractionResult(engine="none", lines=[], key_value_pairs=[], table_candidate_rows=[])

    if source_text.strip():
        return source_text, page_texts, layout

    try:
        prepared_pages = prepare_document_pages(file_bytes, filename, content_type, extraction.page_texts)
    except Exception:
        prepared_pages = []

    if not prepared_pages:
        return source_text, page_texts, layout

    visual_ocr = get_visual_ocr_engine().run([page.image_bytes for page in prepared_pages])
    visual_text = getattr(visual_ocr, "text", "")
    if visual_text.strip():
        source_text = visual_text
        page_texts = getattr(visual_ocr, "page_texts", [])
        visual_tokens = getattr(visual_ocr, "tokens", [])
        visual_source = getattr(visual_ocr, "source", "visual-ocr")
        layout = extract_layout_from_tokens(visual_tokens, engine=f"{visual_source}-layout") if visual_tokens else extract_layout_from_page_texts(page_texts, engine=f"{visual_source}-layout")

    return source_text, page_texts, layout


def _parse_custom_schema(raw_schema: str) -> dict[str, dict[str, str]]:
    try:
        parsed = json.loads(raw_schema)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail=f"Invalid schema JSON: {error.msg}") from error

    if not isinstance(parsed, dict) or not parsed:
        raise HTTPException(status_code=400, detail="Schema must be a non-empty JSON object.")

    normalized: dict[str, dict[str, str]] = {}
    for field_name, config in parsed.items():
        if not isinstance(field_name, str) or not field_name.strip():
            raise HTTPException(status_code=400, detail="Schema field names must be non-empty strings.")
        if not isinstance(config, dict):
            raise HTTPException(status_code=400, detail=f"Schema field '{field_name}' must be an object.")
        normalized[field_name] = {
            "type": str(config.get("type") or "string"),
            "description": str(config.get("description") or ""),
        }
    return normalized


def _flatten_report_sections(report_sections) -> dict[str, str]:
    values: dict[str, str] = {}
    for section in report_sections:
        if section.variant == "pairs" and section.rows:
            for row in section.rows:
                if row:
                    values[row[0]] = row[1] if len(row) > 1 else ""
        elif section.variant == "table" and section.columns and section.rows:
            if len(section.columns) == 2 and section.columns[0].lower() == "campo":
                for row in section.rows:
                    if row:
                        values[row[0]] = row[1] if len(row) > 1 else ""
        elif section.variant == "text" and section.body:
            values[section.title] = section.body
    return values


def _normalize_supported_document(classification, filename: str, source_text: str):
    if not classification.supported:
        return None
    if classification.document_family not in {"identity", "certificate", "passport", "driver_license"}:
        return None
    if not source_text.strip():
        return None
    return normalize_text_with_heuristics(
        classification.document_family,
        classification.country,
        filename,
        source_text,
        assumptions=[f"Fast supported normalization for {classification.document_family}/{classification.country}."],
        variant=classification.variant,
        pack_id=classification.pack_id,
        document_side=classification.document_side,
    )


def _ensure_api_key(x_api_key: str | None) -> None:
    expected = os.getenv("OCR_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing OCR API key")


@router.get("/health")
async def healthcheck() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "ocr-api",
        "ocr_runtime": get_visual_ocr_runtime_details(),
        "webhook_configured": bool(os.getenv("OCR_RESULT_WEBHOOK_URL")),
    }


@router.post("/process", response_model=ProcessResponse)
async def process_document(
    file: UploadFile = File(...),
    document_family: str = Form("auto"),
    country: str = Form("AUTO"),
    response_mode: str = Form("json"),
    ocr_visual_engine: str | None = Form(default=None),
    decision_profile: str | None = Form(default=None),
    tenant_id: str | None = Form(default=None),
    ocr_structured_mode: str | None = Form(default=None),
    ocr_ensemble_mode: str | None = Form(default=None),
    ocr_ensemble_engines: str | None = Form(default=None),
    field_adjudication_mode: str | None = Form(default=None),
    x_api_key: str | None = Header(default=None),
) -> ProcessResponse:
    _ensure_api_key(x_api_key)
    file_bytes = await file.read()
    resolved_response_mode = "full" if response_mode == "full" else "json"
    return run_processing_pipeline(
        file_bytes,
        file.filename or "documento.pdf",
        file.content_type,
        document_family,
        country,
        resolved_response_mode,
        ocr_visual_engine=ocr_visual_engine,
        decision_profile=decision_profile,
        tenant_id=tenant_id,
        structured_mode_override=ocr_structured_mode,
        ocr_ensemble_mode=ocr_ensemble_mode,
        ocr_ensemble_engines=ocr_ensemble_engines,
        field_adjudication_mode=field_adjudication_mode,
    )


@router.post("/preprocess", response_model=PreprocessResponse)
async def preprocess_document(file: UploadFile = File(...), x_api_key: str | None = Header(default=None)) -> PreprocessResponse:
    _ensure_api_key(x_api_key)
    file_bytes = await file.read()
    result = preprocess_document_input(file_bytes, file.filename or "documento.pdf", file.content_type)
    return PreprocessResponse(
        blur_score=result.blur_score,
        glare_score=result.glare_score,
        orientation=result.orientation,
        page_count=result.page_count,
        has_embedded_text=result.has_embedded_text,
        extraction_source=result.extraction_source,
        warnings=result.warnings,
        pages=result.pages,
        quality_assessment=result.quality_assessment,
    )


@router.post("/analyze/quality", response_model=QualityAnalysisResponse)
async def analyze_quality(file: UploadFile = File(...), x_api_key: str | None = Header(default=None)) -> QualityAnalysisResponse:
    _ensure_api_key(x_api_key)
    file_bytes = await file.read()
    result = preprocess_document_input(file_bytes, file.filename or "documento.pdf", file.content_type)
    return QualityAnalysisResponse(
        page_count=result.page_count,
        has_embedded_text=result.has_embedded_text,
        extraction_source=result.extraction_source,
        warnings=result.warnings,
        pages=result.pages,
        quality_assessment=result.quality_assessment,
    )


@router.post("/classify", response_model=ClassifyResponse)
async def classify_uploaded_document(
    file: UploadFile = File(...),
    document_family: str = Form("auto"),
    country: str = Form("AUTO"),
    x_api_key: str | None = Header(default=None),
) -> ClassifyResponse:
    _ensure_api_key(x_api_key)
    file_bytes = await file.read()
    source_text, page_texts, _ = _extract_source_context(file_bytes, file.filename or "documento.pdf", file.content_type)
    classification = classify_document(source_text, document_family, country)
    split = split_document_pages(page_texts or ([source_text] if source_text.strip() else []), document_family, country)
    return ClassifyResponse(
        document_family=classification.document_family,
        country=classification.country,
        variant=classification.variant,
        pack_id=classification.pack_id,
        pack_version=classification.pack_version,
        document_side=classification.document_side,
        confidence=classification.confidence,
        supported=classification.supported,
        reasons=classification.reasons,
        multi_document=split.mixed_detected and len(split.segments) > 1,
        segments=[
            ClassifySegment(
                start_page=segment.start_page,
                end_page=segment.end_page,
                page_numbers=segment.page_numbers,
                document_family=segment.document_family,
                country=segment.country,
                variant=segment.variant,
                pack_id=segment.pack_id,
                document_side=segment.document_side,
                confidence=segment.confidence,
                supported=segment.supported,
            )
            for segment in split.segments
        ],
    )


@router.post("/extract", response_model=ExtractResponse)
async def extract_document(payload: ExtractRequest, x_api_key: str | None = Header(default=None)) -> ExtractResponse:
    _ensure_api_key(x_api_key)
    result = extract_from_source_text(payload.source_text, payload.document_family, payload.country, payload.filename)
    return ExtractResponse(
        fields_detected=result.fields_detected,
        candidate_sections=result.candidate_sections,
        engine=result.engine,
        layout_engine=result.layout_engine,
        line_count=result.line_count,
        key_value_pairs=result.key_value_pairs,
        table_candidate_rows=result.table_candidate_rows,
        document_family=result.document_family,
        country=result.country,
        variant=result.variant,
        pack_id=result.pack_id,
        supported=result.supported,
    )


@router.post("/split", response_model=SplitResponse)
async def split_document(
    file: UploadFile = File(...),
    document_family: str = Form("mixed"),
    country: str = Form("AUTO"),
    x_api_key: str | None = Header(default=None),
) -> SplitResponse:
    _ensure_api_key(x_api_key)
    file_bytes = await file.read()
    result = split_document_input(file_bytes, file.filename or "documento.pdf", file.content_type, document_family, country)
    return SplitResponse(
        page_count=result.page_count,
        mixed_detected=result.mixed_detected,
        assumptions=result.assumptions,
        segments=result.segments,
    )


@router.post("/extract/tables", response_model=TableExtractionResponse)
async def extract_document_tables(
    file: UploadFile = File(...),
    document_family: str = Form("auto"),
    country: str = Form("AUTO"),
    output_format: str = Form("json"),
    x_api_key: str | None = Header(default=None),
) -> TableExtractionResponse:
    _ensure_api_key(x_api_key)
    file_bytes = await file.read()
    source_text, page_texts, layout = _extract_source_context(file_bytes, file.filename or "documento.pdf", file.content_type)
    classification = classify_document(source_text, document_family, country)
    normalized = _normalize_supported_document(classification, file.filename or "documento.pdf", source_text)
    if normalized is not None:
        report_sections = normalized.report_sections
        variant = normalized.variant
        pack_id = classification.pack_id
    else:
        processed = run_processing_pipeline(
            file_bytes,
            file.filename or "documento.pdf",
            file.content_type,
            classification.document_family,
            classification.country,
            response_mode="json",
        )
        report_sections = processed.report_sections
        variant = processed.variant
        pack_id = processed.document.pack_id if processed.document else classification.pack_id
    return build_table_extraction_response(
        document_family=classification.document_family,
        country=classification.country,
        variant=variant,
        pack_id=pack_id,
        report_sections=report_sections,
        layout=layout if layout.lines else extract_layout_from_page_texts(page_texts or [source_text], engine="text-layout"),
        output_format="csv" if output_format.lower() == "csv" else "json",
    )


@router.post("/extract/custom", response_model=CustomExtractionResponse)
async def extract_custom_document_fields(
    file: UploadFile = File(...),
    custom_schema: str = Form(..., alias="schema_json"),
    document_family: str = Form("unclassified"),
    country: str = Form("AUTO"),
    x_api_key: str | None = Header(default=None),
) -> CustomExtractionResponse:
    _ensure_api_key(x_api_key)
    schema = _parse_custom_schema(custom_schema)
    file_bytes = await file.read()
    source_text, _, layout = _extract_source_context(file_bytes, file.filename or "documento.pdf", file.content_type)
    classification = classify_document(source_text, document_family, country)
    normalized = _normalize_supported_document(classification, file.filename or "documento.pdf", source_text)
    fields = extract_custom_fields(
        schema=schema,
        source_text=source_text,
        layout=layout,
        classification=classification,
        known_values=_flatten_report_sections(normalized.report_sections) if normalized is not None else None,
    )
    return CustomExtractionResponse(
        document_family=classification.document_family,
        country=classification.country,
        supported_classification=classification.supported,
        fields=fields,
        assumptions=[
            "Experimental custom extraction matched schema fields against OCR/layout evidence.",
            f"Classification context: {classification.document_family}/{classification.country}.",
        ],
    )


@router.post("/normalize", response_model=NormalizeResponse)
async def normalize_document(payload: NormalizeRequest, x_api_key: str | None = Header(default=None)) -> NormalizeResponse:
    _ensure_api_key(x_api_key)
    result = normalize_field_map(payload.fields, payload.document_family, payload.country, payload.filename, payload.variant)
    return NormalizeResponse(
        normalized_fields=result.normalized_fields,
        inferred_fields=result.inferred_fields,
        warnings=result.warnings,
        variant=result.variant,
        engine=result.engine,
    )


@router.post("/validate", response_model=ValidateResponse)
async def validate_document(payload: ValidateRequest, x_api_key: str | None = Header(default=None)) -> ValidateResponse:
    _ensure_api_key(x_api_key)
    evaluation = validate_field_map(
        document_family=payload.document_family,
        country=payload.country,
        variant=payload.variant,
        pack_id=payload.pack_id,
        tenant_id=payload.tenant_id,
        normalized_fields=payload.normalized_fields,
        classification_confidence=payload.classification_confidence,
        document_side=payload.document_side,
        decision_profile=payload.decision_profile,
    )
    return ValidateResponse(
        decision=evaluation.decision,
        issues=evaluation.issues,
        rule_pack_id=evaluation.rule_pack_id,
        review_required=evaluation.review_required,
    )
