import { getAuthContext } from "@/lib/auth";

export async function ensureRouteAccessJson() {
  const auth = await getAuthContext();

  if (!auth.configured) {
    return null;
  }

  if (!auth.user) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  return null;
}

export async function ensureRouteAccessInline() {
  const auth = await getAuthContext();

  if (!auth.configured) {
    return null;
  }

  if (!auth.user) {
    return new Response("Unauthorized", { status: 401 });
  }

  return null;
}
