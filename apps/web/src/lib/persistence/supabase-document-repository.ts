import type {
  DocumentPageRecord,
  DocumentRecord,
  ExtractedField,
  ProcessingJobRecord,
  ReportSection,
  ReviewEdit,
  ReviewSession,
  ValidationIssue
} from "@ocr/shared";
import { createHash } from "node:crypto";
import { createBaseDocumentRecord, createDefaultProcessingStages, normalizeDocumentRecord } from "@/lib/document-record";
import { hasSupabasePublicConfig } from "@/lib/supabase/config";
import { getOptionalAuthenticatedUser } from "@/lib/supabase/server-auth";
import { getSupabaseServerClient, getSupabaseStorageBucket } from "@/lib/supabase/server";
import type { CreateDocumentInput, DocumentRepository } from "./types";

const DEFAULT_TENANT_SLUG = process.env.SUPABASE_DEFAULT_TENANT_SLUG || "default-workspace";
const DEFAULT_TENANT_NAME = process.env.SUPABASE_DEFAULT_TENANT_NAME || "Default Workspace";
const ALLOW_TENANT_BOOTSTRAP = process.env.SUPABASE_BOOTSTRAP_TENANT_ACCESS === "true";

let cachedTenantId: string | null = null;
let bucketEnsured = false;

type DocumentRow = {
  id: string;
  tenant_id: string | null;
  source_filename: string;
  mime_type: string;
  file_size: number | null;
  storage_path: string;
  storage_provider: DocumentRecord["storageProvider"];
  sha256: string | null;
  document_family: DocumentRecord["documentFamily"];
  country: string;
  variant: string | null;
  pack_id: string | null;
  pack_version: string | null;
  document_side: string | null;
  cross_side_detected: boolean | null;
  risk_level: DocumentRecord["riskLevel"];
  status: DocumentRecord["status"];
  decision: DocumentRecord["decision"];
  issuer: string | null;
  holder_name: string | null;
  page_count: number;
  global_confidence: number | null;
  classification_confidence: number | null;
  extraction_source: string | null;
  processing_engine: string | null;
  report_html: string | null;
  human_summary: string | null;
  review_required: boolean;
  created_at: string;
  updated_at: string;
  processed_at: string | null;
  last_reviewed_at: string | null;
};

type ValidationIssueRow = {
  id: string;
  document_id: string;
  field_name: string;
  issue_type: string;
  severity: ValidationIssue["severity"];
  message: string;
  suggested_action: string | null;
  created_at: string;
};

type ExtractedFieldRow = {
  id: string;
  document_id: string;
  page_number: number;
  section: string;
  field_name: string;
  label: string | null;
  raw_text: string | null;
  normalized_value: string | null;
  value_type: string | null;
  confidence: number | null;
  engine: string | null;
  bbox: ExtractedField["bbox"] | null;
  evidence_span: ExtractedField["evidenceSpan"] | null;
  validation_status: ExtractedField["validationStatus"];
  review_status: ExtractedField["reviewStatus"];
  is_inferred: boolean;
};

type DocumentPageRow = {
  id: string;
  document_id: string;
  page_number: number;
  image_path: string | null;
  width: number | null;
  height: number | null;
  orientation: number | null;
  quality_score: number | null;
  blur_score: number | null;
  glare_score: number | null;
  has_embedded_text: boolean;
  created_at: string;
};

type ReviewSessionRow = {
  id: string;
  document_id: string;
  reviewer_name: string | null;
  status: ReviewSession["status"];
  notes: string | null;
  created_at: string;
  closed_at: string | null;
};

type ReviewEditRow = {
  id: string;
  review_session_id: string;
  document_id: string;
  field_id: string | null;
  field_name: string;
  previous_value: string | null;
  new_value: string | null;
  reason: string | null;
  reviewer_name: string | null;
  created_at: string;
};

type ProcessingJobRow = {
  id: string;
  document_id: string;
  status: ProcessingJobRecord["status"];
  engine: string | null;
  attempt_count: number | null;
  max_attempts: number | null;
  next_retry_at: string | null;
  idempotency_key: string | null;
  queue_name: string | null;
  current_stage: ProcessingJobRecord["currentStage"];
  lease_owner?: string | null;
  lease_expires_at?: string | null;
  payload: ProcessingJobRecord["payload"] | null;
  result: ProcessingJobRecord["result"] | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
};

