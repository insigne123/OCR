import type { DocumentFamily } from "@ocr/shared";

import type { PublicApiClient, PublicApiProcessingMode } from "@/lib/public-api-types";

const DEFAULT_DEV_API_KEY = "public-dev-key";
const DEFAULT_TENANT_ID = "public-default-tenant";
const DEFAULT_TRIAL_DOCUMENT_LIMIT = 50;
const DEFAULT_ALLOWED_MIME_TYPES = [
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/heic",
  "image/heif",
  "image/tiff",
] as const;

function coercePositiveInteger(value: string | undefined, fallback: number) {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function normalizeClientMode(value: unknown): PublicApiClient["accessMode"] {
  return value === "trial" ? "trial" : "public";
}

function normalizeProcessingMode(value: unknown): PublicApiProcessingMode | null {
  if (value === "queue") return "queue";
  if (value === "sync") return "sync";
  return null;
}

function buildClient(record: Record<string, unknown>, fallback: { id: string; name: string; tenantId: string; apiKey: string; accessMode?: "public" | "trial" }): PublicApiClient | null {
  const apiKey = typeof record.apiKey === "string" ? record.apiKey : typeof record.key === "string" ? record.key : fallback.apiKey;
  if (!apiKey) return null;
  return {
    id: typeof record.id === "string" ? record.id : fallback.id,
    name: typeof record.name === "string" ? record.name : fallback.name,
    tenantId: typeof record.tenantId === "string" ? record.tenantId : fallback.tenantId,
    apiKey,
    accessMode: normalizeClientMode(record.accessMode ?? fallback.accessMode),
    documentLimit: typeof record.documentLimit === "number" ? record.documentLimit : typeof record.trialDocumentLimit === "number" ? record.trialDocumentLimit : null,
    expiresAt: typeof record.expiresAt === "string" ? record.expiresAt : typeof record.trialExpiresAt === "string" ? record.trialExpiresAt : null,
    allowCallbacks: typeof record.allowCallbacks === "boolean" ? record.allowCallbacks : false,
    forceProcessingMode: normalizeProcessingMode(record.forceProcessingMode),
  };
}

function parseApiClientsFromEnv(): PublicApiClient[] {
  const raw = process.env.OCR_PUBLIC_API_KEYS;
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (Array.isArray(parsed)) {
        return parsed
          .map((entry, index) => {
            if (!entry || typeof entry !== "object") return null;
            return buildClient(entry as Record<string, unknown>, {
              id: `public-client-${index + 1}`,
              name: `Public Client ${index + 1}`,
              tenantId: DEFAULT_TENANT_ID,
              apiKey: "",
              accessMode: "public",
            });
          })
          .filter((entry): entry is PublicApiClient => Boolean(entry));
      }
    } catch {
      return [];
    }
  }

  if (process.env.OCR_PUBLIC_API_KEY) {
    return [
      {
        id: process.env.OCR_PUBLIC_API_CLIENT_ID ?? "public-default-client",
        name: process.env.OCR_PUBLIC_API_CLIENT_NAME ?? "Default Public Client",
        tenantId: process.env.OCR_PUBLIC_DEFAULT_TENANT_ID ?? DEFAULT_TENANT_ID,
        apiKey: process.env.OCR_PUBLIC_API_KEY,
        accessMode: "public",
        allowCallbacks: true,
        forceProcessingMode: null,
        documentLimit: null,
        expiresAt: null,
      },
    ];
  }

  return [];
}

function parseTrialClientsFromEnv(): PublicApiClient[] {
  const raw = process.env.OCR_TRIAL_API_KEYS;
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (Array.isArray(parsed)) {
        return parsed
          .map((entry, index) => {
            if (!entry || typeof entry !== "object") return null;
            return buildClient(entry as Record<string, unknown>, {
              id: `trial-client-${index + 1}`,
              name: `Trial Client ${index + 1}`,
              tenantId: process.env.OCR_TRIAL_DEFAULT_TENANT_ID ?? DEFAULT_TENANT_ID,
              apiKey: "",
              accessMode: "trial",
            });
          })
          .filter((entry): entry is PublicApiClient => Boolean(entry))
          .map((entry) => ({
            ...entry,
            accessMode: "trial",
            documentLimit: entry.documentLimit ?? DEFAULT_TRIAL_DOCUMENT_LIMIT,
            allowCallbacks: entry.allowCallbacks ?? false,
            forceProcessingMode: entry.forceProcessingMode ?? "sync",
          }));
      }
    } catch {
      return [];
    }
  }

  if (process.env.OCR_TRIAL_API_KEY) {
    return [
      {
        id: process.env.OCR_TRIAL_API_CLIENT_ID ?? "trial-default-client",
        name: process.env.OCR_TRIAL_API_CLIENT_NAME ?? "Trial Default Client",
        tenantId: process.env.OCR_TRIAL_DEFAULT_TENANT_ID ?? DEFAULT_TENANT_ID,
        apiKey: process.env.OCR_TRIAL_API_KEY,
        accessMode: "trial",
        documentLimit: coercePositiveInteger(process.env.OCR_TRIAL_DOCUMENT_LIMIT, DEFAULT_TRIAL_DOCUMENT_LIMIT),
        expiresAt: process.env.OCR_TRIAL_EXPIRES_AT ?? null,
        allowCallbacks: process.env.OCR_TRIAL_ALLOW_CALLBACKS === "true",
        forceProcessingMode: "sync",
      },
    ];
  }

  return [];
}

