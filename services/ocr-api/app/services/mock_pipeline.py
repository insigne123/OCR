from html import escape

from app.schemas import ProcessResponse, ReportSection, ValidationIssue


def _certificate_sections() -> list[ReportSection]:
    return [
        ReportSection(
            id="summary",
            title="Resumen",
            variant="pairs",
            rows=[
                ["Documento", "CERTIFICADO DE COTIZACIONES"],
                ["Emisor", "AFP ProVida S.A."],
                ["Titular", "CRISTINA ALEJANDRA ORTEGA RODRIGUEZ"],
                ["RUT", "16897320-9"],
                ["Cuenta de cotizacion", "1008-0760-0100199653"],
            ],
        ),
        ReportSection(
            id="dates",
            title="Fechas",
            variant="table",
            columns=["Periodo pago", "Fecha de pago"],
            rows=[
                ["2025-08", "-"],
                ["2025-07", "2025-08-12"],
                ["2025-06", "2025-06-09"],
            ],
        ),
        ReportSection(
            id="amounts",
            title="Montos",
            variant="table",
            columns=["Periodo pago", "Renta imponible", "Fondo de pensiones"],
            rows=[
                ["2025-08", "0", "0"],
                ["2025-07", "2,536,386", "253,639"],
                ["2025-06", "1,372,891", "137,289"],
            ],
        ),
    ]


def _identity_sections(filename: str) -> list[ReportSection]:
    return [
        ReportSection(
            id="summary",
            title="Resumen",
            variant="pairs",
            rows=[
                ["Documento", "DOCUMENTO DE IDENTIDAD"],
                ["Archivo", filename],
                ["Pais", "CL"],
                ["Titular", "NOMBRE POR CONFIRMAR"],
                ["Numero", "ID-CL-DEMO-001"],
            ],
        ),
        ReportSection(
            id="identity",
            title="Identidad",
            variant="pairs",
            rows=[
                ["Nombre completo", "NOMBRE POR CONFIRMAR"],
                ["Numero de documento", "ID-CL-DEMO-001"],
                ["Nacionalidad", "CHILENA"],
                ["MRZ", "NO DETECTADA"],
            ],
        ),
    ]


def _certificate_issues() -> list[ValidationIssue]:
    return [
        ValidationIssue(
            id="issue-low-confidence-rut",
            type="LOW_CONFIDENCE",
            field="RUT del afiliado",
            severity="medium",
            message="La lectura del RUT requiere confirmacion adicional antes de autoaceptar.",
            suggestedAction="Comparar contra otra linea del documento o fuente secundaria.",
        ),
        ValidationIssue(
            id="issue-missing-code",
            type="MISSING_FIELD",
            field="codigo_cotizacion",
            severity="low",
            message="Hay periodos sin codigo de cotizacion visible.",
            suggestedAction="Definir si el campo es obligatorio para este flujo.",
        ),
    ]


def _identity_issues() -> list[ValidationIssue]:
    return [
        ValidationIssue(
            id="issue-format-review",
            type="FORMAT_REVIEW",
            field="Numero de documento",
            severity="medium",
            message="El numero debe validarse con reglas por pais antes de autoaprobar.",
            suggestedAction="Aplicar reglas CL y validar frente/dorso.",
        )
    ]


