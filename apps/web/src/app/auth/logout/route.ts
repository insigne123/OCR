import { NextResponse } from "next/server";
import { createSupabaseServerAuthClient } from "@/lib/supabase/server-auth";

export async function POST(request: Request) {
  const supabase = await createSupabaseServerAuthClient();

  if (supabase) {
    await supabase.auth.signOut();
  }

  return NextResponse.redirect(new URL("/login?message=Signed%20out", request.url));
}
