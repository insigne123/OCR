import { ensurePublicApiClient } from "@/lib/public-api-auth";
import { getWebhookLogById } from "@/lib/public-api-store";
import { retryPublicWebhookDelivery } from "@/lib/public-api-status";

type RouteContext = {
  params: Promise<{ deliveryId: string }>;
};

export async function POST(request: Request, { params }: RouteContext) {
  const client = ensurePublicApiClient(request);
  if (client instanceof Response) return client;

  const { deliveryId } = await params;
  const log = await getWebhookLogById(deliveryId);
  if (!log || log.apiClientId !== client.id) {
    return Response.json({ error: "Webhook log not found." }, { status: 404 });
  }

  const delivery = await retryPublicWebhookDelivery(deliveryId);
  return Response.json({ delivery });
}
