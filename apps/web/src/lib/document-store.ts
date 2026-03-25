import type { DocumentDecision, DocumentFamily, DocumentRecord, DocumentStatus, ReviewEdit, ReviewSession } from "@ocr/shared";
import { readFile } from "fs/promises";
import { buildReportHtml } from "./report-html";
import { recordOpsAuditEvent } from "./ops-audit";
import { getLocalAbsolutePath, getLocalAbsoluteStoragePath } from "./persistence/local-document-repository";
import { getDocumentRepository } from "./persistence";
import { createSignedStorageUrl, getSupabaseServerClient, getSupabaseStorageBucket } from "./supabase/server";

function nowIso() {
  return new Date().toISOString();
}

function createReviewEdit(input: {
  fieldId: string;
  fieldName: string;
  previousValue: string | null;
  newValue: string | null;
  reason: string;
  reviewerName: string;
}): ReviewEdit {
  return {
    id: crypto.randomUUID(),
    fieldId: input.fieldId,
    fieldName: input.fieldName,
    previousValue: input.previousValue,
    newValue: input.newValue,
    reason: input.reason,
    createdAt: nowIso(),
    reviewerName: input.reviewerName
  };
}

function getOrCreateOpenReviewSession(document: DocumentRecord, reviewerName: string) {
  const existing = document.reviewSessions.find((session) => session.status === "open");
  if (existing) {
    return existing;
  }

  return {
    id: crypto.randomUUID(),
    reviewerName,
    status: "open" as const,
    notes: null,
    openedAt: nowIso(),
    updatedAt: nowIso(),
    edits: []
  };
}

function upsertReviewSession(document: DocumentRecord, session: ReviewSession) {
  const sessions = document.reviewSessions.filter((entry) => entry.id !== session.id);
  return [...sessions, session].sort((left, right) => new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime());
}

function updateReportSectionsFromField(document: DocumentRecord, fieldId: string, nextValue: string) {
  const targetField = document.extractedFields.find((field) => field.id === fieldId);

  if (!targetField) {
    return document.reportSections;
  }

  return document.reportSections.map((section) => {
    if (section.id !== targetField.section) return section;

    if (section.variant === "pairs" && section.rows) {
      return {
        ...section,
        rows: section.rows.map((row) => (row[0] === targetField.label ? [row[0], nextValue] : row))
      };
    }

    if (section.variant === "table" && section.columns && section.rows) {
      if (section.columns[0]?.toLowerCase() === "campo") {
        return {
          ...section,
          rows: section.rows.map((row) => (row[0] === targetField.label ? [row[0], nextValue] : row))
        };
      }

      const [rowContext, columnLabel] = targetField.label.split(" · ");
      const columnIndex = section.columns.indexOf(columnLabel);

      if (!rowContext || columnIndex === -1) {
        return section;
      }

      return {
        ...section,
        rows: section.rows.map((row) => {
          if (row[0] !== rowContext) return row;
          return row.map((cell, index) => (index === columnIndex ? nextValue : cell));
        })
      };
    }

    if (section.variant === "text" && section.title === targetField.label) {
      return {
        ...section,
        body: nextValue
      };
    }

    return section;
  });
}

export async function getAllDocuments() {
  return getDocumentRepository().listDocuments();
}

export async function getDocumentById(documentId: string) {
  return getDocumentRepository().getDocumentById(documentId);
}

export async function getDocumentByIdInternal(documentId: string) {
  return getDocumentRepository().getDocumentByIdInternal(documentId);
}

export async function getReviewQueueDocuments() {
  const documents = await getAllDocuments();
  return documents.filter((document) => document.reviewRequired || document.status === "review");
}

export async function getReportReadyDocuments() {
  const documents = await getAllDocuments();
  return documents.filter((document) => Boolean(document.reportHtml));
}

export async function getJobFeed() {
  const documents = await getAllDocuments();

  return documents
    .filter((document) => document.latestJob)
    .map((document) => ({
      document,
      job: document.latestJob
    }))
    .sort((left, right) => new Date(right.job!.createdAt).getTime() - new Date(left.job!.createdAt).getTime());
}

export async function createDocumentFromUpload(input: {
  file: File;
  documentFamily: DocumentFamily;
  country: string;
  tenantId?: string;
}) {
  return getDocumentRepository().createDocumentFromUpload(input);
}

export async function updateDocument(documentId: string, updater: (document: DocumentRecord) => DocumentRecord) {
  return getDocumentRepository().updateDocument(documentId, updater);
}

