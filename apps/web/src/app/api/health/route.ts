import { hasSupabasePublicConfig } from "@/lib/supabase/config";
import { getOcrApiUrl } from "@/lib/ocr-config";
import { getAllDocuments } from "@/lib/document-store";
import { buildMetricsSnapshot } from "@/lib/ops-metrics";
import { getWebFeatureFlags } from "@/lib/runtime-flags";

export async function GET() {
  const ocrApiUrl = getOcrApiUrl();
  let ocrApi = "not_configured";
  let ocrApiDetails: unknown = null;
  const documents = await getAllDocuments();

  try {
    const response = await fetch(`${ocrApiUrl}/v1/health`, {
      cache: "no-store"
    });
    ocrApi = response.ok ? "ok" : `http_${response.status}`;
    ocrApiDetails = response.ok ? await response.json() : null;
  } catch {
    ocrApi = "unreachable";
  }

  return Response.json({
    status: "ok",
    app: "web",
    supabase: hasSupabasePublicConfig() ? "configured" : "local_mode",
    webFeatureFlags: getWebFeatureFlags(),
    ocrApi,
    ocrApiDetails,
    metrics: buildMetricsSnapshot(documents)
  });
}
