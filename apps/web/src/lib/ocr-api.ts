import type { ConfidenceDetails, DocumentDecision, DocumentPageRecord, DocumentRecord, ExtractedField, FieldAdjudication, IntegrityAssessment, OcrRunSummary, QualityAssessment, ReportSection, ValidationIssue, ValidationStatus, ReviewStatus } from "@ocr/shared";
import { readDocumentBinary } from "./document-store";
import { getOcrApiUrl, getOptionalOcrApiKey } from "./ocr-config";
import { resolveTenantProcessingOptions } from "./tenant-processing";

type RemoteField = {
  id: string;
  section: string;
  field_name: string;
  label: string;
  value: string | null;
  raw_text: string | null;
  value_type: string;
  confidence: number | null;
  engine?: string;
  page_number: number;
  issue_ids: string[];
  bbox: ExtractedField["bbox"];
  evidence?: {
    text?: string | null;
    start?: number | null;
    end?: number | null;
  } | null;
  candidates?: Array<{
    engine: string;
    source: string;
    value?: string | null;
    raw_text?: string | null;
    confidence?: number | null;
    page_number?: number;
    bbox?: ExtractedField["bbox"] | null;
    evidence_text?: string | null;
    selected?: boolean;
    match_type?: string;
    score?: number;
  }>;
  consensus?: {
    engines_considered?: number;
    candidate_count?: number;
    supporting_engines?: string[];
    agreement_ratio?: number;
    disagreement?: boolean;
  } | null;
  adjudication?: {
    method?: string;
    abstained?: boolean;
    selected_value?: string | null;
    selected_source?: string | null;
    selected_engine?: string | null;
    confidence?: number | null;
    rationale?: string;
    evidence_sources?: string[];
  } | null;
  confidence_details?: {
    final: number;
    ocr_confidence?: number | null;
    normalization_confidence?: number | null;
    validation_confidence?: number | null;
    quality_score?: number | null;
    consensus_confidence?: number | null;
    integrity_score?: number | null;
    issue_penalty?: number;
    reasons?: string[];
  } | null;
};

type RemoteProcessResponse = {
  request_id: string;
  response_mode: "json" | "full";
  fields?: RemoteField[];
  document?: {
    family: string;
    country: string;
    variant: string | null;
    pack_id?: string | null;
    pack_version?: string | null;
    document_side?: string | null;
    issuer: string | null;
    holder_name: string | null;
  } | null;
  processing?: {
    engine: string;
    extraction_source: string;
    selected_visual_engine?: string | null;
    ensemble_mode?: string | null;
    decision_profile?: string | null;
    requested_visual_engine?: string | null;
    classification_confidence?: number | null;
    adjudication_mode?: string | null;
    adjudicated_fields?: number;
    adjudication_abstentions?: number;
    processing_trace?: Array<{
      stage: string;
      status?: string;
      started_at: string;
      finished_at: string;
      duration_ms?: number;
      summary?: string;
    }>;
    confidence_details?: {
      final: number;
      ocr_confidence?: number | null;
      normalization_confidence?: number | null;
      validation_confidence?: number | null;
      quality_score?: number | null;
      consensus_confidence?: number | null;
      integrity_score?: number | null;
      issue_penalty?: number;
      reasons?: string[];
    } | null;
    integrity_assessment?: {
      score: number;
      risk_level: "low" | "medium" | "high";
      indicators?: Array<{
        code: string;
        severity: "low" | "medium" | "high";
        source: string;
        message: string;
      }>;
      checks?: Record<string, boolean | number | null>;
    } | null;
    quality_assessment?: {
      score: number;
      blur_score?: number | null;
      glare_score?: number | null;
      crop_ratio?: number | null;
      document_coverage?: number | null;
      orientation?: number | null;
      capture_conditions?: string[];
      recommendations?: string[];
    } | null;
    ocr_runs?: Array<{
      engine: string;
      source: string;
      success: boolean;
      selected?: boolean;
      score?: number;
      page_count?: number;
      text?: string;
      average_confidence?: number | null;
      classification_family?: string | null;
      classification_country?: string | null;
      classification_confidence?: number | null;
      supported_classification?: boolean;
      preprocess_profile?: string;
      assumptions?: string[];
      pages?: Array<{
        page_number: number;
        text?: string;
        token_count?: number;
        average_confidence?: number | null;
        rescue_profile?: string | null;
      }>;
      tokens?: Array<{
        text: string;
        confidence?: number | null;
        bbox: number[][];
        page_number: number;
      }>;
      key_value_pairs?: Array<{
        label: string;
        value: string;
        page_number: number;
        raw_line: string;
      }>;
      table_candidate_rows?: string[];
    }>;
  } | null;
  pages?: Array<{
    page_number: number;
    image_path?: string | null;
    image_base64?: string | null;
    width?: number | null;
    height?: number | null;
    orientation?: number;
    quality_score?: number | null;
    blur_score?: number | null;
    glare_score?: number | null;
    crop_ratio?: number | null;
    document_coverage?: number | null;
    edge_confidence?: number | null;
    skew_angle?: number | null;
    skew_applied?: boolean;
    perspective_applied?: boolean;
    capture_conditions?: string[];
    rescue_profiles?: string[];
    selected_ocr_profile?: string | null;
    corners?: number[][];
    has_embedded_text?: boolean;
  }>;
  document_family: string;
  country: string;
  variant: string | null;
  issuer: string | null;
  holder_name: string | null;
  page_count: number;
  global_confidence: number;
  decision: DocumentDecision;
  review_required: boolean;
  assumptions: string[];
  issues: ValidationIssue[];
  report_sections: ReportSection[];
  human_summary: string | null;
  report_html: string | null;
};

