import { documentDecisionLabels, type DocumentRecord, type ReportSection } from "@ocr/shared";

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderSection(section: ReportSection) {
  if (section.variant === "text") {
    return `
      <section class="section">
        <h2>${escapeHtml(section.title)}</h2>
        <p class="notes">${escapeHtml(section.body ?? "-")}</p>
      </section>
    `;
  }

  if (section.variant === "pairs") {
    const rows = (section.rows ?? [])
      .map(
        (row) => `
          <tr>
            <th scope="row">${escapeHtml(row[0] ?? "-")}</th>
            <td>${escapeHtml(row[1] ?? "-")}</td>
          </tr>
        `
      )
      .join("");

    return `
      <section class="section">
        <h2>${escapeHtml(section.title)}</h2>
        <table>
          <tbody>${rows}</tbody>
        </table>
        ${section.note ? `<p class="notes">${escapeHtml(section.note)}</p>` : ""}
      </section>
    `;
  }

  const header = (section.columns ?? [])
    .map((column) => `<th scope="col">${escapeHtml(column)}</th>`)
    .join("");

  const body = (section.rows ?? [])
    .map(
      (row) => `
        <tr>
          ${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}
        </tr>
      `
    )
    .join("");

  return `
    <section class="section">
      <h2>${escapeHtml(section.title)}</h2>
      <table>
        <thead>
          <tr>${header}</tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
      ${section.note ? `<p class="notes">${escapeHtml(section.note)}</p>` : ""}
    </section>
  `;
}

export function buildReportHtml(document: DocumentRecord) {
  const decisionLabel = documentDecisionLabels[document.decision];
  const tagClass =
    document.decision === "auto_accept"
      ? "ok"
      : document.decision === "reject"
        ? "blocked"
        : "partial";

  const sections = document.reportSections.map(renderSection).join("");
  const issues = document.issues.length
    ? `
      <section class="section">
        <h2>Issues</h2>
        <table>
          <thead>
            <tr>
              <th scope="col">Tipo</th>
              <th scope="col">Campo</th>
              <th scope="col">Mensaje</th>
              <th scope="col">Accion sugerida</th>
            </tr>
          </thead>
          <tbody>
            ${document.issues
              .map(
                (issue) => `
                  <tr>
                    <td>${escapeHtml(issue.type)}</td>
                    <td>${escapeHtml(issue.field)}</td>
                    <td>${escapeHtml(issue.message)}</td>
                    <td>${escapeHtml(issue.suggestedAction)}</td>
                  </tr>
                `
              )
              .join("")}
          </tbody>
        </table>
      </section>
    `
    : "";

  const assumptions = document.assumptions.length
    ? `
      <section class="section">
        <h2>Asunciones</h2>
        <ul>
          ${document.assumptions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        </ul>
      </section>
    `
    : "";

  return `<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reporte OCR - ${escapeHtml(document.filename)}</title>
  <style>
    :root {
      --header-bg: #111827;
      --header-fg: #f9fafb;
      --muted: #6b7280;
      --border: #e5e7eb;
      --table-stripe: #f9fafb;
      --text: #111827;
      --bg: #ffffff;
    }
    html, body { margin: 0; padding: 0; background: #fff; color: var(--text); font-family: ui-sans-serif, system-ui, sans-serif; }
    .wrap { max-width: 1100px; margin: 0 auto; padding: 24px; }
    header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
    h1 { font-size: 1.6rem; margin: 0; }
    .tag { display: inline-block; padding: .25em .6em; border-radius: .5rem; font-weight: 700; font-size: .8rem; }
    .tag.ok { background: #10b981; color: white; }
    .tag.partial { background: #f59e0b; color: white; }
    .tag.blocked { background: #ef4444; color: white; }
    .conf { color: var(--muted); font-size: .95rem; }
    section { margin-top: 28px; }
    section h2 { font-size: 1.25rem; margin: 0 0 8px; }
    table { width: 100%; border-collapse: collapse; margin-top: 6px; }
    table thead th { background: var(--header-bg); color: var(--header-fg); padding: 8px 10px; text-align: left; font-weight: 700; }
    table tbody td { padding: 8px 10px; border-top: 1px solid var(--border); vertical-align: top; }
    table tbody tr:nth-child(odd) { background: var(--table-stripe); }
    th[scope="row"] { white-space: nowrap; color: #374151; }
    ul { margin: 0 0 0 1.25rem; padding: 0; }
    .notes { font-size: .95rem; color: var(--muted); }
    .section + .section { border-top: 1px solid var(--border); padding-top: 16px; }
  </style>
</head>
<body>
  <main class="wrap" aria-label="Reporte OCR">
    <header>
      <div>
        <h1>Reporte OCR - ${escapeHtml(document.filename)}</h1>
        <div class="conf">Confianza global: ${document.globalConfidence?.toFixed(2) ?? "-"} · Decision: ${escapeHtml(decisionLabel)}</div>
      </div>
      <span class="tag ${tagClass}">${escapeHtml(decisionLabel)}</span>
    </header>
    ${sections}
    ${issues}
    ${assumptions}
    ${document.humanSummary ? `<section class="section"><h2>Resumen humano</h2><p class="notes">${escapeHtml(document.humanSummary)}</p></section>` : ""}
  </main>
</body>
</html>`;
}
