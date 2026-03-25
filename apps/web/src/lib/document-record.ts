import type {
  DocumentDecision,
  DocumentFamily,
  DocumentRecord,
  DocumentRiskLevel,
  DocumentStatus,
  ExtractedField,
  DocumentPageRecord,
  ProcessingJobRecord,
  ProcessingStageName,
  ProcessingStageRecord,
  ProcessingStageStatus,
  ProcessingJobStatus,
  ReportSection,
  ReviewEdit,
  ReviewSession,
  ReviewSessionStatus,
  ReviewStatus,
  ValidationIssue,
  ValidationStatus
} from "@ocr/shared";
import { AUTO_COUNTRY_CODE as DEFAULT_AUTO_COUNTRY_CODE } from "@ocr/shared";

const DEFAULT_TENANT_ID = "local-default-tenant";

function slugify(value: string) {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

const DEFAULT_PROCESSING_STAGES: ProcessingStageName[] = ["ingest", "classify", "extract", "normalize", "validate", "report", "persist"];

function createStageRecord(name: ProcessingStageName, status: ProcessingStageStatus = "pending"): ProcessingStageRecord {
  return {
    name,
    status,
    startedAt: null,
    finishedAt: null,
    message: null
  };
}

export function createDefaultProcessingStages() {
  return DEFAULT_PROCESSING_STAGES.map((stage) => createStageRecord(stage));
}

export function createDocumentPageRecord(input: Partial<DocumentPageRecord> & Pick<DocumentPageRecord, "pageNumber">): DocumentPageRecord {
  return {
    id: input.id ?? crypto.randomUUID(),
    pageNumber: input.pageNumber,
    imagePath: input.imagePath ?? null,
    imageBase64: input.imageBase64 ?? null,
    width: input.width ?? null,
    height: input.height ?? null,
    orientation: input.orientation ?? 0,
    qualityScore: input.qualityScore ?? null,
    blurScore: input.blurScore ?? null,
    glareScore: input.glareScore ?? null,
    cropRatio: input.cropRatio ?? null,
    documentCoverage: input.documentCoverage ?? null,
    edgeConfidence: input.edgeConfidence ?? null,
    skewAngle: input.skewAngle ?? null,
    skewApplied: input.skewApplied ?? false,
    perspectiveApplied: input.perspectiveApplied ?? false,
    captureConditions: input.captureConditions ?? [],
    rescueProfiles: input.rescueProfiles ?? [],
    selectedOcrProfile: input.selectedOcrProfile ?? null,
    corners: input.corners ?? [],
    hasEmbeddedText: input.hasEmbeddedText ?? false
  };
}

function normalizeIssueField(value: string) {
  return slugify(value);
}

function toValidationStatus(issueIds: string[]): ValidationStatus {
  if (issueIds.length === 0) return "valid";
  return "warning";
}

function toReviewStatus(issueIds: string[]): ReviewStatus {
  return issueIds.length === 0 ? "confirmed" : "pending";
}

function toFieldValueType(value: string) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return "date";
  if (/^[\d.,-]+$/.test(value)) return "number";
  return "text";
}

function linkIssues(label: string, fieldName: string, issues: ValidationIssue[]) {
  const linked = issues.filter((issue) => {
    const normalizedIssueField = normalizeIssueField(issue.field);
    return normalizedIssueField === normalizeIssueField(label) || normalizedIssueField === normalizeIssueField(fieldName);
  });

  return linked.map((issue) => issue.id);
}

function createField(input: {
  sectionId: string;
  label: string;
  fieldName?: string;
  value: string;
  pageNumber?: number;
  issues: ValidationIssue[];
  engine?: string;
}): ExtractedField {
  const fieldName = input.fieldName ?? slugify(input.label);
  const issueIds = linkIssues(input.label, fieldName, input.issues);

  return {
    id: `${input.sectionId}-${fieldName}-${slugify(input.value) || "value"}`,
    section: input.sectionId,
    fieldName,
    label: input.label,
    rawText: input.value,
    normalizedValue: input.value,
    valueType: toFieldValueType(input.value),
      confidence: issueIds.length > 0 ? 0.74 : 0.9,
      engine: input.engine ?? "mock-pipeline",
    pageNumber: input.pageNumber ?? 1,
    bbox: null,
    evidenceSpan: input.value
      ? {
          text: input.value,
          start: 0,
          end: input.value.length
        }
      : null,
    validationStatus: toValidationStatus(issueIds),
    reviewStatus: toReviewStatus(issueIds),
    isInferred: false,
      issueIds,
      candidates: [],
      consensus: null,
      adjudication: null,
      confidenceDetails: null
    };
}

