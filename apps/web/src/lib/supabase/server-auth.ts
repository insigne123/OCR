import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";
import { getSupabasePublicConfig, hasSupabasePublicConfig } from "./config";

export async function createSupabaseServerAuthClient() {
  if (!hasSupabasePublicConfig()) {
    return null;
  }

  const { url, anonKey } = getSupabasePublicConfig();
  const cookieStore = await cookies();

  return createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet: Array<{ name: string; value: string; options?: CookieOptions }>) {
        cookiesToSet.forEach(({ name, value, options }) => {
          cookieStore.set(name, value, options);
        });
      }
    }
  });
}

export async function getOptionalAuthenticatedUser() {
  const supabase = await createSupabaseServerAuthClient();

  if (!supabase) {
    return null;
  }

  const result = await supabase.auth.getUser();
  return result.data.user ?? null;
}
