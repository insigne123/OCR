import { getPublicApiLimits, getPublicApiClients, isPublicApiAuthConfigured } from "@/lib/public-api-auth";

export async function GET() {
  const limits = getPublicApiLimits();
  return Response.json({
    status: "ok",
    service: "public-ocr-api",
    authConfigured: isPublicApiAuthConfigured(),
    clientsConfigured: getPublicApiClients().length,
    limits: {
      maxSingleFileBytes: limits.maxSingleFileBytes,
      maxBatchItems: limits.maxBatchItems,
      maxBatchBytes: limits.maxBatchBytes,
      maxManifestItems: limits.maxManifestItems,
      maxSyncBatchItems: limits.maxSyncBatchItems,
      defaultProcessingMode: limits.defaultProcessingMode,
      allowedMimeTypes: limits.allowedMimeTypes,
    },
  });
}