function toValidationStatus(issueIds: string[]): ValidationStatus {
  return issueIds.length > 0 ? "warning" : "valid";
}

function mapRemotePage(page: NonNullable<RemoteProcessResponse["pages"]>[number]): DocumentPageRecord {
  return {
    id: `page-${page.page_number}`,
    pageNumber: page.page_number,
    imagePath: page.image_path ?? null,
    imageBase64: page.image_base64 ?? null,
    width: page.width ?? null,
    height: page.height ?? null,
    orientation: page.orientation ?? 0,
    qualityScore: page.quality_score ?? null,
    blurScore: page.blur_score ?? null,
    glareScore: page.glare_score ?? null,
    cropRatio: page.crop_ratio ?? null,
    documentCoverage: page.document_coverage ?? null,
    edgeConfidence: page.edge_confidence ?? null,
    skewAngle: page.skew_angle ?? null,
    skewApplied: page.skew_applied ?? false,
    perspectiveApplied: page.perspective_applied ?? false,
    captureConditions: page.capture_conditions ?? [],
    rescueProfiles: page.rescue_profiles ?? [],
    selectedOcrProfile: page.selected_ocr_profile ?? null,
    corners: page.corners ?? [],
    hasEmbeddedText: page.has_embedded_text ?? false
  };
}

function mapRemoteAdjudication(adjudication: RemoteField["adjudication"]): FieldAdjudication | null {
  if (!adjudication) return null;
  return {
    method: adjudication.method ?? "deterministic",
    abstained: adjudication.abstained ?? false,
    selectedValue: adjudication.selected_value ?? null,
    selectedSource: adjudication.selected_source ?? null,
    selectedEngine: adjudication.selected_engine ?? null,
    confidence: adjudication.confidence ?? null,
    rationale: adjudication.rationale ?? "",
    evidenceSources: adjudication.evidence_sources ?? []
  };
}

function mapRemoteConfidenceDetails(
  details:
    | RemoteField["confidence_details"]
    | NonNullable<NonNullable<RemoteProcessResponse["processing"]>["confidence_details"]>
): ConfidenceDetails | null {
  if (!details) return null;
  return {
    final: details.final,
    ocrConfidence: details.ocr_confidence ?? null,
    normalizationConfidence: details.normalization_confidence ?? null,
    validationConfidence: details.validation_confidence ?? null,
    qualityScore: details.quality_score ?? null,
    consensusConfidence: details.consensus_confidence ?? null,
    integrityScore: details.integrity_score ?? null,
    issuePenalty: details.issue_penalty ?? 0,
    reasons: details.reasons ?? []
  };
}

function mapRemoteIntegrityAssessment(assessment: NonNullable<NonNullable<RemoteProcessResponse["processing"]>["integrity_assessment"]>): IntegrityAssessment | null {
  if (!assessment) return null;
  return {
    score: assessment.score,
    riskLevel: assessment.risk_level,
    indicators: (assessment.indicators ?? []).map((indicator) => ({
      code: indicator.code,
      severity: indicator.severity,
      source: indicator.source,
      message: indicator.message
    })),
    checks: {
      checksumValid: (assessment.checks?.checksumValid as boolean | null | undefined) ?? null,
      crossSideMatch: (assessment.checks?.crossSideMatch as boolean | null | undefined) ?? null,
      averagePageQuality: (assessment.checks?.averagePageQuality as number | null | undefined) ?? null,
      averageOcrAgreement: (assessment.checks?.averageOcrAgreement as number | null | undefined) ?? null
    }
  };
}

