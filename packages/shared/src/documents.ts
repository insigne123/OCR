export type DocumentFamily =
  | "certificate"
  | "identity"
  | "passport"
  | "driver_license"
  | "invoice"
  | "mixed"
  | "unclassified";

export type DocumentStatus =
  | "uploaded"
  | "processing"
  | "completed"
  | "review"
  | "rejected";

export type DocumentDecision =
  | "pending"
  | "auto_accept"
  | "accept_with_warning"
  | "human_review"
  | "reject";

export type ReportSectionVariant = "pairs" | "table" | "text";

export type ValidationSeverity = "low" | "medium" | "high";

export type DocumentRiskLevel = "low" | "medium" | "high";

export type ValidationStatus = "unknown" | "valid" | "warning" | "invalid";

export type ReviewStatus = "pending" | "confirmed" | "corrected" | "dismissed";

export type ReviewSessionStatus = "open" | "completed" | "cancelled";

export type StorageProvider = "local" | "supabase";

export type ProcessingJobStatus = "queued" | "running" | "completed" | "failed";
export type ProcessingStageStatus = "pending" | "running" | "completed" | "failed" | "skipped";
export type ProcessingStageName = "ingest" | "classify" | "extract" | "normalize" | "validate" | "report" | "persist";

export const AUTO_COUNTRY_CODE = "XX";

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface EvidenceSpan {
  text: string;
  start: number | null;
  end: number | null;
}

export interface OcrRunToken {
  text: string;
  confidence: number | null;
  bbox: number[][];
  pageNumber: number;
}

export interface OcrRunPage {
  pageNumber: number;
  text: string;
  tokenCount: number;
  averageConfidence: number | null;
  rescueProfile: string | null;
}

export interface OcrRunSummary {
  engine: string;
  source: string;
  success: boolean;
  selected: boolean;
  score: number;
  pageCount: number;
  text: string;
  averageConfidence: number | null;
  classificationFamily: string | null;
  classificationCountry: string | null;
  classificationConfidence: number | null;
  supportedClassification: boolean;
  preprocessProfile: string;
  assumptions: string[];
  pages: OcrRunPage[];
  tokens: OcrRunToken[];
  keyValuePairs: Array<{
    label: string;
    value: string;
    pageNumber: number;
    rawLine: string;
  }>;
  tableCandidateRows: string[];
}

export interface ProcessingTraceEntry {
  stage: string;
  status: string;
  startedAt: string;
  finishedAt: string;
  durationMs: number;
  summary: string;
}

export interface FieldCandidate {
  engine: string;
  source: string;
  value: string | null;
  rawText: string | null;
  confidence: number | null;
  pageNumber: number;
  bbox: BoundingBox | null;
  evidenceText: string | null;
  selected: boolean;
  matchType: string;
  score: number;
}

export interface FieldConsensus {
  enginesConsidered: number;
  candidateCount: number;
  supportingEngines: string[];
  agreementRatio: number;
  disagreement: boolean;
}

export interface FieldAdjudication {
  method: string;
  abstained: boolean;
  selectedValue: string | null;
  selectedSource: string | null;
  selectedEngine: string | null;
  confidence: number | null;
  rationale: string;
  evidenceSources: string[];
}

export interface ConfidenceDetails {
  final: number;
  ocrConfidence: number | null;
  normalizationConfidence: number | null;
  validationConfidence: number | null;
  qualityScore: number | null;
  consensusConfidence: number | null;
  integrityScore: number | null;
  issuePenalty: number;
  reasons: string[];
}

export interface IntegrityIndicator {
  code: string;
  severity: ValidationSeverity;
  source: string;
  message: string;
}

export interface IntegrityAssessment {
  score: number;
  riskLevel: DocumentRiskLevel;
  indicators: IntegrityIndicator[];
  checks: {
    checksumValid: boolean | null;
    crossSideMatch: boolean | null;
    averagePageQuality: number | null;
    averageOcrAgreement: number | null;
  };
}

export interface QualityAssessment {
  score: number;
  blurScore: number | null;
  glareScore: number | null;
  cropRatio: number | null;
  documentCoverage: number | null;
  orientation: number | null;
  captureConditions: string[];
  recommendations: string[];
}

export interface ReportSection {
  id: string;
  title: string;
  variant: ReportSectionVariant;
  columns?: string[];
  rows?: string[][];
  body?: string;
  note?: string;
}

export interface ValidationIssue {
  id: string;
  type: string;
  field: string;
  severity: ValidationSeverity;
  message: string;
  suggestedAction: string;
}