def build_html(response: ProcessResponse, filename: str) -> str:
    tag_class = "ok" if response.decision == "auto_accept" else "blocked" if response.decision == "reject" else "partial"

    def render_section(section: ReportSection) -> str:
        if section.variant == "text":
            body = escape(section.body or "-")
            return f"<section><h2>{escape(section.title)}</h2><p class='notes'>{body}</p></section>"

        if section.variant == "pairs":
            rows = "".join(
                f"<tr><th scope='row'>{escape(row[0])}</th><td>{escape(row[1])}</td></tr>" for row in (section.rows or [])
            )
            note = f"<p class='notes'>{escape(section.note)}</p>" if section.note else ""
            return f"<section><h2>{escape(section.title)}</h2><table><tbody>{rows}</tbody></table>{note}</section>"

        header = "".join(f"<th scope='col'>{escape(column)}</th>" for column in (section.columns or []))
        body = "".join(
            "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>" for row in (section.rows or [])
        )
        note = f"<p class='notes'>{escape(section.note)}</p>" if section.note else ""
        return f"<section><h2>{escape(section.title)}</h2><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>{note}</section>"

    sections_html = "".join(render_section(section) for section in response.report_sections)
    issues_rows = "".join(
        (
            f"<tr><td>{escape(issue.type)}</td><td>{escape(issue.field)}</td>"
            f"<td>{escape(issue.message)}</td><td>{escape(issue.suggestedAction)}</td></tr>"
        )
        for issue in response.issues
    )
    issues_html = (
        "<section><h2>Issues</h2><table><thead><tr><th scope='col'>Tipo</th><th scope='col'>Campo</th>"
        "<th scope='col'>Mensaje</th><th scope='col'>Accion sugerida</th></tr></thead><tbody>"
        f"{issues_rows}</tbody></table></section>"
        if response.issues
        else ""
    )
    assumptions_html = (
        "<section><h2>Asunciones</h2><ul>"
        + "".join(f"<li>{escape(item)}</li>" for item in response.assumptions)
        + "</ul></section>"
        if response.assumptions
        else ""
    )

    return f"""<!doctype html>
<html lang='es'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Reporte OCR - {escape(filename)}</title>
  <style>
    :root {{ --header-bg:#111827; --header-fg:#f9fafb; --muted:#6b7280; --border:#e5e7eb; --table-stripe:#f9fafb; --text:#111827; }}
    html,body {{ margin:0; padding:0; background:#fff; color:var(--text); font-family:ui-sans-serif,system-ui,sans-serif; }}
    .wrap {{ max-width:1100px; margin:0 auto; padding:24px; }}
    header {{ display:flex; align-items:flex-start; justify-content:space-between; gap:12px; padding-bottom:8px; border-bottom:1px solid var(--border); }}
    h1 {{ font-size:1.6rem; margin:0; }}
    .tag {{ display:inline-block; padding:.25em .6em; border-radius:.5rem; font-weight:700; font-size:.8rem; }}
    .tag.ok {{ background:#10b981; color:white; }}
    .tag.partial {{ background:#f59e0b; color:white; }}
    .tag.blocked {{ background:#ef4444; color:white; }}
    .conf {{ color:var(--muted); font-size:.95rem; }}
    section {{ margin-top:28px; }}
    section h2 {{ font-size:1.25rem; margin:0 0 8px; }}
    table {{ width:100%; border-collapse:collapse; margin-top:6px; }}
    table thead th {{ background:var(--header-bg); color:var(--header-fg); padding:8px 10px; text-align:left; font-weight:700; }}
    table tbody td {{ padding:8px 10px; border-top:1px solid var(--border); vertical-align:top; }}
    table tbody tr:nth-child(odd) {{ background:var(--table-stripe); }}
    th[scope='row'] {{ white-space:nowrap; color:#374151; }}
    ul {{ margin:0 0 0 1.25rem; padding:0; }}
    .notes {{ font-size:.95rem; color:var(--muted); }}
  </style>
</head>
<body>
  <main class='wrap'>
    <header>
      <div>
        <h1>Reporte OCR - {escape(filename)}</h1>
        <div class='conf'>Confianza global: {response.global_confidence:.2f} · Decision: {escape(response.decision)}</div>
      </div>
      <span class='tag {tag_class}'>{escape(response.decision)}</span>
    </header>
    {sections_html}
    {issues_html}
    {assumptions_html}
    <section><h2>Resumen humano</h2><p class='notes'>{escape(response.human_summary or '-')}</p></section>
  </main>
</body>
</html>"""


def run_mock_pipeline(filename: str, document_family: str, country: str) -> ProcessResponse:
    is_identity = document_family == "identity"
    report_sections = _identity_sections(filename) if is_identity else _certificate_sections()
    issues = _identity_issues() if is_identity else _certificate_issues()

    response = ProcessResponse(
        document_family=document_family,
        country=country,
        variant="dni-front" if is_identity else "certificado-cotizaciones",
        issuer="Registro Civil (demo)" if is_identity else "AFP ProVida S.A.",
        holder_name="NOMBRE POR CONFIRMAR" if is_identity else "CRISTINA ALEJANDRA ORTEGA RODRIGUEZ",
        page_count=1,
        global_confidence=0.78 if is_identity else 0.85,
        decision="human_review" if is_identity else "accept_with_warning",
        review_required=True,
        assumptions=[
            "Las fechas se normalizaron a formato ISO.",
            "Los valores dudosos se mantuvieron con warning en lugar de inferencia agresiva.",
        ],
        issues=issues,
        report_sections=report_sections,
        human_summary=(
            "Documento de identidad procesado con confidence moderada y listo para reglas por pais."
            if is_identity
            else "Certificado previsional procesado con salida estructurada y warnings controlados."
        ),
        report_html="",
    )
    response.report_html = build_html(response, filename)
    return response
