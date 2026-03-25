from typing import Any, Literal

from pydantic import BaseModel, Field


DocumentDecision = Literal["pending", "auto_accept", "accept_with_warning", "human_review", "reject"]
ReportSectionVariant = Literal["pairs", "table", "text"]
ValidationSeverity = Literal["low", "medium", "high"]
ResponseMode = Literal["json", "full"]
RiskLevel = Literal["low", "medium", "high"]


class ReportSection(BaseModel):
    id: str
    title: str
    variant: ReportSectionVariant
    columns: list[str] | None = None
    rows: list[list[str]] | None = None
    body: str | None = None
    note: str | None = None


class ValidationIssue(BaseModel):
    id: str
    type: str
    field: str
    severity: ValidationSeverity
    message: str
    suggestedAction: str


class ProcessPageInfo(BaseModel):
    page_number: int
    image_path: str | None = None
    image_base64: str | None = None
    width: int | None = None
    height: int | None = None
    orientation: int = 0
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    blur_score: float | None = Field(default=None, ge=0.0, le=1.0)
    glare_score: float | None = Field(default=None, ge=0.0, le=1.0)
    crop_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    document_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    edge_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    skew_angle: float | None = None
    skew_applied: bool = False
    perspective_applied: bool = False
    capture_conditions: list[str] = []
    rescue_profiles: list[str] = []
    selected_ocr_profile: str | None = None
    corners: list[list[float]] = []
    has_embedded_text: bool = False


class LayoutKeyValueCandidate(BaseModel):
    label: str
    value: str
    page_number: int = 1
    raw_line: str


class OCRTokenInfo(BaseModel):
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    bbox: list[list[float]]
    page_number: int = 1


class OCRRunPageInfo(BaseModel):
    page_number: int
    text: str = ""
    token_count: int = 0
    average_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rescue_profile: str | None = None


class OCRRunInfo(BaseModel):
    engine: str
    source: str
    success: bool
    selected: bool = False
    score: float = 0.0
    page_count: int = 0
    text: str = ""
    average_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    classification_family: str | None = None
    classification_country: str | None = None
    classification_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    supported_classification: bool = False
    preprocess_profile: str = "original"
    assumptions: list[str] = []
    pages: list[OCRRunPageInfo] = []
    tokens: list[OCRTokenInfo] = []
    key_value_pairs: list[LayoutKeyValueCandidate] = []
    table_candidate_rows: list[str] = []


class ProcessingTraceEntry(BaseModel):
    stage: str
    status: str = "completed"
    started_at: str
    finished_at: str
    duration_ms: float = Field(default=0.0, ge=0.0)
    summary: str = ""


class FieldCandidateResult(BaseModel):
    engine: str
    source: str
    value: str | None = None
    raw_text: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    page_number: int = 1
    bbox: dict[str, float] | None = None
    evidence_text: str | None = None
    selected: bool = False
    match_type: str = "unknown"
    score: float = Field(default=0.0, ge=0.0, le=1.0)


class FieldConsensusResult(BaseModel):
    engines_considered: int = 0
    candidate_count: int = 0
    supporting_engines: list[str] = []
    agreement_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    disagreement: bool = False


class FieldAdjudicationResult(BaseModel):
    method: str = "deterministic"
    abstained: bool = False
    selected_value: str | None = None
    selected_source: str | None = None
    selected_engine: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str = ""
    evidence_sources: list[str] = []


class ConfidenceDetails(BaseModel):
    final: float = Field(ge=0.0, le=1.0)
    ocr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    normalization_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    validation_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    consensus_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    integrity_score: float | None = Field(default=None, ge=0.0, le=1.0)
    issue_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: list[str] = []


class IntegrityIndicator(BaseModel):
    code: str
    severity: ValidationSeverity
    source: str
    message: str


