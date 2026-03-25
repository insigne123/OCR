"use client";

import type { DocumentStatus } from "@ocr/shared";
import { useRouter } from "next/navigation";
import { useState } from "react";
import styles from "./process-document-button.module.css";

type ProcessDocumentButtonProps = {
  documentId: string;
  status: DocumentStatus;
};

export function ProcessDocumentButton({ documentId, status }: ProcessDocumentButtonProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setPending(true);
    setError(null);

    const response = await fetch(`/api/documents/${documentId}/process${status === "completed" ? "?force=1" : ""}`, {
      method: "POST"
    });

    const payload = (await response.json()) as { error?: string };

    if (!response.ok) {
      setPending(false);
      setError(payload.error ?? "No se pudo ejecutar el pipeline.");
      return;
    }

    setPending(false);
    router.refresh();
  }

  const isBusy = pending || status === "processing";
  const label = isBusy ? "Queued / running..." : status === "completed" ? "Queue reprocessing" : "Queue document";
  const hint =
    status === "processing"
      ? "El documento ya esta en cola o en ejecucion. Usa Jobs para correr el worker o reintentar fallos segun corresponda."
      : "Este boton agrega el documento a la cola. Luego puedes ejecutar un worker cycle desde la vista Jobs.";

  return (
    <div className={styles.wrapper}>
      <button className={styles.button} disabled={isBusy} onClick={handleClick} type="button">
        {label}
      </button>
      <p className={styles.hint}>{hint}</p>
      {error ? <p aria-live="polite" className={styles.error}>{error}</p> : null}
    </div>
  );
}