export interface ExtractedField {
  id: string;
  section: string;
  fieldName: string;
  label: string;
  rawText: string | null;
  normalizedValue: string | null;
  valueType: string;
  confidence: number | null;
  engine: string;
  pageNumber: number;
  bbox: BoundingBox | null;
  evidenceSpan: EvidenceSpan | null;
  validationStatus: ValidationStatus;
  reviewStatus: ReviewStatus;
  isInferred: boolean;
  issueIds: string[];
  candidates: FieldCandidate[];
  consensus: FieldConsensus | null;
  adjudication: FieldAdjudication | null;
  confidenceDetails?: ConfidenceDetails | null;
}

export interface DocumentPageRecord {
  id: string;
  pageNumber: number;
  imagePath: string | null;
  imageBase64?: string | null;
  width: number | null;
  height: number | null;
  orientation: number;
  qualityScore: number | null;
  blurScore: number | null;
  glareScore: number | null;
  cropRatio: number | null;
  documentCoverage: number | null;
  edgeConfidence: number | null;
  skewAngle: number | null;
  skewApplied: boolean;
  perspectiveApplied: boolean;
  captureConditions: string[];
  rescueProfiles: string[];
  selectedOcrProfile: string | null;
  corners: number[][];
  hasEmbeddedText: boolean;
}

export interface ReviewEdit {
  id: string;
  fieldId: string;
  fieldName: string;
  previousValue: string | null;
  newValue: string | null;
  reason: string;
  createdAt: string;
  reviewerName: string;
}

export interface ReviewSession {
  id: string;
  reviewerName: string;
  status: ReviewSessionStatus;
  notes: string | null;
  openedAt: string;
  updatedAt: string;
  edits: ReviewEdit[];
}

export interface ProcessingJobRecord {
  id: string;
  status: ProcessingJobStatus;
  engine: string;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  errorMessage: string | null;
  attemptCount: number;
  maxAttempts: number;
  nextRetryAt: string | null;
  idempotencyKey: string;
  queueName: string;
  currentStage: ProcessingStageName | null;
  leaseOwner?: string | null;
  leaseExpiresAt?: string | null;
  payload: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  stages: ProcessingStageRecord[];
}

export interface ProcessingStageRecord {
  name: ProcessingStageName;
  status: ProcessingStageStatus;
  startedAt: string | null;
  finishedAt: string | null;
  message: string | null;
}

export interface ProcessingMetadataSummary {
  packId: string | null;
  packVersion: string | null;
  documentSide: string | null;
  crossSideDetected: boolean;
  routingStrategy?: string | null;
  routingReasons?: string[];
  decisionProfile: string | null;
  requestedVisualEngine: string | null;
  selectedVisualEngine: string | null;
  ensembleMode: string | null;
  classificationConfidence: number | null;
  extractionSource: string | null;
  processingEngine: string | null;
  ocrRuns: OcrRunSummary[];
  adjudicationMode: string | null;
  adjudicatedFields: number;
  adjudicationAbstentions: number;
  processingTrace: ProcessingTraceEntry[];
  confidenceDetails?: ConfidenceDetails | null;
  integrityAssessment?: IntegrityAssessment | null;
  qualityAssessment?: QualityAssessment | null;
}

export interface DocumentRecord {
  id: string;
  tenantId: string;
  filename: string;
  mimeType: string;
  size: number;
  storagePath: string;
  storageProvider: StorageProvider;
  sourceHash: string | null;
  status: DocumentStatus;
  decision: DocumentDecision;
  documentFamily: DocumentFamily;
  country: string;
  variant: string | null;
  riskLevel: DocumentRiskLevel;
  issuer: string | null;
  holderName: string | null;
  pageCount: number;
  globalConfidence: number | null;
  reviewRequired: boolean;
  createdAt: string;
  updatedAt: string;
  processedAt: string | null;
  assumptions: string[];
  issues: ValidationIssue[];
  extractedFields: ExtractedField[];
  documentPages: DocumentPageRecord[];
  reviewSessions: ReviewSession[];
  latestJob: ProcessingJobRecord | null;
  processingMetadata: ProcessingMetadataSummary;
  lastReviewedAt: string | null;
  reportSections: ReportSection[];
  humanSummary: string | null;
  reportHtml: string | null;
}

export const documentFamilyOptions: Array<{ value: DocumentFamily; label: string }> = [
  { value: "certificate", label: "Certificados" },
  { value: "identity", label: "Identidad" },
  { value: "passport", label: "Pasaportes" },
  { value: "driver_license", label: "Licencias" },
  { value: "invoice", label: "Facturas" },
  { value: "mixed", label: "PDF mixto" },
  { value: "unclassified", label: "Sin clasificar" }
];

export const documentStatusLabels: Record<DocumentStatus, string> = {
  uploaded: "Subido",
  processing: "Procesando",
  completed: "Completado",
  review: "Revision",
  rejected: "Rechazado"
};

export const documentDecisionLabels: Record<DocumentDecision, string> = {
  pending: "Pendiente",
  auto_accept: "OK",
  accept_with_warning: "Partial",
  human_review: "Review",
  reject: "Blocked"
};
