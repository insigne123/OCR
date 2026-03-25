import { NextResponse } from "next/server";
import { createSupabaseServerAuthClient } from "@/lib/supabase/server-auth";

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get("code");
  const next = requestUrl.searchParams.get("next") || "/";
  const origin = requestUrl.origin;

  const supabase = await createSupabaseServerAuthClient();

  if (!supabase) {
    return NextResponse.redirect(new URL("/", origin));
  }

  if (code) {
    const result = await supabase.auth.exchangeCodeForSession(code);

    if (result.error) {
      return NextResponse.redirect(new URL(`/login?error=${encodeURIComponent(result.error.message)}`, origin));
    }
  }

  return NextResponse.redirect(new URL(next, origin));
}
