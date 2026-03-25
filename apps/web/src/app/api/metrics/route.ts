import { getAllDocuments } from "@/lib/document-store";
import { ensureRouteAccessInline } from "@/lib/route-auth";
import { buildMetricsSnapshot, buildPrometheusMetrics } from "@/lib/ops-metrics";

export async function GET(request: Request) {
  const unauthorized = await ensureRouteAccessInline();
  if (unauthorized) return unauthorized;

  const { searchParams } = new URL(request.url);
  const format = searchParams.get("format") ?? "prometheus";
  const documents = await getAllDocuments();

  if (format === "json") {
    return Response.json(buildMetricsSnapshot(documents));
  }

  return new Response(buildPrometheusMetrics(documents), {
    headers: {
      "content-type": "text/plain; version=0.0.4; charset=utf-8"
    }
  });
}