function mapRemoteQualityAssessment(assessment: NonNullable<NonNullable<RemoteProcessResponse["processing"]>["quality_assessment"]>): QualityAssessment | null {
  if (!assessment) return null;
  return {
    score: assessment.score,
    blurScore: assessment.blur_score ?? null,
    glareScore: assessment.glare_score ?? null,
    cropRatio: assessment.crop_ratio ?? null,
    documentCoverage: assessment.document_coverage ?? null,
    orientation: assessment.orientation ?? null,
    captureConditions: assessment.capture_conditions ?? [],
    recommendations: assessment.recommendations ?? []
  };
}

function mapRemoteOcrRun(run: NonNullable<NonNullable<RemoteProcessResponse["processing"]>["ocr_runs"]>[number]): OcrRunSummary {
  return {
    engine: run.engine,
    source: run.source,
    success: run.success,
    selected: run.selected ?? false,
    score: run.score ?? 0,
    pageCount: run.page_count ?? 0,
    text: run.text ?? "",
    averageConfidence: run.average_confidence ?? null,
    classificationFamily: run.classification_family ?? null,
    classificationCountry: run.classification_country ?? null,
    classificationConfidence: run.classification_confidence ?? null,
    supportedClassification: run.supported_classification ?? false,
    preprocessProfile: run.preprocess_profile ?? "original",
    assumptions: run.assumptions ?? [],
    pages: (run.pages ?? []).map((page) => ({
      pageNumber: page.page_number,
      text: page.text ?? "",
      tokenCount: page.token_count ?? 0,
      averageConfidence: page.average_confidence ?? null,
      rescueProfile: page.rescue_profile ?? null
    })),
    tokens: (run.tokens ?? []).map((token) => ({
      text: token.text,
      confidence: token.confidence ?? null,
      bbox: token.bbox,
      pageNumber: token.page_number
    })),
    keyValuePairs: (run.key_value_pairs ?? []).map((pair) => ({
      label: pair.label,
      value: pair.value,
      pageNumber: pair.page_number,
      rawLine: pair.raw_line
    })),
    tableCandidateRows: run.table_candidate_rows ?? []
  };
}

function toReviewStatus(issueIds: string[]): ReviewStatus {
  return issueIds.length > 0 ? "pending" : "confirmed";
}

function mapRemoteField(field: RemoteField): ExtractedField {
  return {
    id: field.id,
    section: field.section,
    fieldName: field.field_name,
    label: field.label,
    rawText: field.raw_text,
    normalizedValue: field.value,
    valueType: field.value_type,
    confidence: field.confidence,
    engine: field.engine ?? "ocr-api",
    pageNumber: field.page_number,
    bbox: field.bbox,
    evidenceSpan: field.evidence?.text
      ? {
          text: field.evidence.text,
          start: field.evidence.start ?? null,
          end: field.evidence.end ?? null
        }
      : null,
    validationStatus: toValidationStatus(field.issue_ids),
    reviewStatus: toReviewStatus(field.issue_ids),
    isInferred: false,
    issueIds: field.issue_ids,
    candidates: (field.candidates ?? []).map((candidate) => ({
      engine: candidate.engine,
      source: candidate.source,
      value: candidate.value ?? null,
      rawText: candidate.raw_text ?? null,
      confidence: candidate.confidence ?? null,
      pageNumber: candidate.page_number ?? 1,
      bbox: candidate.bbox ?? null,
      evidenceText: candidate.evidence_text ?? null,
      selected: candidate.selected ?? false,
      matchType: candidate.match_type ?? "unknown",
      score: candidate.score ?? 0,
    })),
    consensus: field.consensus
      ? {
          enginesConsidered: field.consensus.engines_considered ?? 0,
          candidateCount: field.consensus.candidate_count ?? 0,
          supportingEngines: field.consensus.supporting_engines ?? [],
          agreementRatio: field.consensus.agreement_ratio ?? 0,
          disagreement: field.consensus.disagreement ?? false,
        }
      : null,
    adjudication: mapRemoteAdjudication(field.adjudication),
    confidenceDetails: mapRemoteConfidenceDetails(field.confidence_details)
  };
}