export function createExtractedFieldsFromSections(
  reportSections: ReportSection[],
  issues: ValidationIssue[],
  engine = "mock-pipeline"
) {
  const fields: ExtractedField[] = [];

  for (const section of reportSections) {
    if (section.variant === "pairs" && section.rows) {
      for (const row of section.rows) {
        fields.push(
          createField({
            sectionId: section.id,
            label: row[0],
            value: row[1] ?? "",
            issues,
            engine
          })
        );
      }
    }

    if (section.variant === "table" && section.columns && section.rows) {
      const [firstColumn, ...remainingColumns] = section.columns;

      for (const [rowIndex, row] of section.rows.entries()) {
        if (section.columns.length === 2 && firstColumn.toLowerCase() === "campo") {
          fields.push(
            createField({
              sectionId: section.id,
              label: row[0] ?? `${section.title} ${rowIndex + 1}`,
              value: row[1] ?? "",
              issues,
              engine
            })
          );
          continue;
        }

        const rowContext = row[0] ?? `${section.title} ${rowIndex + 1}`;

        for (const [columnIndex, column] of remainingColumns.entries()) {
          fields.push(
            createField({
              sectionId: section.id,
              label: `${rowContext} · ${column}`,
              fieldName: `${slugify(rowContext)}-${slugify(column)}`,
              value: row[columnIndex + 1] ?? "",
              issues,
              engine
            })
          );
        }
      }
    }

    if (section.variant === "text" && section.body) {
      fields.push(
        createField({
          sectionId: section.id,
          label: section.title,
          value: section.body,
          issues,
          engine
        })
      );
    }
  }

  return fields;
}

export function createJobSnapshot(input: {
  status: ProcessingJobStatus;
  engine: string;
  errorMessage?: string | null;
  createdAt?: string;
  startedAt?: string | null;
  finishedAt?: string | null;
  attemptCount?: number;
  maxAttempts?: number;
  nextRetryAt?: string | null;
  idempotencyKey?: string;
  queueName?: string;
  currentStage?: ProcessingStageName | null;
  payload?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
  stages?: ProcessingStageRecord[];
}): ProcessingJobRecord {
  return {
    id: crypto.randomUUID(),
    status: input.status,
    engine: input.engine,
    createdAt: input.createdAt ?? new Date().toISOString(),
    startedAt: input.startedAt ?? null,
    finishedAt: input.finishedAt ?? null,
    errorMessage: input.errorMessage ?? null,
    attemptCount: input.attemptCount ?? 0,
    maxAttempts: input.maxAttempts ?? 3,
    nextRetryAt: input.nextRetryAt ?? null,
    idempotencyKey: input.idempotencyKey ?? crypto.randomUUID(),
    queueName: input.queueName ?? "default",
    currentStage: input.currentStage ?? null,
    leaseOwner: null,
    leaseExpiresAt: null,
    payload: input.payload ?? null,
    result: input.result ?? null,
    stages: input.stages ?? createDefaultProcessingStages()
  };
}

export function createReviewSession(input: {
  reviewerName: string;
  status?: ReviewSessionStatus;
  notes?: string | null;
  openedAt?: string;
  updatedAt?: string;
  edits?: ReviewEdit[];
}): ReviewSession {
  const timestamp = input.openedAt ?? new Date().toISOString();

  return {
    id: crypto.randomUUID(),
    reviewerName: input.reviewerName,
    status: input.status ?? "open",
    notes: input.notes ?? null,
    openedAt: timestamp,
    updatedAt: input.updatedAt ?? timestamp,
    edits: input.edits ?? []
  };
}