type GeneratedReportRow = {
  id: string;
  document_id: string;
  format: string;
  payload: {
    assumptions?: string[];
    reportSections?: ReportSection[];
    processingMetadata?: DocumentRecord["processingMetadata"];
    fieldCandidatesById?: Record<string, Pick<ExtractedField, "candidates" | "consensus" | "adjudication" | "confidenceDetails">>;
  } | null;
};

function ensureNoError(error: { message: string } | null) {
  if (error) {
    throw new Error(error.message);
  }
}

function stableUuid(seed: string) {
  const hex = createHash("sha1").update(seed).digest("hex").slice(0, 32).padEnd(32, "0");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-5${hex.slice(13, 16)}-a${hex.slice(17, 20)}-${hex.slice(20, 32)}`;
}

function coerceUuid(value: string, seedPrefix: string) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
    ? value
    : stableUuid(`${seedPrefix}:${value}`);
}

async function ensureStorageBucket() {
  if (bucketEnsured) {
    return;
  }

  const supabase = getSupabaseServerClient();
  const bucketName = getSupabaseStorageBucket();
  const buckets = await supabase.storage.listBuckets();
  ensureNoError(buckets.error);

  const exists = (buckets.data ?? []).some((bucket) => bucket.name === bucketName);

  if (!exists) {
    const created = await supabase.storage.createBucket(bucketName, {
      public: false,
      fileSizeLimit: "20MB"
    });
    ensureNoError(created.error);
  }

  bucketEnsured = true;
}

async function ensureWorkspaceTenant(): Promise<string> {
  if (cachedTenantId) {
    return cachedTenantId;
  }

  const supabase = getSupabaseServerClient();
  const existing = await supabase.from("tenants").select("id").eq("slug", DEFAULT_TENANT_SLUG).maybeSingle();
  ensureNoError(existing.error);

  if (existing.data?.id) {
    cachedTenantId = existing.data.id;
    return existing.data.id;
  }

  const created = await supabase
    .from("tenants")
    .insert({
      name: DEFAULT_TENANT_NAME,
      slug: DEFAULT_TENANT_SLUG
    })
    .select("id")
    .single();
  ensureNoError(created.error);
  if (!created.data?.id) {
    throw new Error("Could not create default Supabase tenant.");
  }

  cachedTenantId = created.data.id;
  return created.data.id;
}

async function ensureUserProfileAndMembership(tenantId: string) {
  if (!hasSupabasePublicConfig()) {
    return;
  }

  const user = await getOptionalAuthenticatedUser();

  if (!user) {
    return;
  }

  const supabase = getSupabaseServerClient();

  const profileUpsert = await supabase.from("profiles").upsert(
    {
      id: user.id,
      email: user.email ?? null,
      display_name:
        (typeof user.user_metadata?.full_name === "string" && user.user_metadata.full_name) ||
        (typeof user.user_metadata?.name === "string" && user.user_metadata.name) ||
        user.email ||
        "User"
    },
    { onConflict: "id" }
  );
  ensureNoError(profileUpsert.error);

  const existingMembership = await supabase
    .from("tenant_members")
    .select("role")
    .eq("tenant_id", tenantId)
    .eq("user_id", user.id)
    .maybeSingle();
  ensureNoError(existingMembership.error);

  if (existingMembership.data?.role) {
    return;
  }

  if (!ALLOW_TENANT_BOOTSTRAP) {
    throw new Error("Tenant access is not provisioned for the current user. Set SUPABASE_BOOTSTRAP_TENANT_ACCESS=true only for initial bootstrap.");
  }

  const memberUpsert = await supabase.from("tenant_members").upsert(
    {
      tenant_id: tenantId,
      user_id: user.id,
      role: "admin"
    },
    { onConflict: "tenant_id,user_id" }
  );
  ensureNoError(memberUpsert.error);
}

async function persistDerivedPageAssets(document: DocumentRecord) {
  if (document.documentPages.length === 0) {
    return document;
  }

  const supabase = getSupabaseServerClient();
  await ensureStorageBucket();

  const pages = await Promise.all(
    document.documentPages.map(async (page) => {
      if (!page.imageBase64) {
        return {
          ...page,
          imageBase64: null
        };
      }

      const storagePath = `derived-pages/${document.id}/page-${page.pageNumber}.png`;
      const upload = await supabase.storage.from(getSupabaseStorageBucket()).upload(storagePath, Buffer.from(page.imageBase64, "base64"), {
        contentType: "image/png",
        upsert: true
      });
      ensureNoError(upload.error);

      return {
        ...page,
        imagePath: storagePath,
        imageBase64: null
      };
    })
  );

  return {
    ...document,
    documentPages: pages
  };
}

function slugifyFilename(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9.]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100);
}

function groupByDocumentId<T extends { document_id: string }>(rows: T[]) {
  return rows.reduce<Record<string, T[]>>((accumulator, row) => {
    accumulator[row.document_id] ??= [];
    accumulator[row.document_id].push(row);
    return accumulator;
  }, {});
}

function groupEditsBySession(rows: ReviewEditRow[]) {
  return rows.reduce<Record<string, ReviewEdit[]>>((accumulator, row) => {
    accumulator[row.review_session_id] ??= [];
    accumulator[row.review_session_id].push({
      id: row.id,
      fieldId: row.field_id ?? "",
      fieldName: row.field_name,
      previousValue: row.previous_value,
      newValue: row.new_value,
      reason: row.reason ?? "",
      createdAt: row.created_at,
      reviewerName: row.reviewer_name ?? "Analista OCR"
    });
    return accumulator;
  }, {});
}

function mapIssueRows(rows: ValidationIssueRow[] | undefined): ValidationIssue[] {
  return (rows ?? []).map((row) => ({
    id: row.id,
    type: row.issue_type,
    field: row.field_name,
    severity: row.severity,
    message: row.message,
    suggestedAction: row.suggested_action ?? ""
  }));
}

function mapFieldRows(rows: ExtractedFieldRow[] | undefined): ExtractedField[] {
  return (rows ?? []).map((row) => ({
    id: row.id,
    section: row.section,
    fieldName: row.field_name,
    label: row.label ?? row.field_name,
    rawText: row.raw_text,
    normalizedValue: row.normalized_value,
    valueType: row.value_type ?? "text",
    confidence: row.confidence,
    engine: row.engine ?? "unknown",
    pageNumber: row.page_number,
    bbox: row.bbox,
    evidenceSpan: row.evidence_span,
    validationStatus: row.validation_status,
    reviewStatus: row.review_status,
    isInferred: row.is_inferred,
    issueIds: [],
    candidates: [],
    consensus: null,
    adjudication: null,
    confidenceDetails: null
  }));
}

function mapPageRows(rows: DocumentPageRow[] | undefined): DocumentPageRecord[] {
  return (rows ?? []).map((row) => ({
    id: row.id,
    pageNumber: row.page_number,
    imagePath: row.image_path,
    width: row.width,
    height: row.height,
    orientation: row.orientation ?? 0,
    qualityScore: row.quality_score,
    blurScore: row.blur_score,
    glareScore: row.glare_score,
    cropRatio: null,
    documentCoverage: null,
    edgeConfidence: null,
    skewAngle: null,
    skewApplied: false,
    perspectiveApplied: false,
    captureConditions: [],
    rescueProfiles: [],
    selectedOcrProfile: null,
    corners: [],
    hasEmbeddedText: row.has_embedded_text
  }));
}

function mapReviewSessions(rows: ReviewSessionRow[] | undefined, editsBySession: Record<string, ReviewEdit[]>): ReviewSession[] {
  return (rows ?? []).map((row) => ({
    id: row.id,
    reviewerName: row.reviewer_name ?? "Analista OCR",
    status: row.status,
    notes: row.notes,
    openedAt: row.created_at,
    updatedAt: row.closed_at ?? row.created_at,
    edits: editsBySession[row.id] ?? []
  }));
}

function latestJob(rows: ProcessingJobRow[] | undefined): ProcessingJobRecord | null {
  const row = rows?.[0];

  if (!row) {
    return null;
  }

  return {
    id: row.id,
    status: row.status,
    engine: row.engine ?? "unknown",
    createdAt: row.created_at,
    startedAt: row.started_at,
    finishedAt: row.finished_at,
    errorMessage: row.error_message,
    attemptCount: row.attempt_count ?? 0,
    maxAttempts: row.max_attempts ?? 3,
    nextRetryAt: row.next_retry_at,
    idempotencyKey: row.idempotency_key ?? row.id,
    queueName: row.queue_name ?? "default",
    currentStage: row.current_stage ?? null,
    leaseOwner: row.lease_owner ?? null,
    leaseExpiresAt: row.lease_expires_at ?? null,
    payload: row.payload ?? null,
    result: row.result ?? null,
    stages: Array.isArray(row.result?.stages) ? (row.result?.stages as ProcessingJobRecord["stages"]) : createDefaultProcessingStages()
  };
}

function reportPayload(row: GeneratedReportRow | undefined) {
  return row?.payload ?? {};
}

function mapDocument(
  row: DocumentRow,
  issuesByDocumentId: Record<string, ValidationIssueRow[]>,
  pagesByDocumentId: Record<string, DocumentPageRow[]>,
  fieldsByDocumentId: Record<string, ExtractedFieldRow[]>,
  sessionsByDocumentId: Record<string, ReviewSessionRow[]>,
  editsBySession: Record<string, ReviewEdit[]>,
  jobsByDocumentId: Record<string, ProcessingJobRow[]>,
  reportByDocumentId: Record<string, GeneratedReportRow>
) {
  const issues = mapIssueRows(issuesByDocumentId[row.id]);
  const report = reportPayload(reportByDocumentId[row.id]);
  const fieldCandidatesById = (report.fieldCandidatesById ?? {}) as Record<string, Pick<ExtractedField, "candidates" | "consensus" | "adjudication" | "confidenceDetails">>;
  const extractedFields = mapFieldRows(fieldsByDocumentId[row.id]).map((field) => ({
    ...field,
    issueIds: issues.filter((issue) => issue.field === field.label || issue.field === field.fieldName).map((issue) => issue.id),
    candidates: fieldCandidatesById[field.id]?.candidates ?? [],
    consensus: fieldCandidatesById[field.id]?.consensus ?? null,
    adjudication: fieldCandidatesById[field.id]?.adjudication ?? null,
    confidenceDetails: fieldCandidatesById[field.id]?.confidenceDetails ?? null
  }));

  return normalizeDocumentRecord({
    ...createBaseDocumentRecord({
      id: row.id,
      tenantId: row.tenant_id ?? undefined,
      filename: row.source_filename,
      mimeType: row.mime_type,
      size: row.file_size ?? 0,
      storagePath: row.storage_path,
      documentFamily: row.document_family,
      country: row.country,
      storageProvider: row.storage_provider,
      sourceHash: row.sha256,
      status: row.status,
      decision: row.decision,
      riskLevel: row.risk_level,
      createdAt: row.created_at,
      updatedAt: row.updated_at
    }),
    variant: row.variant,
    issuer: row.issuer,
    holderName: row.holder_name,
    pageCount: row.page_count,
    globalConfidence: row.global_confidence,
    reviewRequired: row.review_required,
    processedAt: row.processed_at,
    lastReviewedAt: row.last_reviewed_at,
    assumptions: report.assumptions ?? [],
    issues,
    extractedFields,
    documentPages: mapPageRows(pagesByDocumentId[row.id]),
    reviewSessions: mapReviewSessions(sessionsByDocumentId[row.id], editsBySession),
    latestJob: latestJob(jobsByDocumentId[row.id]),
    processingMetadata: {
      ...(report.processingMetadata ?? {}),
      packId: row.pack_id ?? report.processingMetadata?.packId ?? null,
      packVersion: row.pack_version ?? report.processingMetadata?.packVersion ?? null,
      documentSide: row.document_side ?? report.processingMetadata?.documentSide ?? null,
      crossSideDetected: row.cross_side_detected ?? report.processingMetadata?.crossSideDetected ?? false,
      decisionProfile: report.processingMetadata?.decisionProfile ?? null,
      requestedVisualEngine: report.processingMetadata?.requestedVisualEngine ?? null,
      selectedVisualEngine: report.processingMetadata?.selectedVisualEngine ?? null,
      ensembleMode: report.processingMetadata?.ensembleMode ?? null,
      classificationConfidence: row.classification_confidence ?? report.processingMetadata?.classificationConfidence ?? null,
      extractionSource: row.extraction_source ?? report.processingMetadata?.extractionSource ?? null,
      processingEngine: row.processing_engine ?? report.processingMetadata?.processingEngine ?? null,
      ocrRuns: report.processingMetadata?.ocrRuns ?? [],
      adjudicationMode: report.processingMetadata?.adjudicationMode ?? null,
      adjudicatedFields: report.processingMetadata?.adjudicatedFields ?? 0,
      adjudicationAbstentions: report.processingMetadata?.adjudicationAbstentions ?? 0,
      processingTrace: report.processingMetadata?.processingTrace ?? []
    },
    reportSections: report.reportSections ?? [],
    humanSummary: row.human_summary,
    reportHtml: row.report_html
  });
}

async function hydrateDocuments(rows: DocumentRow[]) {
  if (rows.length === 0) {
    return [];
  }

  const ids = rows.map((row) => row.id);
  const supabase = getSupabaseServerClient();

  const [issuesResult, pagesResult, fieldsResult, sessionsResult, editsResult, jobsResult, reportsResult] = await Promise.all([
    supabase.from("validation_issues").select("*").in("document_id", ids),
    supabase.from("document_pages").select("*").in("document_id", ids),
    supabase.from("extracted_fields").select("*").in("document_id", ids),
    supabase.from("review_sessions").select("*").in("document_id", ids),
    supabase.from("review_edits").select("*").in("document_id", ids),
    supabase.from("processing_jobs").select("*").in("document_id", ids).order("created_at", { ascending: false }),
    supabase.from("generated_reports").select("*").eq("format", "json").in("document_id", ids)
  ]);

  ensureNoError(issuesResult.error);
  ensureNoError(pagesResult.error);
  ensureNoError(fieldsResult.error);
  ensureNoError(sessionsResult.error);
  ensureNoError(editsResult.error);
  ensureNoError(jobsResult.error);
  ensureNoError(reportsResult.error);

  const issuesByDocumentId = groupByDocumentId((issuesResult.data ?? []) as ValidationIssueRow[]);
  const pagesByDocumentId = groupByDocumentId((pagesResult.data ?? []) as DocumentPageRow[]);
  const fieldsByDocumentId = groupByDocumentId((fieldsResult.data ?? []) as ExtractedFieldRow[]);
  const sessionsByDocumentId = groupByDocumentId((sessionsResult.data ?? []) as ReviewSessionRow[]);
  const editsBySession = groupEditsBySession((editsResult.data ?? []) as ReviewEditRow[]);
  const jobsByDocumentId = groupByDocumentId((jobsResult.data ?? []) as ProcessingJobRow[]);
  const reportByDocumentId = ((reportsResult.data ?? []) as GeneratedReportRow[]).reduce<Record<string, GeneratedReportRow>>(
    (accumulator, row) => {
      accumulator[row.document_id] = row;
      return accumulator;
    },
    {}
  );

  return rows.map((row) =>
    mapDocument(row, issuesByDocumentId, pagesByDocumentId, fieldsByDocumentId, sessionsByDocumentId, editsBySession, jobsByDocumentId, reportByDocumentId)
  );
}

async function persistDocument(document: DocumentRecord) {
  const preparedDocument = await persistDerivedPageAssets(document);
  const supabase = getSupabaseServerClient();
  const tenantId =
    preparedDocument.tenantId && preparedDocument.tenantId !== "local-default-tenant" ? preparedDocument.tenantId : await ensureWorkspaceTenant();
  await ensureUserProfileAndMembership(tenantId);

  const documentRow = {
    id: preparedDocument.id,
    tenant_id: tenantId,
    source_filename: preparedDocument.filename,
    mime_type: preparedDocument.mimeType,
    file_size: preparedDocument.size,
    storage_path: preparedDocument.storagePath,
    storage_provider: preparedDocument.storageProvider,
    sha256: preparedDocument.sourceHash,
    document_family: preparedDocument.documentFamily,
    country: preparedDocument.country,
    variant: preparedDocument.variant,
    pack_id: preparedDocument.processingMetadata.packId,
    pack_version: preparedDocument.processingMetadata.packVersion,
    document_side: preparedDocument.processingMetadata.documentSide,
    cross_side_detected: preparedDocument.processingMetadata.crossSideDetected,
    risk_level: preparedDocument.riskLevel,
    status: preparedDocument.status,
    decision: preparedDocument.decision,
    issuer: preparedDocument.issuer,
    holder_name: preparedDocument.holderName,
    page_count: preparedDocument.pageCount,
    global_confidence: preparedDocument.globalConfidence,
    classification_confidence: preparedDocument.processingMetadata.classificationConfidence,
    extraction_source: preparedDocument.processingMetadata.extractionSource,
    processing_engine: preparedDocument.processingMetadata.processingEngine,
    report_html: preparedDocument.reportHtml,
    human_summary: preparedDocument.humanSummary,
    review_required: preparedDocument.reviewRequired,
    created_at: preparedDocument.createdAt,
    updated_at: preparedDocument.updatedAt,
    processed_at: preparedDocument.processedAt,
    last_reviewed_at: preparedDocument.lastReviewedAt
  };

  const documentWrite = await supabase.from("documents").upsert(documentRow, { onConflict: "id" });
  ensureNoError(documentWrite.error);

  const issueStableIds = preparedDocument.issues.map((issue, index) => coerceUuid(`${issue.id}:${index}`, `${preparedDocument.id}:issue`));
  const pageStableIds = preparedDocument.documentPages.map((page, index) => coerceUuid(`${page.id}:${page.pageNumber}:${index}`, `${preparedDocument.id}:page`));
  const fieldStableIds = preparedDocument.extractedFields.map((field, index) => coerceUuid(`${field.id}:${field.fieldName}:${field.pageNumber}:${index}`, `${preparedDocument.id}:field`));
  const fieldStableIdLookup = new Map(preparedDocument.extractedFields.map((field, index) => [field.id, fieldStableIds[index]]));

  async function persistIssues() {
    const issuesDelete = await supabase.from("validation_issues").delete().eq("document_id", preparedDocument.id);
    ensureNoError(issuesDelete.error);
    if (preparedDocument.issues.length === 0) return;
    const issuesWrite = await supabase.from("validation_issues").insert(
      preparedDocument.issues.map((issue, index) => ({
        id: issueStableIds[index],
        document_id: preparedDocument.id,
        field_name: issue.field,
        issue_type: issue.type,
        severity: issue.severity,
        message: issue.message,
        suggested_action: issue.suggestedAction,
        created_at: preparedDocument.updatedAt
      }))
    );
    ensureNoError(issuesWrite.error);
  }

  async function persistPages() {
    const pagesDelete = await supabase.from("document_pages").delete().eq("document_id", preparedDocument.id);
    ensureNoError(pagesDelete.error);
    if (preparedDocument.documentPages.length === 0) return;
    const pagesWrite = await supabase.from("document_pages").insert(
      preparedDocument.documentPages.map((page, index) => ({
        id: pageStableIds[index],
        document_id: preparedDocument.id,
        page_number: page.pageNumber,
        image_path: page.imagePath,
        width: page.width,
        height: page.height,
        orientation: page.orientation,
        quality_score: page.qualityScore,
        blur_score: page.blurScore,
        glare_score: page.glareScore,
        has_embedded_text: page.hasEmbeddedText,
        created_at: preparedDocument.updatedAt
      }))
    );
    ensureNoError(pagesWrite.error);
  }

  async function persistFields() {
    const fieldsDelete = await supabase.from("extracted_fields").delete().eq("document_id", preparedDocument.id);
    ensureNoError(fieldsDelete.error);
    if (preparedDocument.extractedFields.length === 0) return;
    const fieldsWrite = await supabase.from("extracted_fields").insert(
      preparedDocument.extractedFields.map((field, index) => ({
        id: fieldStableIds[index],
        document_id: preparedDocument.id,
        page_number: field.pageNumber,
        section: field.section,
        field_name: field.fieldName,
        label: field.label,
        raw_text: field.rawText,
        normalized_value: field.normalizedValue,
        value_type: field.valueType,
        confidence: field.confidence,
        engine: field.engine,
        bbox: field.bbox,
        evidence_span: field.evidenceSpan,
        validation_status: field.validationStatus,
        review_status: field.reviewStatus,
        is_inferred: field.isInferred,
        created_at: preparedDocument.updatedAt
      }))
    );
    ensureNoError(fieldsWrite.error);
  }

  async function persistReport() {
    const reportDelete = await supabase.from("generated_reports").delete().eq("document_id", preparedDocument.id);
    ensureNoError(reportDelete.error);
    const reportWrite = await supabase.from("generated_reports").insert({
      id: crypto.randomUUID(),
      document_id: preparedDocument.id,
      format: "json",
      payload: {
        assumptions: preparedDocument.assumptions,
        reportSections: preparedDocument.reportSections,
        processingMetadata: preparedDocument.processingMetadata,
        fieldCandidatesById: Object.fromEntries(
          preparedDocument.extractedFields.map((field, index) => [
            fieldStableIds[index],
            {
              candidates: field.candidates,
              consensus: field.consensus,
              adjudication: field.adjudication,
              confidenceDetails: field.confidenceDetails ?? null
            }
          ])
        )
      },
      created_at: preparedDocument.updatedAt
    });
    ensureNoError(reportWrite.error);
  }

  async function persistReviews() {
    const sessionStableIds = new Map(preparedDocument.reviewSessions.map((session, index) => [session.id, coerceUuid(`${session.id}:${index}`, `${preparedDocument.id}:review-session`)]));
    const [editsDelete, sessionsDelete] = await Promise.all([
      supabase.from("review_edits").delete().eq("document_id", preparedDocument.id),
      supabase.from("review_sessions").delete().eq("document_id", preparedDocument.id),
    ]);
    ensureNoError(editsDelete.error);
    ensureNoError(sessionsDelete.error);
    if (preparedDocument.reviewSessions.length === 0) return;
    const sessionsWrite = await supabase.from("review_sessions").insert(
      preparedDocument.reviewSessions.map((session) => ({
        id: sessionStableIds.get(session.id) ?? coerceUuid(session.id, `${preparedDocument.id}:review-session`),
        document_id: preparedDocument.id,
        reviewer_name: session.reviewerName,
        status: session.status,
        notes: session.notes,
        created_at: session.openedAt,
        closed_at: session.status === "completed" ? session.updatedAt : null
      }))
    );
    ensureNoError(sessionsWrite.error);

    const edits = preparedDocument.reviewSessions.flatMap((session, sessionIndex) =>
      session.edits.map((edit, editIndex) => ({
        id: coerceUuid(edit.id, `${preparedDocument.id}:review-edit:${sessionIndex}:${editIndex}`),
        review_session_id: sessionStableIds.get(session.id) ?? coerceUuid(session.id, `${preparedDocument.id}:review-session`),
        document_id: preparedDocument.id,
        field_id: edit.fieldId ? (fieldStableIdLookup.get(edit.fieldId) ?? coerceUuid(edit.fieldId, `${preparedDocument.id}:field-ref`)) : null,
        field_name: edit.fieldName,
        previous_value: edit.previousValue,
        new_value: edit.newValue,
        reason: edit.reason,
        reviewer_name: edit.reviewerName,
        created_at: edit.createdAt
      }))
    );

    if (edits.length === 0) return;
    const editsWrite = await supabase.from("review_edits").insert(edits);
    ensureNoError(editsWrite.error);
  }

  async function persistJob() {
    if (!preparedDocument.latestJob) return;
    const jobWrite = await supabase.from("processing_jobs").upsert(
      {
        id: coerceUuid(preparedDocument.latestJob.id, `${preparedDocument.id}:job`),
        document_id: preparedDocument.id,
        job_type: "document_processing",
        status: preparedDocument.latestJob.status,
        engine: preparedDocument.latestJob.engine,
        attempt_count: preparedDocument.latestJob.attemptCount,
        max_attempts: preparedDocument.latestJob.maxAttempts,
        next_retry_at: preparedDocument.latestJob.nextRetryAt,
        idempotency_key: preparedDocument.latestJob.idempotencyKey,
        queue_name: preparedDocument.latestJob.queueName,
        current_stage: preparedDocument.latestJob.currentStage,
        lease_owner: preparedDocument.latestJob.leaseOwner ?? null,
        lease_expires_at: preparedDocument.latestJob.leaseExpiresAt ?? null,
        payload: preparedDocument.latestJob.payload ?? {},
        result: {
          ...(preparedDocument.latestJob.result ?? {}),
          stages: preparedDocument.latestJob.stages
        },
        error_message: preparedDocument.latestJob.errorMessage,
        created_at: preparedDocument.latestJob.createdAt,
        started_at: preparedDocument.latestJob.startedAt,
        finished_at: preparedDocument.latestJob.finishedAt
      },
      { onConflict: "id" }
    );
    ensureNoError(jobWrite.error);
  }

  await Promise.all([persistIssues(), persistPages(), persistFields(), persistReport(), persistReviews(), persistJob()]);

  return preparedDocument;
}

export class SupabaseDocumentRepository implements DocumentRepository {
  readonly storageProvider = "supabase" as const;

  async listDocuments() {
    const supabase = getSupabaseServerClient();
    const tenantId = await ensureWorkspaceTenant();
    await ensureUserProfileAndMembership(tenantId);
    const result = await supabase.from("documents").select("*").eq("tenant_id", tenantId).order("updated_at", { ascending: false });
    ensureNoError(result.error);
    return hydrateDocuments((result.data ?? []) as DocumentRow[]);
  }

  async getDocumentById(documentId: string) {
    const supabase = getSupabaseServerClient();
    const tenantId = await ensureWorkspaceTenant();
    await ensureUserProfileAndMembership(tenantId);
    const result = await supabase.from("documents").select("*").eq("tenant_id", tenantId).eq("id", documentId).maybeSingle();
    ensureNoError(result.error);

    if (!result.data) {
      return null;
    }

    const [document] = await hydrateDocuments([result.data as DocumentRow]);
    return document ?? null;
  }

  async getDocumentByIdInternal(documentId: string) {
    const supabase = getSupabaseServerClient();
    const result = await supabase.from("documents").select("*").eq("id", documentId).maybeSingle();
    ensureNoError(result.error);

    if (!result.data) {
      return null;
    }

    const [document] = await hydrateDocuments([result.data as DocumentRow]);
    return document ?? null;
  }

  async createDocumentFromUpload(input: CreateDocumentInput) {
    const id = crypto.randomUUID();
    const buffer = Buffer.from(await input.file.arrayBuffer());
    const timestamp = new Date().toISOString();
    const storagePath = `${id}-${slugifyFilename(input.file.name) || "documento.bin"}`;
    const supabase = getSupabaseServerClient();
    const tenantId = input.tenantId ?? (await ensureWorkspaceTenant());
    if (!input.tenantId) {
      await ensureUserProfileAndMembership(tenantId);
    }
    await ensureStorageBucket();
    const upload = await supabase.storage.from(getSupabaseStorageBucket()).upload(storagePath, buffer, {
      contentType: input.file.type || "application/octet-stream",
      upsert: true
    });
    ensureNoError(upload.error);

    const document = normalizeDocumentRecord(
      createBaseDocumentRecord({
        id,
        tenantId,
        filename: input.file.name,
        mimeType: input.file.type || "application/octet-stream",
        size: buffer.byteLength,
        storagePath,
        documentFamily: input.documentFamily,
        country: input.country,
        storageProvider: this.storageProvider,
        sourceHash: createHash("sha256").update(buffer).digest("hex"),
        createdAt: timestamp,
        updatedAt: timestamp
      })
    );

    return persistDocument(document);
  }

  async updateDocument(documentId: string, updater: (document: DocumentRecord) => DocumentRecord) {
    const current = await this.getDocumentById(documentId);

    if (!current) {
      return null;
    }

    const updated = normalizeDocumentRecord(updater(current));
    return persistDocument(updated);
  }
}
