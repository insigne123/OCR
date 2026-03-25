import { ensurePublicApiClient } from "@/lib/public-api-auth";
import { listWebhookLogs } from "@/lib/public-api-store";
import { deliverQueuedPublicWebhooks } from "@/lib/public-api-status";

export async function GET(request: Request) {
  const client = ensurePublicApiClient(request);
  if (client instanceof Response) return client;

  const { searchParams } = new URL(request.url);
  const limit = Number.parseInt(searchParams.get("limit") ?? "100", 10);
  const logs = await listWebhookLogs({
    apiClientId: client.id,
    status: (searchParams.get("status") as never) ?? undefined,
    eventType: searchParams.get("event_type") ?? undefined,
    limit: Number.isFinite(limit) ? Math.max(1, Math.min(limit, 200)) : 100,
  });
  return Response.json({ items: logs });
}

export async function POST(request: Request) {
  const client = ensurePublicApiClient(request);
  if (client instanceof Response) return client;

  const body = (await request.json().catch(() => ({}))) as { action?: string; limit?: number };
  if (body.action !== "drain") {
    return Response.json({ error: "Unsupported action." }, { status: 400 });
  }
  const deliveries = await deliverQueuedPublicWebhooks({ apiClientId: client.id, limit: Math.max(1, Math.min(body.limit ?? 10, 50)) });
  return Response.json({ deliveries });
}
