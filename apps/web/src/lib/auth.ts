import { getOptionalAuthenticatedUser } from "@/lib/supabase/server-auth";
import { hasSupabasePublicConfig } from "@/lib/supabase/config";
import { redirect } from "next/navigation";

export async function getAuthContext() {
  const configured = hasSupabasePublicConfig();
  const user = configured ? await getOptionalAuthenticatedUser() : null;

  return {
    configured,
    user,
    isAuthenticated: Boolean(user)
  };
}

export async function requireAuthenticatedUser() {
  const { configured, user } = await getAuthContext();

  if (!configured) {
    return null;
  }

  if (!user) {
    throw new Error("UNAUTHORIZED");
  }

  return user;
}

export async function requireAuthenticatedAppUser() {
  const { configured, user } = await getAuthContext();

  if (configured && !user) {
    redirect("/login");
  }

  return user;
}
