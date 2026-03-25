import { ensurePublicApiClient } from "@/lib/public-api-auth";
import { buildUsageAnalytics, filterUsageLedger } from "@/lib/public-api-analytics";
import { listUsageLedgerRecords } from "@/lib/public-api-store";

export async function GET(request: Request) {
  const client = ensurePublicApiClient(request);
  if (client instanceof Response) return client;

  const { searchParams } = new URL(request.url);
  const records = await listUsageLedgerRecords({ apiClientId: client.id, limit: 5000 });
  const filtered = filterUsageLedger(records, {
    from: searchParams.get("from"),
    to: searchParams.get("to"),
  });

  return Response.json(buildUsageAnalytics(filtered));
}