export async function runRemoteProcessing(
  document: DocumentRecord,
  overrides?: {
    visualEngine?: string | null;
    decisionProfile?: string | null;
    structuredMode?: string | null;
    ensembleMode?: string | null;
    ensembleEngines?: string | null;
    fieldAdjudicationMode?: string | null;
  }
) {
  const apiUrl = getOcrApiUrl();
  const apiKey = getOptionalOcrApiKey();

  const fileBuffer = await readDocumentBinary(document);
  const processingOptions = resolveTenantProcessingOptions(document);
  const formData = new FormData();
  formData.set("file", new Blob([fileBuffer], { type: document.mimeType }), document.filename);
  formData.set("document_family", document.documentFamily);
  formData.set("country", document.country);
  formData.set("response_mode", "full");
  if (document.tenantId) {
    formData.set("tenant_id", document.tenantId);
  }
  const visualEngine = overrides?.visualEngine ?? processingOptions.visualEngine;
  const decisionProfile = overrides?.decisionProfile ?? processingOptions.decisionProfile;
  const structuredMode = overrides?.structuredMode ?? processingOptions.structuredMode;
  const ensembleMode = overrides?.ensembleMode ?? processingOptions.ensembleMode;
  const ensembleEngines = overrides?.ensembleEngines ?? processingOptions.ensembleEngines;
  const fieldAdjudicationMode = overrides?.fieldAdjudicationMode ?? processingOptions.fieldAdjudicationMode;
  if (visualEngine) {
    formData.set("ocr_visual_engine", visualEngine);
  }
  if (decisionProfile) {
    formData.set("decision_profile", decisionProfile);
  }
  if (structuredMode) {
    formData.set("ocr_structured_mode", structuredMode);
  }
  if (ensembleMode) {
    formData.set("ocr_ensemble_mode", ensembleMode);
  }
  if (ensembleEngines) {
    formData.set("ocr_ensemble_engines", ensembleEngines);
  }
  if (fieldAdjudicationMode) {
    formData.set("field_adjudication_mode", fieldAdjudicationMode);
  }

  const response = await fetch(`${apiUrl}/v1/process`, {
    method: "POST",
    body: formData,
    cache: "no-store",
    headers: apiKey
      ? {
          "x-api-key": apiKey
        }
      : undefined
  });

  if (!response.ok) {
    throw new Error(`OCR API returned ${response.status}`);
  }

  const payload = (await response.json()) as RemoteProcessResponse;

  return {
    decision: payload.decision,
    documentFamily: payload.document_family as DocumentRecord["documentFamily"],
    country: payload.country,
    variant: payload.variant,
    issuer: payload.issuer,
    holderName: payload.holder_name,
    pageCount: payload.page_count,
    globalConfidence: payload.global_confidence,
    reviewRequired: payload.review_required,
    assumptions: payload.assumptions,
    issues: payload.issues,
    extractedFields: payload.fields?.map(mapRemoteField) ?? [],
    documentPages: payload.pages?.map(mapRemotePage) ?? [],
    processingMetadata: {
      packId: payload.document?.pack_id ?? null,
      packVersion: payload.document?.pack_version ?? null,
      documentSide: payload.document?.document_side ?? null,
      crossSideDetected: payload.document?.document_side === "front+back",
      decisionProfile: payload.processing?.decision_profile ?? null,
      requestedVisualEngine: payload.processing?.requested_visual_engine ?? null,
      selectedVisualEngine: payload.processing?.selected_visual_engine ?? null,
      ensembleMode: payload.processing?.ensemble_mode ?? null,
      classificationConfidence: payload.processing?.classification_confidence ?? null,
      extractionSource: payload.processing?.extraction_source ?? null,
      processingEngine: payload.processing?.engine ?? null,
      ocrRuns: payload.processing?.ocr_runs?.map(mapRemoteOcrRun) ?? [],
      adjudicationMode: payload.processing?.adjudication_mode ?? null,
      adjudicatedFields: payload.processing?.adjudicated_fields ?? 0,
      adjudicationAbstentions: payload.processing?.adjudication_abstentions ?? 0,
      confidenceDetails: mapRemoteConfidenceDetails(payload.processing?.confidence_details ?? null),
      integrityAssessment: payload.processing?.integrity_assessment ? mapRemoteIntegrityAssessment(payload.processing.integrity_assessment) : null,
      qualityAssessment: payload.processing?.quality_assessment ? mapRemoteQualityAssessment(payload.processing.quality_assessment) : null,
      processingTrace: (payload.processing?.processing_trace ?? []).map((entry) => ({
        stage: entry.stage,
        status: entry.status ?? 'completed',
        startedAt: entry.started_at,
        finishedAt: entry.finished_at,
        durationMs: entry.duration_ms ?? 0,
        summary: entry.summary ?? '',
      })),
    },
    reportSections: payload.report_sections,
    humanSummary: payload.human_summary,
    reportHtml: payload.report_html
  } satisfies Partial<DocumentRecord>;
}