class IntegrityAssessment(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    indicators: list[IntegrityIndicator] = []
    checks: dict[str, bool | float | None] = {}


class QualityAssessment(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    blur_score: float | None = Field(default=None, ge=0.0, le=1.0)
    glare_score: float | None = Field(default=None, ge=0.0, le=1.0)
    crop_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    document_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    orientation: int | None = None
    capture_conditions: list[str] = []
    recommendations: list[str] = []


class SplitSegmentInfo(BaseModel):
    segment_id: str
    start_page: int
    end_page: int
    page_numbers: list[int]
    document_family: str
    country: str
    variant: str | None = None
    pack_id: str | None = None
    document_side: str | None = None
    supported: bool = True
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str


class ProcessDocumentInfo(BaseModel):
    family: str
    country: str
    variant: str | None = None
    pack_id: str | None = None
    pack_version: str | None = None
    document_side: str | None = None
    issuer: str | None = None
    holder_name: str | None = None


class ProcessMetadata(BaseModel):
    request_id: str
    response_mode: ResponseMode = "json"
    page_count: int = 1
    engine: str
    extraction_source: str
    selected_visual_engine: str | None = None
    ensemble_mode: str | None = None
    decision_profile: str | None = None
    requested_visual_engine: str | None = None
    classification_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    global_confidence: float = Field(ge=0.0, le=1.0)
    decision: DocumentDecision
    review_required: bool
    processed_at: str
    ocr_runs: list[OCRRunInfo] = []
    adjudication_mode: str | None = None
    adjudicated_fields: int = 0
    adjudication_abstentions: int = 0
    processing_trace: list[ProcessingTraceEntry] = []
    confidence_details: ConfidenceDetails | None = None
    integrity_assessment: IntegrityAssessment | None = None
    quality_assessment: QualityAssessment | None = None


class ExtractedFieldResult(BaseModel):
    id: str
    section: str
    field_name: str
    label: str
    value: str | None = None
    raw_text: str | None = None
    value_type: str = "text"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    engine: str = "heuristic"
    page_number: int = 1
    issue_ids: list[str] = []
    bbox: dict[str, float] | None = None
    evidence: dict[str, Any] | None = None
    candidates: list[FieldCandidateResult] = []
    consensus: FieldConsensusResult | None = None
    adjudication: FieldAdjudicationResult | None = None
    confidence_details: ConfidenceDetails | None = None


class ProcessResponse(BaseModel):
    request_id: str = ""
    response_mode: ResponseMode = "json"
    document: ProcessDocumentInfo | None = None
    processing: ProcessMetadata | None = None
    fields: list[ExtractedFieldResult] = []
    pages: list[ProcessPageInfo] = []
    document_family: str
    country: str
    variant: str | None = None
    issuer: str | None = None
    holder_name: str | None = None
    page_count: int = 1
    global_confidence: float = Field(ge=0.0, le=1.0)
    decision: DocumentDecision
    review_required: bool
    assumptions: list[str]
    issues: list[ValidationIssue]
    report_sections: list[ReportSection]
    human_summary: str | None = None
    report_html: str | None = None


class NormalizedDocument(BaseModel):
    document_family: str
    country: str
    variant: str | None = None
    issuer: str | None = None
    holder_name: str | None = None
    global_confidence: float = Field(ge=0.0, le=1.0)
    assumptions: list[str]
    issues: list[ValidationIssue]
    report_sections: list[ReportSection]
    human_summary: str | None = None


class PreprocessResponse(BaseModel):
    blur_score: float
    glare_score: float
    orientation: int
    page_count: int
    has_embedded_text: bool = False
    extraction_source: str = "binary-no-text"
    warnings: list[str] = []
    pages: list[ProcessPageInfo] = []
    quality_assessment: QualityAssessment | None = None


class ExtractRequest(BaseModel):
    document_family: str = "unclassified"
    country: str = "XX"
    filename: str = "documento.pdf"
    source_text: str = ""


class ExtractResponse(BaseModel):
    fields_detected: int
    candidate_sections: list[str]
    engine: str
    layout_engine: str = "text-layout"
    line_count: int = 0
    key_value_pairs: list[LayoutKeyValueCandidate] = []
    table_candidate_rows: list[str] = []
    document_family: str
    country: str
    variant: str | None = None
    pack_id: str | None = None
    supported: bool = True


class NormalizeRequest(BaseModel):
    document_family: str = "unclassified"
    country: str = "XX"
    variant: str | None = None
    filename: str = "documento.txt"
    fields: dict[str, str]


class NormalizeResponse(BaseModel):
    normalized_fields: dict[str, str]
    inferred_fields: list[str]
    warnings: list[str]
    variant: str | None = None
    engine: str = "heuristic-normalize"


class ValidateRequest(BaseModel):
    document_family: str
    country: str = "XX"
    variant: str | None = None
    pack_id: str | None = None
    tenant_id: str | None = None
    document_side: str | None = None
    decision_profile: str | None = None
    classification_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    normalized_fields: dict[str, str]


class ValidateResponse(BaseModel):
    decision: DocumentDecision
    issues: list[ValidationIssue]
    rule_pack_id: str | None = None
    review_required: bool = False


class SplitResponse(BaseModel):
    page_count: int
    mixed_detected: bool
    assumptions: list[str]
    segments: list[SplitSegmentInfo]


class ClassifySegment(BaseModel):
    start_page: int
    end_page: int
    page_numbers: list[int]
    document_family: str
    country: str
    variant: str | None = None
    pack_id: str | None = None
    document_side: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    supported: bool = True


class ClassifyResponse(BaseModel):
    document_family: str
    country: str
    variant: str | None = None
    pack_id: str | None = None
    pack_version: str | None = None
    document_side: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    supported: bool = True
    reasons: list[str] = []
    multi_document: bool = False
    segments: list[ClassifySegment] = []


class TableCell(BaseModel):
    row_index: int
    column_index: int
    value: str


class TableExtractionResult(BaseModel):
    table_id: str
    title: str
    headers: list[str] = []
    rows: list[list[str]] = []
    cells: list[TableCell] = []
    confidence: float = Field(ge=0.0, le=1.0)
    source: str = "layout-table"
    format_hint: str = "json"


class TableExtractionResponse(BaseModel):
    document_family: str
    country: str
    variant: str | None = None
    pack_id: str | None = None
    tables: list[TableExtractionResult] = []
    csv: str | None = None
    assumptions: list[str] = []


class CustomExtractionSchemaField(BaseModel):
    type: str = "string"
    description: str = ""


class CustomExtractionFieldResult(BaseModel):
    field_name: str
    value: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_text: str | None = None
    page_number: int = 1
    source: str = "experimental-zero-shot"
    reasoning: str = ""


class CustomExtractionResponse(BaseModel):
    document_family: str
    country: str
    supported_classification: bool = False
    fields: list[CustomExtractionFieldResult] = []
    assumptions: list[str] = []


class QualityAnalysisResponse(BaseModel):
    page_count: int
    has_embedded_text: bool = False
    extraction_source: str = "binary-no-text"
    warnings: list[str] = []
    pages: list[ProcessPageInfo] = []
    quality_assessment: QualityAssessment
