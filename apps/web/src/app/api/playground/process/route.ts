import { ensureRouteAccessJson } from "@/lib/route-auth";
import { getOcrApiUrl, getOptionalOcrApiKey } from "@/lib/ocr-config";

export async function POST(request: Request) {
  const unauthorized = await ensureRouteAccessJson();
  if (unauthorized) return unauthorized;

  const apiUrl = getOcrApiUrl();
  const apiKey = getOptionalOcrApiKey();

  const formData = await request.formData();
  let response: Response;

  try {
    response = await fetch(`${apiUrl}/v1/process`, {
      method: "POST",
      body: formData,
      headers: apiKey
        ? {
            "x-api-key": apiKey
          }
        : undefined,
      cache: "no-store"
    });
  } catch {
    return Response.json(
      {
        error: `Could not reach OCR API at ${apiUrl}. Start the OCR service with npm run dev:ocr-api.`
      },
      { status: 503 }
    );
  }

  const payload = await response.text();

  return new Response(payload, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json; charset=utf-8"
    }
  });
}
