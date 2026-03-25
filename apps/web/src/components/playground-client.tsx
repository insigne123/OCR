"use client";

import { useState } from "react";
import styles from "./playground-client.module.css";

const INITIAL_JSON = `{
  "hint": "Sube un documento o imagen para ver aqui el JSON canonico del endpoint OCR."
}`;

export function PlaygroundClient() {
  const [pending, setPending] = useState(false);
  const [jsonOutput, setJsonOutput] = useState(INITIAL_JSON);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(formData: FormData) {
    setPending(true);
    setError(null);
    setJsonOutput(INITIAL_JSON);

    const response = await fetch("/api/playground/process", {
      method: "POST",
      body: formData
    });

    const text = await response.text();

    if (!response.ok) {
      setPending(false);
      try {
        const parsed = JSON.parse(text) as { error?: string };
        setError(parsed.error ?? text ?? "No se pudo procesar el documento.");
      } catch {
        setError(text || "No se pudo procesar el documento.");
      }
      return;
    }

    try {
      const parsed = JSON.parse(text) as unknown;
      setJsonOutput(JSON.stringify(parsed, null, 2));
    } catch {
      setJsonOutput(text);
    }

    setPending(false);
  }

  return (
    <div className={styles.layout}>
      <section className={styles.panel}>
        <div className={styles.header}>
          <div>
            <span className={styles.eyebrow}>Input</span>
            <h2 className={styles.title}>Process document</h2>
          </div>
          <span className={styles.meta}>API-first test</span>
        </div>

        <form
          className={styles.form}
          onSubmit={async (event) => {
            event.preventDefault();
            await handleSubmit(new FormData(event.currentTarget));
          }}
        >
          <label className={styles.field}>
            <span className={styles.label}>Document or image</span>
            <input accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.heic,.heif" className={styles.input} name="file" required type="file" />
          </label>

          <div className={styles.inlineFields}>
            <label className={styles.field}>
              <span className={styles.label}>Document family</span>
              <select className={styles.input} defaultValue="auto" name="document_family">
                <option value="auto">auto</option>
                <option value="certificate">certificate</option>
                <option value="identity">identity</option>
                <option value="passport">passport</option>
                <option value="driver_license">driver_license</option>
                <option value="invoice">invoice</option>
                <option value="unclassified">unclassified</option>
              </select>
            </label>

            <label className={styles.field}>
              <span className={styles.label}>Country</span>
              <input className={styles.input} defaultValue="AUTO" maxLength={5} name="country" required />
            </label>
          </div>

          <label className={styles.field}>
            <span className={styles.label}>Response mode</span>
            <select className={styles.input} defaultValue="json" name="response_mode">
              <option value="json">json</option>
              <option value="full">full</option>
            </select>
          </label>

          <button className={styles.submit} disabled={pending} type="submit">
            {pending ? "Processing..." : "Upload and get JSON"}
          </button>

          {error ? <p className={styles.error}>{error}</p> : null}
        </form>
      </section>

      <section className={styles.panel}>
        <div className={styles.header}>
          <div>
            <span className={styles.eyebrow}>Output</span>
            <h2 className={styles.title}>JSON response</h2>
          </div>
          <button
            className={styles.copyButton}
            onClick={async () => {
              await navigator.clipboard.writeText(jsonOutput);
            }}
            type="button"
          >
            Copy JSON
          </button>
        </div>

        <pre className={styles.code}>{jsonOutput}</pre>
      </section>
    </div>
  );
}
