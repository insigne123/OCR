from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.schemas import NormalizedDocument, ReportSection
from app.services.field_value_utils import canonicalize_chile_run, normalize_date_value
from app.services.processing_pipeline import _should_try_visual_support_for_certificate, run_processing_pipeline


class CertificateAfpSupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        pdf_path = repo_root / "test-data" / "AFP.pdf"
        cls.response = run_processing_pipeline(
            pdf_path.read_bytes(),
            pdf_path.name,
            "application/pdf",
            "auto",
            "AUTO",
            "json",
            ocr_visual_engine="auto",
            decision_profile="balanced",
            structured_mode_override="auto",
            ocr_ensemble_mode="always",
            ocr_ensemble_engines="rapidocr,google-documentai,azure-document-intelligence",
            field_adjudication_mode="auto",
        )

    def test_supports_long_spanish_dates_and_comma_runs(self) -> None:
        self.assertEqual(normalize_date_value("14 de septiembre de 2025"), "2025-09-14")
        self.assertEqual(canonicalize_chile_run("16,897,320-9"), "16.897.320-9")

    def test_afp_pdf_extracts_header_fields(self) -> None:
        values = {field.label: field.value for field in self.response.fields}

        self.assertEqual(self.response.document_family, "certificate")
        self.assertEqual(self.response.country, "CL")
        self.assertEqual(values.get("Titular"), self.response.holder_name)
        self.assertNotEqual(values.get("Titular"), "Certificado de Cotizaciones")
        self.assertNotEqual(values.get("RUT"), "NO DETECTADO")
        self.assertNotEqual(values.get("Numero de certificado"), "NO DETECTADO")
        self.assertNotEqual(values.get("Fecha de emision"), "NO DETECTADA")
        self.assertNotEqual(values.get("Cuenta"), "NO DETECTADA")

    def test_afp_pdf_extracts_contribution_rows_without_missing_rut_issue(self) -> None:
        movement_section = next(section for section in self.response.report_sections if section.id == "movements")

        self.assertGreaterEqual(len(movement_section.rows or []), 12)
        self.assertTrue(any(row[5] != "-" for row in movement_section.rows or []))
        self.assertFalse(any(issue.id == "issue-missing-rut" for issue in self.response.issues))
        self.assertFalse(any(issue.id == "rule-certificate-missing-rut-cl" for issue in self.response.issues))

    def test_afp_pdf_keeps_embedded_text_route_when_evidence_is_strong(self) -> None:
        processing = self.response.processing
        self.assertIsNotNone(processing)
        if processing is None:
            return
        self.assertEqual(processing.extraction_source, "pdf-embedded-text")

    def test_weak_afp_certificate_would_trigger_visual_support(self) -> None:
        weak_certificate = NormalizedDocument(
            document_family="certificate",
            country="CL",
            variant="certificate-cl-previsional-text",
            issuer="AFP ProVida S.A.",
            holder_name="NOMBRE POR CONFIRMAR",
            global_confidence=0.71,
            assumptions=[],
            issues=[],
            report_sections=[
                ReportSection(
                    id="summary",
                    title="Resumen",
                    variant="pairs",
                    rows=[
                        ["Titular", "NOMBRE POR CONFIRMAR"],
                        ["RUT", "NO DETECTADO"],
                        ["Numero de certificado", "NO DETECTADO"],
                        ["Cuenta", "1008-0760-0100199653"],
                    ],
                ),
                ReportSection(
                    id="movements",
                    title="Filas tabulares detectadas",
                    variant="table",
                    columns=["Periodo", "Renta imponible", "Fondo pensiones", "Codigo", "Empleador", "RUT empleador", "Fecha pago", "Detalle"],
                    rows=[["JUL-2025", "-", "-", "-", "-", "-", "-", "Sin filas tabulares detectadas"]],
                ),
            ],
            human_summary=None,
        )

        self.assertTrue(_should_try_visual_support_for_certificate(weak_certificate, "pdf-embedded-text", "certificate-cl-previsional"))


if __name__ == "__main__":
    unittest.main()
