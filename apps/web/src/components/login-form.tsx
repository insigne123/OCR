"use client";

import { useState } from "react";
import styles from "./login-form.module.css";

type LoginFormProps = {
  defaultEmail?: string;
};

export function LoginForm({ defaultEmail = "" }: LoginFormProps) {
  const [mode, setMode] = useState<"password" | "otp">("password");

  return (
    <form action="/auth/login" className={styles.form} method="post">
      <div className={styles.modeRow}>
        <button
          className={mode === "password" ? `${styles.modeButton} ${styles.modeButtonActive}` : styles.modeButton}
          onClick={() => setMode("password")}
          type="button"
        >
          Password
        </button>
        <button
          className={mode === "otp" ? `${styles.modeButton} ${styles.modeButtonActive}` : styles.modeButton}
          onClick={() => setMode("otp")}
          type="button"
        >
          Magic Link
        </button>
      </div>

      <input name="mode" type="hidden" value={mode} />

      <label className={styles.field}>
        <span className={styles.label}>Email</span>
        <input autoComplete="email" className={styles.input} defaultValue={defaultEmail} name="email" placeholder="you@company.com" required type="email" />
      </label>

      <label className={styles.field}>
        <span className={styles.label}>Password</span>
        <input autoComplete="current-password" className={styles.input} name="password" placeholder={mode === "password" ? "Enter your password" : "Optional in magic link mode"} type="password" />
      </label>

      <button className={styles.submit} type="submit">
        {mode === "password" ? "Sign in" : "Send magic link"}
      </button>
    </form>
  );
}