export function createBaseDocumentRecord(input: {
  id?: string;
  filename: string;
  mimeType: string;
  size: number;
  storagePath: string;
  documentFamily?: DocumentFamily;
  country?: string;
  tenantId?: string;
  storageProvider?: DocumentRecord["storageProvider"];
  sourceHash?: string | null;
  status?: DocumentStatus;
  decision?: DocumentDecision;
  riskLevel?: DocumentRiskLevel;
  createdAt?: string;
  updatedAt?: string;
}): DocumentRecord {
  const timestamp = input.createdAt ?? new Date().toISOString();

  return {
    id: input.id ?? crypto.randomUUID(),
    tenantId: input.tenantId ?? DEFAULT_TENANT_ID,
    filename: input.filename,
    mimeType: input.mimeType,
    size: input.size,
    storagePath: input.storagePath,
    storageProvider: input.storageProvider ?? "local",
    sourceHash: input.sourceHash ?? null,
    status: input.status ?? "uploaded",
    decision: input.decision ?? "pending",
    documentFamily: input.documentFamily ?? "unclassified",
    country: (input.country ?? DEFAULT_AUTO_COUNTRY_CODE).toUpperCase(),
    variant: null,
    riskLevel: input.riskLevel ?? "medium",
    issuer: null,
    holderName: null,
    pageCount: 1,
    globalConfidence: null,
    reviewRequired: false,
    createdAt: timestamp,
    updatedAt: input.updatedAt ?? timestamp,
    processedAt: null,
    assumptions: [],
    issues: [],
    extractedFields: [],
    documentPages: [],
    reviewSessions: [],
    latestJob: null,
    processingMetadata: {
      packId: null,
      packVersion: null,
      documentSide: null,
      crossSideDetected: false,
      routingStrategy: null,
      routingReasons: [],
      decisionProfile: null,
      requestedVisualEngine: null,
      selectedVisualEngine: null,
      ensembleMode: null,
      classificationConfidence: null,
      extractionSource: null,
      processingEngine: null,
      ocrRuns: [],
      adjudicationMode: null,
      adjudicatedFields: 0,
      adjudicationAbstentions: 0,
      processingTrace: [],
      confidenceDetails: null,
      integrityAssessment: null,
      qualityAssessment: null
    },
    lastReviewedAt: null,
    reportSections: [],
    humanSummary: null,
    reportHtml: null
  };
}

export function normalizeDocumentRecord(raw: Partial<DocumentRecord>): DocumentRecord {
  const base = createBaseDocumentRecord({
    id: raw.id,
    filename: raw.filename ?? "documento",
    mimeType: raw.mimeType ?? "application/octet-stream",
    size: raw.size ?? 0,
    storagePath: raw.storagePath ?? "uploads/documento",
    documentFamily: raw.documentFamily,
    country: raw.country,
    tenantId: raw.tenantId,
    storageProvider: raw.storageProvider,
    sourceHash: raw.sourceHash,
    status: raw.status,
    decision: raw.decision,
    riskLevel: raw.riskLevel,
    createdAt: raw.createdAt,
    updatedAt: raw.updatedAt
  });

  const reportSections = raw.reportSections ?? [];
  const issues = raw.issues ?? [];

  return {
    ...base,
    variant: raw.variant ?? null,
    riskLevel: raw.riskLevel ?? base.riskLevel,
    issuer: raw.issuer ?? null,
    holderName: raw.holderName ?? null,
    pageCount: raw.pageCount ?? 1,
    globalConfidence: raw.globalConfidence ?? null,
    reviewRequired: raw.reviewRequired ?? false,
    updatedAt: raw.updatedAt ?? base.updatedAt,
    processedAt: raw.processedAt ?? null,
    assumptions: raw.assumptions ?? [],
    issues,
    extractedFields:
      raw.extractedFields && raw.extractedFields.length > 0
        ? raw.extractedFields.map((field) => ({
            ...field,
            candidates: field.candidates ?? [],
            consensus: field.consensus ?? null,
            adjudication: field.adjudication ?? null,
            confidenceDetails: field.confidenceDetails ?? null
          }))
        : createExtractedFieldsFromSections(reportSections, issues),
    documentPages: raw.documentPages?.map((page) => createDocumentPageRecord(page)) ?? [],
    reviewSessions: raw.reviewSessions ?? [],
    latestJob: raw.latestJob
      ? {
          ...createJobSnapshot({ status: "queued", engine: raw.latestJob.engine ?? "unknown" }),
          ...raw.latestJob,
          stages: raw.latestJob.stages ?? createDefaultProcessingStages(),
          attemptCount: raw.latestJob.attemptCount ?? 0,
          maxAttempts: raw.latestJob.maxAttempts ?? 3,
          nextRetryAt: raw.latestJob.nextRetryAt ?? null,
          idempotencyKey: raw.latestJob.idempotencyKey ?? raw.id ?? crypto.randomUUID(),
          queueName: raw.latestJob.queueName ?? "default",
          currentStage: raw.latestJob.currentStage ?? null,
          leaseOwner: raw.latestJob.leaseOwner ?? null,
          leaseExpiresAt: raw.latestJob.leaseExpiresAt ?? null,
          payload: raw.latestJob.payload ?? null,
          result: raw.latestJob.result ?? null
        }
      : null,
    processingMetadata: {
      ...base.processingMetadata,
      ...raw.processingMetadata,
      processingTrace: raw.processingMetadata?.processingTrace ?? base.processingMetadata.processingTrace
    },
    lastReviewedAt: raw.lastReviewedAt ?? null,
    reportSections,
    humanSummary: raw.humanSummary ?? null,
    reportHtml: raw.reportHtml ?? null
  };
}
