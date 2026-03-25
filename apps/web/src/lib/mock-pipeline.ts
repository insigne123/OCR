import type { DocumentRecord, ReportSection, ValidationIssue } from "@ocr/shared";
import { createExtractedFieldsFromSections } from "./document-record";

function nowIso() {
  return new Date().toISOString();
}

function buildCertificateSections(): ReportSection[] {
  return [
    {
      id: "summary",
      title: "Resumen",
      variant: "pairs",
      rows: [
        ["Documento", "CERTIFICADO DE COTIZACIONES"],
        ["Emisor", "AFP ProVida S.A."],
        ["Titular", "CRISTINA ALEJANDRA ORTEGA RODRIGUEZ"],
        ["RUT", "16897320-9"],
        ["Cuenta de cotizacion", "1008-0760-0100199653"],
        ["Periodo de cotizacion", "2025-08"]
      ]
    },
    {
      id: "dates",
      title: "Fechas",
      variant: "table",
      columns: ["Periodo pago", "Fecha de pago"],
      rows: [
        ["2025-08", "-"],
        ["2025-07", "2025-08-12"],
        ["2025-06", "2025-06-09"],
        ["2025-05", "2025-06-13"],
        ["2025-04", "2025-05-13"]
      ]
    },
    {
      id: "amounts",
      title: "Montos",
      variant: "table",
      columns: ["Periodo pago", "Renta imponible", "Fondo de pensiones"],
      rows: [
        ["2025-08", "0", "0"],
        ["2025-07", "2,536,386", "253,639"],
        ["2025-06", "1,372,891", "137,289"],
        ["2025-05", "255,319", "25,532"],
        ["2025-04", "2,529,117", "252,912"]
      ]
    },
    {
      id: "identifiers",
      title: "Identificadores",
      variant: "pairs",
      rows: [
        ["RUT del afiliado", "16897320-9"],
        ["Cuenta de cotizacion", "1008-0760-0100199653"],
        ["Codigo de cotizacion", "PERIODO SIN INFORMACION"],
        ["Empleador", "BACK OFFICE SOUTH AMERICA SPA"],
        ["RUT Empleador", "77,012,071-3; 81,826,800-9"]
      ],
      note: "Empleadores reportados: BACK OFFICE SOUTH AMERICA SPA; CAJA LOS ANDES."
    },
    {
      id: "human-summary",
      title: "Resumen humano",
      variant: "text",
      body: "Se extrajeron datos del certificado, incluyendo titular, cuenta, periodos y montos. La salida es consistente en la mayor parte del documento, pero algunos campos requieren confirmacion manual para pasar a autoaceptacion."
    }
  ];
}

function buildIdentitySections(filename: string): ReportSection[] {
  return [
    {
      id: "summary",
      title: "Resumen",
      variant: "pairs",
      rows: [
        ["Documento", "DOCUMENTO DE IDENTIDAD"],
        ["Archivo", filename],
        ["Pais", "CL"],
        ["Titular", "NOMBRE POR CONFIRMAR"],
        ["Numero", "ID-CL-DEMO-001"],
        ["Estado", "LISTO PARA REVISION"]
      ]
    },
    {
      id: "dates",
      title: "Fechas",
      variant: "table",
      columns: ["Campo", "Valor"],
      rows: [
        ["Fecha de emision", "2020-02-18"],
        ["Fecha de vencimiento", "2030-02-18"]
      ]
    },
    {
      id: "identity",
      title: "Identidad",
      variant: "pairs",
      rows: [
        ["Nombre completo", "NOMBRE POR CONFIRMAR"],
        ["Numero de documento", "ID-CL-DEMO-001"],
        ["Nacionalidad", "CHILENA"],
        ["Sexo", "-"],
        ["MRZ", "NO DETECTADA"]
      ]
    },
    {
      id: "human-summary",
      title: "Resumen humano",
      variant: "text",
      body: "Se identifico un documento de identidad y se genero una salida estructurada inicial. La plantilla esta lista para reglas por pais y validacion cruzada frente/dorso en la siguiente iteracion."
    }
  ];
}

function buildUnsupportedSections(document: DocumentRecord): ReportSection[] {
  return [
    {
      id: "summary",
      title: "Resumen",
      variant: "pairs",
      rows: [
        ["Archivo", document.filename],
        ["Familia declarada", document.documentFamily],
        ["Pais objetivo", document.country || "XX"],
        ["Estado", "REQUIERE REVIEW / SOPORTE"],
      ]
    },
    {
      id: "human-summary",
      title: "Resumen humano",
      variant: "text",
      body: "La familia documental aun no tiene un extractor local confiable en el mock pipeline. El caso debe pasar a revision humana o al OCR API remoto."
    }
  ];
}

function buildCertificateIssues(): ValidationIssue[] {
  return [
    {
      id: "issue-low-confidence-rut",
      type: "LOW_CONFIDENCE",
      field: "RUT del afiliado",
      severity: "medium",
      message: "La interpretacion del RUT parece correcta, pero el formato podria requerir una fuente adicional para autoaprobar.",
      suggestedAction: "Comparar contra otra linea del documento o una fuente externa validada."
    },
    {
      id: "issue-missing-code",
      type: "MISSING_FIELD",
      field: "codigo_cotizacion",
      severity: "low",
      message: "Hay periodos sin codigo de cotizacion visible en la lectura OCR.",
      suggestedAction: "Determinar si el campo es obligatorio para este flujo antes de bloquear el caso."
    }
  ];
}