export async function recordReviewEdit(input: {
  documentId: string;
  fieldId: string;
  newValue: string;
  reason: string;
  reviewerName: string;
}) {
  const updated = await updateDocument(input.documentId, (document) => {
    const targetField = document.extractedFields.find((field) => field.id === input.fieldId);

    if (!targetField) {
      return document;
    }

    const session = getOrCreateOpenReviewSession(document, input.reviewerName);
    const edit = createReviewEdit({
      fieldId: targetField.id,
      fieldName: targetField.fieldName,
      previousValue: targetField.normalizedValue,
      newValue: input.newValue,
      reason: input.reason,
      reviewerName: input.reviewerName
    });

    const updatedSession: ReviewSession = {
      ...session,
      updatedAt: nowIso(),
      edits: [...session.edits, edit]
    };

    const reportSections = updateReportSectionsFromField(document, input.fieldId, input.newValue);

    const nextDocument: DocumentRecord = {
      ...document,
      status: "review",
      reviewRequired: true,
      updatedAt: nowIso(),
      lastReviewedAt: nowIso(),
      reviewSessions: upsertReviewSession(document, updatedSession),
      extractedFields: document.extractedFields.map((field) => {
        if (field.id !== input.fieldId) return field;

        return {
          ...field,
          normalizedValue: input.newValue,
          reviewStatus: "corrected" as const,
          validationStatus: field.issueIds.length > 0 ? field.validationStatus : ("valid" as const),
          adjudication: null
        };
      }),
      reportSections
    };

    return {
      ...nextDocument,
      reportHtml: buildReportHtml(nextDocument)
    };
  });

  if (updated) {
    await recordOpsAuditEvent({
      action: "review.edit",
      tenantId: updated.tenantId,
      documentId: updated.id,
      payload: {
        fieldId: input.fieldId,
        fieldName: updated.extractedFields.find((field) => field.id === input.fieldId)?.fieldName ?? null,
        reviewerName: input.reviewerName,
        reason: input.reason,
      },
    })
  }

  return updated
}

export async function completeReview(input: {
  documentId: string;
  reviewerName: string;
  notes?: string;
  decision?: DocumentDecision;
}) {
  const updated = await updateDocument(input.documentId, (document) => {
    const session = getOrCreateOpenReviewSession(document, input.reviewerName);
    const decision = input.decision ?? (document.issues.length > 0 ? "accept_with_warning" : "auto_accept");
    const status: DocumentStatus =
      decision === "reject" ? "rejected" : decision === "human_review" ? "review" : "completed";

    const updatedSession: ReviewSession = {
      ...session,
      status: "completed",
      notes: input.notes ?? session.notes,
      updatedAt: nowIso()
    };

    const nextDocument: DocumentRecord = {
      ...document,
      status,
      decision,
      reviewRequired: decision === "human_review",
      updatedAt: nowIso(),
      lastReviewedAt: nowIso(),
      reviewSessions: upsertReviewSession(document, updatedSession)
    };

    return {
      ...nextDocument,
      reportHtml: buildReportHtml(nextDocument)
    };
  });

  if (updated) {
    await recordOpsAuditEvent({
      action: "review.complete",
      tenantId: updated.tenantId,
      documentId: updated.id,
      payload: {
        reviewerName: input.reviewerName,
        decision: updated.decision,
        notes: input.notes ?? null,
      },
    })
  }

  return updated
}

export function getAbsoluteStoragePath(document: DocumentRecord) {
  return getLocalAbsoluteStoragePath(document);
}

export async function readDocumentBinary(document: DocumentRecord) {
  return readBinaryFromStorage(document.storageProvider, document.storagePath);
}

export async function readBinaryFromStorage(storageProvider: DocumentRecord["storageProvider"], storagePath: string) {
  if (storageProvider === "supabase") {
    const download = await getSupabaseServerClient().storage.from(getSupabaseStorageBucket()).download(storagePath);

    if (download.error) {
      throw new Error(download.error.message);
    }

    return Buffer.from(await download.data.arrayBuffer());
  }

  return readFile(getLocalAbsolutePath(storagePath));
}

export async function getDocumentSignedUrl(document: DocumentRecord, expiresIn = 60) {
  return getStorageSignedUrl(document.storageProvider, document.storagePath, expiresIn);
}

export async function getStorageSignedUrl(storageProvider: DocumentRecord["storageProvider"], storagePath: string, expiresIn = 60) {
  if (storageProvider !== "supabase") {
    return null;
  }

  return createSignedStorageUrl(storagePath, expiresIn);
}

export function getStorageRuntimeLabel() {
  return getDocumentRepository().storageProvider === "supabase" ? "Supabase ready" : "Local file store";
}
