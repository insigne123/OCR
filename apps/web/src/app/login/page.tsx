import { redirect } from "next/navigation";
import { LoginForm } from "@/components/login-form";
import { getAuthContext } from "@/lib/auth";
import styles from "./page.module.css";

type LoginPageProps = {
  searchParams: Promise<{
    message?: string;
    error?: string;
    email?: string;
  }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const auth = await getAuthContext();

  if (!auth.configured) {
    redirect("/");
  }

  if (auth.isAuthenticated) {
    redirect("/");
  }

  return (
    <main className={styles.page}>
      <section className={styles.card}>
        <div className={styles.brand}>
          <div className={styles.mark} aria-hidden="true" />
          <div>
            <span className={styles.eyebrow}>Archiva systems</span>
            <h1 className={styles.title}>Sign in to OCR Control</h1>
          </div>
        </div>

        <p className={styles.description}>
          Entra con password o usa magic link para acceder al workspace documental protegido por Supabase Auth.
        </p>

        {params.message ? <p className={styles.message}>{params.message}</p> : null}
        {params.error ? <p className={styles.error}>{params.error}</p> : null}

        <LoginForm defaultEmail={params.email} />
      </section>
    </main>
  );
}