function buildIdentityIssues(): ValidationIssue[] {
  return [
    {
      id: "issue-identity-number",
      type: "FORMAT_REVIEW",
      field: "Numero de documento",
      severity: "medium",
      message: "El formato del identificador necesita validacion deterministica por pais y variante.",
      suggestedAction: "Aplicar validador CL y confirmar contra frente/dorso antes de aceptar."
    }
  ];
}

function buildUnsupportedIssues(): ValidationIssue[] {
  return [
    {
      id: "issue-unsupported-family",
      type: "UNSUPPORTED_DOCUMENT",
      field: "document_family",
      severity: "high",
      message: "La familia documental aun no tiene soporte estructurado en el pipeline local.",
      suggestedAction: "Procesar con OCR API remoto o mantener el documento en revision humana."
    }
  ];
}

export function buildProcessedMockDocument(document: DocumentRecord): DocumentRecord {
  const isIdentity = document.documentFamily === "identity";
  const isCertificate = document.documentFamily === "certificate";
  const isSupported = isIdentity || isCertificate;
  const reportSections = isIdentity ? buildIdentitySections(document.filename) : isCertificate ? buildCertificateSections() : buildUnsupportedSections(document);
  const issues = isIdentity ? buildIdentityIssues() : isCertificate ? buildCertificateIssues() : buildUnsupportedIssues();
  const globalConfidence = isIdentity ? 0.78 : isCertificate ? 0.85 : 0.32;
  const decision = isIdentity ? "human_review" : isCertificate ? "accept_with_warning" : "human_review";
  const status = isIdentity ? "review" : isCertificate ? "completed" : "review";

  return {
    ...document,
    status,
    decision,
    country: document.country || "XX",
    variant: isIdentity ? "identity-cl-front-text" : isCertificate ? "certificate-cl-previsional-text" : null,
    issuer: isIdentity ? "Registro Civil (demo)" : isCertificate ? "AFP ProVida S.A." : null,
    holderName: isIdentity ? "NOMBRE POR CONFIRMAR" : isCertificate ? "CRISTINA ALEJANDRA ORTEGA RODRIGUEZ" : null,
    pageCount: document.pageCount || 1,
    globalConfidence,
    reviewRequired: decision === "human_review" || decision === "accept_with_warning",
    updatedAt: nowIso(),
    processedAt: nowIso(),
    assumptions: isIdentity
      ? [
          "La fecha de emision y vencimiento fueron normalizadas al formato ISO.",
          "No se detecto MRZ, por lo que se mantuvo el documento en revision."
        ]
      : isCertificate
        ? [
          "Las fechas de pago se normalizaron a formato ISO.",
          "Los montos se conservaron como texto legible para evitar perdida semantica antes de la version numerica final.",
          "Los campos faltantes quedaron marcados como desconocidos y no fueron inferidos."
        ]
        : ["El mock pipeline solo soporta certificados e identidad; esta familia queda marcada para review."],
    issues,
    extractedFields: createExtractedFieldsFromSections(reportSections, issues),
    documentPages: [
      {
        id: `page-${document.id}-1`,
        pageNumber: 1,
        imagePath: null,
        width: 1600,
        height: 2200,
        orientation: 0,
        qualityScore: isSupported ? 0.82 : 0.35,
        blurScore: isSupported ? 0.12 : 0.32,
        glareScore: isSupported ? 0.08 : 0.24,
        cropRatio: 0.96,
        documentCoverage: 0.91,
        edgeConfidence: 0.84,
        skewAngle: 0,
        skewApplied: false,
        perspectiveApplied: false,
        captureConditions: isSupported ? ['clean'] : ['glare', 'low_quality'],
        rescueProfiles: isSupported ? [] : ["shadow_boost"],
        selectedOcrProfile: isSupported ? 'original' : 'shadow_boost',
        corners: [],
        hasEmbeddedText: true
      }
    ],
    reportSections,
    processingMetadata: {
      packId: isIdentity ? "identity-cl-front" : isCertificate ? "certificate-cl-previsional" : null,
      packVersion: isSupported ? "2026-03" : null,
      documentSide: isIdentity ? "front" : null,
      crossSideDetected: false,
      decisionProfile: "balanced",
      requestedVisualEngine: null,
      selectedVisualEngine: null,
      ensembleMode: null,
      classificationConfidence: isIdentity ? 0.86 : isCertificate ? 0.82 : 0.32,
      extractionSource: "mock-pipeline",
      processingEngine: "mock-pipeline",
      ocrRuns: [],
      adjudicationMode: null,
      adjudicatedFields: 0,
      adjudicationAbstentions: 0,
      processingTrace: []
    },
    humanSummary: isIdentity
      ? "Documento de identidad procesado con confidence moderada y listo para reglas mas estrictas por pais."
      : isCertificate
        ? "Certificado previsional procesado con datos estructurados, warnings controlados y reporte HTML generado."
        : "Documento derivado a revision porque la familia aun no tiene soporte estructurado en el mock pipeline.",
    reportHtml: null
  };
}