function allowLocalDevClient() {
  if (process.env.OCR_PUBLIC_ALLOW_DEV_AUTH === "false") {
    return false;
  }
  return process.env.NODE_ENV !== "production";
}

export function getPublicApiClients(): PublicApiClient[] {
  const configured = parseApiClientsFromEnv();
  if (configured.length > 0) {
    return configured;
  }

  if (!allowLocalDevClient()) {
    return [];
  }

  return [
    {
      id: "public-local-dev",
      name: "Local Public Dev",
      tenantId: process.env.OCR_PUBLIC_DEFAULT_TENANT_ID ?? DEFAULT_TENANT_ID,
      apiKey: DEFAULT_DEV_API_KEY,
      accessMode: "public",
      allowCallbacks: true,
      forceProcessingMode: null,
      documentLimit: null,
      expiresAt: null,
    },
  ];
}

export function getTrialApiClients(): PublicApiClient[] {
  return parseTrialClientsFromEnv();
}

export function isPublicApiAuthConfigured() {
  return parseApiClientsFromEnv().length > 0;
}

export function isTrialApiAuthConfigured() {
  return parseTrialClientsFromEnv().length > 0;
}

function extractApiKey(request: Request) {
  const direct = request.headers.get("x-api-key");
  if (direct) return direct.trim();

  const authorization = request.headers.get("authorization") ?? request.headers.get("Authorization");
  if (!authorization) return null;
  const [scheme, token] = authorization.split(" ", 2);
  if (scheme?.toLowerCase() !== "bearer" || !token) return null;
  return token.trim();
}

export function authenticatePublicApiRequest(request: Request) {
  const apiKey = extractApiKey(request);
  const clients = getPublicApiClients();
  const configured = isPublicApiAuthConfigured();

  if (!configured && !apiKey) {
    return { configured: false, client: clients[0] ?? null };
  }

  const client = clients.find((entry) => entry.apiKey === apiKey);
  if (!client) {
    return { configured, client: null };
  }

  return { configured, client };
}

export function authenticateTrialApiRequest(request: Request) {
  const apiKey = extractApiKey(request);
  const clients = getTrialApiClients();
  const client = clients.find((entry) => entry.apiKey === apiKey);
  return { configured: clients.length > 0, client: client ?? null };
}

export function ensurePublicApiClient(request: Request) {
  const auth = authenticatePublicApiRequest(request);
  if (!auth.client) {
    return Response.json({ error: "Unauthorized public API client." }, { status: 401 });
  }
  return auth.client;
}

export function ensureTrialApiClient(request: Request) {
  const auth = authenticateTrialApiRequest(request);
  if (!auth.client) {
    return Response.json({ error: "Unauthorized trial API client." }, { status: 401 });
  }
  return auth.client;
}

export function getPublicApiLimits() {
  return {
    maxSingleFileBytes: coercePositiveInteger(process.env.OCR_PUBLIC_MAX_FILE_BYTES, 15 * 1024 * 1024),
    maxBatchItems: coercePositiveInteger(process.env.OCR_PUBLIC_MAX_BATCH_ITEMS, 20),
    maxBatchBytes: coercePositiveInteger(process.env.OCR_PUBLIC_MAX_BATCH_BYTES, 100 * 1024 * 1024),
    maxManifestItems: coercePositiveInteger(process.env.OCR_PUBLIC_MAX_MANIFEST_ITEMS, 100),
    maxSyncBatchItems: coercePositiveInteger(process.env.OCR_PUBLIC_MAX_SYNC_BATCH_ITEMS, 5),
    defaultProcessingMode: ((process.env.OCR_PUBLIC_DEFAULT_PROCESSING_MODE ?? "sync").toLowerCase() === "queue" ? "queue" : "sync") as PublicApiProcessingMode,
    allowedMimeTypes: [...DEFAULT_ALLOWED_MIME_TYPES],
  };
}

export function normalizeRequestedProcessingMode(value: FormDataEntryValue | string | null | undefined): PublicApiProcessingMode {
  return typeof value === "string" && value.toLowerCase() === "queue" ? "queue" : "sync";
}

export function normalizeRequestedDocumentFamily(value: FormDataEntryValue | string | null | undefined): DocumentFamily {
  const candidate = typeof value === "string" ? value : "unclassified";
  const allowed: DocumentFamily[] = ["certificate", "identity", "passport", "driver_license", "invoice", "mixed", "unclassified"];
  return allowed.includes(candidate as DocumentFamily) ? (candidate as DocumentFamily) : "unclassified";
}
