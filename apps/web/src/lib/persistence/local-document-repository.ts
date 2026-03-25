import type { DocumentRecord } from "@ocr/shared";
import { createHash } from "node:crypto";
import { access, mkdir, readFile, writeFile } from "fs/promises";
import path from "path";
import { createBaseDocumentRecord, createJobSnapshot, normalizeDocumentRecord } from "@/lib/document-record";
import { buildProcessedMockDocument } from "@/lib/mock-pipeline";
import { buildReportHtml } from "@/lib/report-html";
import type { CreateDocumentInput, DocumentRepository } from "./types";

const dataDirectory = path.join(process.cwd(), ".data");
const uploadDirectory = path.join(dataDirectory, "uploads");
const derivedPagesDirectory = path.join(dataDirectory, "derived-pages");
const documentsFile = path.join(dataDirectory, "documents.json");

function slugifyFilename(value: string) {
  const extension = path.extname(value);
  const basename = path.basename(value, extension);
  const slug = basename
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);

  return `${slug || "documento"}${extension.toLowerCase()}`;
}

function createSeedDocument(): DocumentRecord {
  const base = createBaseDocumentRecord({
    id: "demo-certificado-001",
    filename: "demo_certificado_cotizaciones.pdf",
    mimeType: "application/pdf",
    size: 248392,
    storagePath: "uploads/demo_certificado_cotizaciones.pdf",
    documentFamily: "certificate",
    country: "CL",
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 12).toISOString(),
    updatedAt: new Date(Date.now() - 1000 * 60 * 60 * 12).toISOString(),
    sourceHash: "demo-seed-hash",
    storageProvider: "local"
  });

  const processed = buildProcessedMockDocument(base);

  return normalizeDocumentRecord({
    ...processed,
    latestJob: createJobSnapshot({
      status: "completed",
      engine: "mock-pipeline",
      createdAt: processed.createdAt,
      startedAt: processed.createdAt,
      finishedAt: processed.updatedAt
    }),
    reportHtml: buildReportHtml(processed)
  });
}

async function ensureStore() {
  await mkdir(uploadDirectory, { recursive: true });
  await mkdir(derivedPagesDirectory, { recursive: true });

  try {
    await access(documentsFile);
  } catch {
    await writeFile(documentsFile, JSON.stringify([createSeedDocument()], null, 2), "utf-8");
  }
}

async function readDocuments() {
  await ensureStore();
  const contents = await readFile(documentsFile, "utf-8");
  const parsed = JSON.parse(contents) as Array<Partial<DocumentRecord>>;
  return parsed.map((document) => normalizeDocumentRecord(document));
}

async function writeDocuments(documents: DocumentRecord[]) {
  await ensureStore();
  await writeFile(documentsFile, JSON.stringify(documents.map((document) => normalizeDocumentRecord(document)), null, 2), "utf-8");
}

export function getLocalAbsoluteStoragePath(document: DocumentRecord) {
  return path.join(process.cwd(), ".data", document.storagePath);
}

export function getLocalAbsolutePath(storagePath: string) {
  return path.join(process.cwd(), ".data", storagePath);
}

async function persistDerivedPages(document: DocumentRecord) {
  if (document.documentPages.length === 0) {
    return document;
  }

  let mutated = false;
  const persistedPages = [];

  for (const page of document.documentPages) {
    if (!page.imageBase64) {
      persistedPages.push({ ...page, imageBase64: null });
      continue;
    }

    const folder = path.join(derivedPagesDirectory, document.id);
    await mkdir(folder, { recursive: true });
    const relativePath = path.join("derived-pages", document.id, `page-${page.pageNumber}.png`).replaceAll("\\", "/");
    await writeFile(path.join(process.cwd(), ".data", relativePath), Buffer.from(page.imageBase64, "base64"));
    persistedPages.push({
      ...page,
      imagePath: relativePath,
      imageBase64: null
    });
    mutated = true;
  }

  return mutated ? { ...document, documentPages: persistedPages } : { ...document, documentPages: persistedPages };
}

export class LocalDocumentRepository implements DocumentRepository {
  readonly storageProvider = "local" as const;

  async listDocuments() {
    const documents = await readDocuments();
    return documents.sort((left, right) => new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime());
  }

  async getDocumentById(documentId: string) {
    const documents = await readDocuments();
    return documents.find((document) => document.id === documentId) ?? null;
  }

  async getDocumentByIdInternal(documentId: string) {
    return this.getDocumentById(documentId);
  }

  async createDocumentFromUpload(input: CreateDocumentInput) {
    const documents = await readDocuments();
    const id = crypto.randomUUID();
    const safeFilename = slugifyFilename(input.file.name);
    const storedFilename = `${id}-${safeFilename}`;
    const relativeStoragePath = path.join("uploads", storedFilename).replaceAll("\\", "/");
    const absoluteStoragePath = path.join(uploadDirectory, storedFilename);
    const buffer = Buffer.from(await input.file.arrayBuffer());

    await writeFile(absoluteStoragePath, buffer);

    const timestamp = new Date().toISOString();
    const document = normalizeDocumentRecord(
      createBaseDocumentRecord({
        id,
        tenantId: input.tenantId,
        filename: input.file.name,
        mimeType: input.file.type || "application/octet-stream",
        size: buffer.byteLength,
        storagePath: relativeStoragePath,
        documentFamily: input.documentFamily,
        country: input.country,
        sourceHash: createHash("sha256").update(buffer).digest("hex"),
        storageProvider: this.storageProvider,
        createdAt: timestamp,
        updatedAt: timestamp
      })
    );

    documents.push(document);
    await writeDocuments(documents);
    return document;
  }

  async updateDocument(documentId: string, updater: (document: DocumentRecord) => DocumentRecord) {
    const documents = await readDocuments();
    const index = documents.findIndex((document) => document.id === documentId);

    if (index === -1) {
      return null;
    }

    const updated = await persistDerivedPages(normalizeDocumentRecord(updater(documents[index])));
    documents[index] = updated;
    await writeDocuments(documents);
    return updated;
  }
}
