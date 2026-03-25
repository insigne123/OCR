import { getTrialApiClients, isTrialApiAuthConfigured } from "@/lib/public-api-auth";

export async function GET() {
  return Response.json({
    status: "ok",
    service: "public-ocr-trial-api",
    authConfigured: isTrialApiAuthConfigured(),
    trialClientsConfigured: getTrialApiClients().length,
    defaults: {
      documentLimit: 50,
      processingMode: "sync",
      callbacksEnabled: false,
    },
  });
}
