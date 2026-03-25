"use client";

import { AUTO_COUNTRY_CODE, documentFamilyOptions } from "@ocr/shared";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import styles from "./upload-form.module.css";

export function UploadForm() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFileName, setSelectedFileName] = useState("Selecciona un PDF o una imagen escaneada");

  async function handleSubmit(formData: FormData) {
    setPending(true);
    setError(null);

    const response = await fetch("/api/documents", {
      method: "POST",
      body: formData
    });

    const payload = (await response.json()) as { error?: string; document?: { id: string } };

    if (!response.ok || !payload.document) {
      setPending(false);
      setError(payload.error ?? "No se pudo registrar el documento.");
      return;
    }

    router.push(`/documents/${payload.document.id}`);
    router.refresh();
  }

  return (
    <form
      className={styles.form}
      onSubmit={async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        await handleSubmit(new FormData(event.currentTarget));
      }}
    >
      <div className={styles.field}>
        <label className={styles.fileCard} htmlFor="file">
          <span className={styles.fileBadge}>Documento fuente</span>
          <strong className={styles.fileTitle}>{selectedFileName}</strong>
          <span className={styles.fileMeta}>PDF, JPG, PNG, TIFF o HEIF. Mientras mejor orientado este el archivo, mejor sera la lectura.</span>
        </label>
        <input
          accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.heic,.heif"
          className={styles.fileInput}
          id="file"
          name="file"
          onChange={(event) => {
            const nextFile = event.currentTarget.files?.[0];
            setSelectedFileName(nextFile?.name ?? "Selecciona un PDF o una imagen escaneada");
          }}
          required
          type="file"
        />
      </div>

      <div className={styles.inlineFields}>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="documentFamily">
            Familia documental
          </label>
          <select className={styles.select} id="documentFamily" name="documentFamily" defaultValue="unclassified">
            {documentFamilyOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label className={styles.label} htmlFor="country">
            Pais objetivo
          </label>
          <input className={styles.input} id="country" maxLength={2} name="country" defaultValue={AUTO_COUNTRY_CODE} required />
        </div>
      </div>

      <button className={styles.button} disabled={pending} type="submit">
        {pending ? "Guardando documento..." : "Subir y abrir documento"}
      </button>

      <div className={styles.helperGrid}>
        <div className={styles.helperCard}>
          <span className={styles.helperLabel}>Storage</span>
          <strong className={styles.helperValue}>Local prototype</strong>
        </div>
        <div className={styles.helperCard}>
          <span className={styles.helperLabel}>Pipeline</span>
          <strong className={styles.helperValue}>Ready to process</strong>
        </div>
        <div className={styles.helperCard}>
          <span className={styles.helperLabel}>Destino</span>
          <strong className={styles.helperValue}>Workspace documental</strong>
        </div>
      </div>

      <p className={styles.hint}>Usa `XX` para autodeteccion de pais. En esta fase el archivo se guarda localmente en `apps/web/.data/uploads` y queda listo para procesar o reprocesar.</p>

      {error ? <p aria-live="polite" className={styles.error}>{error}</p> : null}
    </form>
  );
}
