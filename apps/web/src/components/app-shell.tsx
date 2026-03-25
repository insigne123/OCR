import Link from "next/link";
import type { ReactNode } from "react";
import { getAuthContext } from "@/lib/auth";
import styles from "./app-shell.module.css";

type AppSection = "overview" | "documents" | "playground" | "jobs" | "review" | "reports";

type AppShellProps = {
  activeSection: AppSection;
  eyebrow: string;
  title: string;
  subtitle: string;
  toolbar?: ReactNode;
  sidebarFooter?: ReactNode;
  children: ReactNode;
};

const navigation = [
  {
    key: "overview",
    label: "Overview",
    href: "/",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2.5" y="2.5" width="6" height="6" rx="1.5" />
        <rect x="11.5" y="2.5" width="6" height="6" rx="1.5" />
        <rect x="2.5" y="11.5" width="6" height="6" rx="1.5" />
        <rect x="11.5" y="11.5" width="6" height="6" rx="1.5" />
      </svg>
    )
  },
  {
    key: "documents",
    label: "Documents",
    href: "/#documents",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M11.5 2.5H5.5a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V7.5L11.5 2.5Z" />
        <polyline points="11.5,2.5 11.5,7.5 16.5,7.5" />
        <line x1="6.5" y1="11" x2="13.5" y2="11" />
        <line x1="6.5" y1="14" x2="11" y2="14" />
      </svg>
    )
  },
  {
    key: "playground",
    label: "Playground",
    href: "/playground",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M6 3.5h8" />
        <path d="M5.5 6.5h9" />
        <path d="M7.5 9.5h5" />
        <path d="M10 12l5.5 4.5H4.5L10 12Z" />
      </svg>
    )
  },
  {
    key: "jobs",
    label: "Jobs",
    href: "/jobs",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M6 4h8" />
        <path d="M6 10h8" />
        <path d="M6 16h8" />
        <circle cx="4" cy="4" r="1" fill="currentColor" stroke="none" />
        <circle cx="4" cy="10" r="1" fill="currentColor" stroke="none" />
        <circle cx="4" cy="16" r="1" fill="currentColor" stroke="none" />
      </svg>
    )
  },
  {
    key: "review",
    label: "Review Queue",
    href: "/review",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="9" cy="9" r="5.5" />
        <line x1="13" y1="13" x2="17" y2="17" />
      </svg>
    )
  },
  {
    key: "reports",
    label: "Reports",
    href: "/reports",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <line x1="5" y1="16" x2="5" y2="9" />
        <line x1="10" y1="16" x2="10" y2="4" />
        <line x1="15" y1="16" x2="15" y2="11" />
      </svg>
    )
  }
] as const;

export async function AppShell({ activeSection, eyebrow, title, subtitle, toolbar, sidebarFooter, children }: AppShellProps) {
  const auth = await getAuthContext();

  return (
    <main className={styles.page}>
      <div className={styles.frame}>
        <aside className={styles.sidebar}>
          <div className={styles.brandBlock}>
            <div className={styles.brandMark} aria-hidden="true">
              <span className={styles.brandOrb} />
            </div>
            <div className={styles.brandCopy}>
              <span className={styles.brandEyebrow}>Archiva systems</span>
              <strong className={styles.brandTitle}>OCR Control</strong>
            </div>
          </div>

          <nav className={styles.nav} aria-label="Principal">
            {navigation.map((item) => (
              <Link
                className={item.key === activeSection ? `${styles.navItem} ${styles.navItemActive}` : styles.navItem}
                href={item.href}
                key={item.key}
              >
                <span className={styles.navIcon}>{item.icon}</span>
                <span className={styles.navLabel}>{item.label}</span>
              </Link>
            ))}
          </nav>

          <section className={styles.systemCard}>
            <span className={styles.systemEyebrow}>Workspace</span>
            <strong className={styles.systemTitle}>Professional app shell</strong>
            <p className={styles.systemText}>
              Interfaz enfocada en operacion documental, lectura, validacion y reportes; menos landing, mas herramienta.
            </p>
          </section>

          <section className={styles.systemCard}>
            <span className={styles.systemEyebrow}>Access</span>
            <strong className={styles.systemTitle}>{auth.configured ? (auth.user?.email ?? "Protected workspace") : "Local development mode"}</strong>
            <p className={styles.systemText}>
              {auth.configured
                ? auth.user
                  ? "Sesion activa mediante Supabase Auth."
                  : "La autenticacion esta habilitada y las rutas estan protegidas."
                : "Supabase Auth no esta configurado; la app funciona en modo local sin login."}
            </p>
            {auth.configured && auth.user ? (
              <form action="/auth/logout" className={styles.authForm} method="post">
                <button className={styles.authButton} type="submit">
                  Sign out
                </button>
              </form>
            ) : null}
          </section>

          {sidebarFooter ? <div className={styles.sidebarFooter}>{sidebarFooter}</div> : null}
        </aside>

        <section className={styles.main}>
          <header className={styles.header}>
            <div className={styles.headerCopy}>
              <span className={styles.headerEyebrow}>{eyebrow}</span>
              <h1 className={styles.headerTitle}>{title}</h1>
              <p className={styles.headerSubtitle}>{subtitle}</p>
            </div>
            {toolbar ? <div className={styles.toolbar}>{toolbar}</div> : null}
          </header>

          <div className={styles.content}>{children}</div>
        </section>
      </div>
    </main>
  );
}
