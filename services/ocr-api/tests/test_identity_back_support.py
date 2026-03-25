from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.cross_side_consistency import build_cross_side_consistency_signal
from app.services.document_classifier import classify_document
from app.services.field_value_utils import parse_identity_card_mrz
from app.services.heuristic_normalizer import normalize_identity_text
from app.services.page_analysis import PageAnalysisResult, PageClassificationResult
from app.services.processing_pipeline import _build_identity_cross_side_normalized


def _page_classification(page_number: int, text: str):
    return PageClassificationResult(page_number=page_number, classification=classify_document(text, "auto", "AUTO"))


CHILE_ID_FRONT_TEXT = """FECHADEVENCIMIENTO
13OCT2035
NUMERO DOCUMENTO
B64.872.150
REPUBLICA DE CHILE
SERVICIO DE REGISTRO CIVIL E IDENTIFICACION
SEXO
M
NICOLAS FAELLES
13OCT2005
FECHADENACIMIENTO
02DIC2025
YARUR GONGORA
NOMBRE TITULAR
FECHADEEMISION
CHILENA
NACIONALIDAD
APELLIDOS
NOMBRES
21.952.550-8
CEDULA DE IDENTIDAD"""


CHILE_ID_BACK_TEXT = """NACICAN
5CC0940B
438584
Nacio en:
PROVIDENCIA
INCHLB648721500S13<<<<<<<<<<
0510132M3510133CHL21952550<8<9
YARURKGONGORAK<NICOLASKFAELLES"""


class IdentityBackSupportTests(unittest.TestCase):
    @staticmethod
    def _rows_to_dict(rows: list[list[str]] | None) -> dict[str, str]:
        output: dict[str, str] = {}
        for row in rows or []:
            if len(row) >= 2:
                output[row[0]] = row[1]
        return output

    def test_parse_identity_card_mrz_extracts_chile_back_fields(self) -> None:
        parsed = parse_identity_card_mrz(CHILE_ID_BACK_TEXT)

        self.assertEqual(parsed["issuing_country"], "CL")
        self.assertEqual(parsed["document_number"], "B64.872.150")
        self.assertEqual(parsed["run"], "21.952.550-8")
        self.assertEqual(parsed["birth_date"], "2005-10-13")
        self.assertEqual(parsed["expiry_date"], "2035-10-13")
        self.assertEqual(parsed["holder_name"], "NICOLAS FAELLES YARUR GONGORA")

    def test_classifier_prefers_identity_back_for_td1_mrz(self) -> None:
        classification = classify_document(CHILE_ID_BACK_TEXT, "auto", "AUTO")

        self.assertEqual(classification.document_family, "identity")
        self.assertEqual(classification.country, "CL")
        self.assertEqual(classification.variant, "identity-cl-back-text")
        self.assertEqual(classification.document_side, "back")

    def test_identity_normalizer_populates_back_side_from_mrz(self) -> None:
        normalized = normalize_identity_text(
            CHILE_ID_BACK_TEXT,
            "CL",
            "IMG_0843.jpeg",
            assumptions=[],
            pack_id="identity-cl-back",
            document_side="back",
        )
        sections = {section.id: section for section in normalized.report_sections}
        reverse_rows = self._rows_to_dict(sections["reverse"].rows)
        summary_rows = self._rows_to_dict(sections["summary"].rows)

        self.assertEqual(normalized.variant, "identity-cl-back-text")
        self.assertEqual(normalized.holder_name, "NICOLAS FAELLES YARUR GONGORA")
        self.assertGreaterEqual(normalized.global_confidence, 0.9)
        self.assertEqual(summary_rows["Numero"], "B64.872.150")
        self.assertEqual(summary_rows["RUN"], "21.952.550-8")
        self.assertEqual(reverse_rows["Lugar de nacimiento"], "PROVIDENCIA")

    def test_cross_side_merge_keeps_front_and_back_fields_consistent(self) -> None:
        page_analysis = PageAnalysisResult(
            pages=[
                _page_classification(1, CHILE_ID_FRONT_TEXT),
                _page_classification(2, CHILE_ID_BACK_TEXT),
            ],
            dominant=classify_document(CHILE_ID_FRONT_TEXT, "auto", "AUTO"),
            document_side="front+back",
            cross_side_detected=True,
            assumptions=[],
        )
        signal = build_cross_side_consistency_signal(page_analysis, [CHILE_ID_FRONT_TEXT, CHILE_ID_BACK_TEXT], "CL")

        normalized = _build_identity_cross_side_normalized(
            filename="front-back.pdf",
            page_analysis=page_analysis,
            page_texts=[CHILE_ID_FRONT_TEXT, CHILE_ID_BACK_TEXT],
            prepared_pages=[],
            cross_side_signal=signal,
            assumptions=[],
        )

        self.assertIsNotNone(normalized)
        if normalized is None:
            self.fail("Expected normalized front+back document")
        values: dict[str, str] = {}
        for section in normalized.report_sections:
            values.update(self._rows_to_dict(section.rows))
        self.assertEqual(normalized.holder_name, "NICOLAS FAELLES YARUR GONGORA")
        self.assertEqual(values["Numero de documento"], "B64.872.150")
        self.assertEqual(values["RUN"], "21.952.550-8")
        self.assertEqual(values["Lugar de nacimiento"], "PROVIDENCIA")


if __name__ == "__main__":
    unittest.main()
