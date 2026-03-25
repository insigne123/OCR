import { NextResponse } from "next/server";
import { createSupabaseServerAuthClient } from "@/lib/supabase/server-auth";

function buildRedirectBase(request: Request) {
  const fromEnv = process.env.NEXT_PUBLIC_SITE_URL;
  if (fromEnv) return fromEnv.replace(/\/$/, "");

  const origin = new URL(request.url).origin;
  return origin.replace(/\/$/, "");
}

export async function POST(request: Request) {
  const supabase = await createSupabaseServerAuthClient();

  if (!supabase) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  const formData = await request.formData();
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const mode = String(formData.get("mode") ?? "password");

  if (!email) {
    return NextResponse.redirect(new URL("/login?error=Email%20is%20required", request.url));
  }

  if (mode === "otp") {
    const next = "/";
    const callbackUrl = `${buildRedirectBase(request)}/auth/callback?next=${encodeURIComponent(next)}`;
    const result = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: callbackUrl
      }
    });

    if (result.error) {
      return NextResponse.redirect(new URL(`/login?error=${encodeURIComponent(result.error.message)}&email=${encodeURIComponent(email)}`, request.url));
    }

    return NextResponse.redirect(
      new URL(`/login?message=${encodeURIComponent("Magic link sent. Check your inbox.")}&email=${encodeURIComponent(email)}`, request.url)
    );
  }

  if (!password) {
    return NextResponse.redirect(
      new URL(`/login?error=${encodeURIComponent("Password is required in password mode")}&email=${encodeURIComponent(email)}`, request.url)
    );
  }

  const result = await supabase.auth.signInWithPassword({
    email,
    password
  });

  if (result.error) {
    return NextResponse.redirect(new URL(`/login?error=${encodeURIComponent(result.error.message)}&email=${encodeURIComponent(email)}`, request.url));
  }

  return NextResponse.redirect(new URL("/", request.url));
}
