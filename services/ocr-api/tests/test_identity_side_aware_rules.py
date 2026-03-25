from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.heuristic_normalizer import normalize_identity_text
from app.services.rule_packs import evaluate_normalized_document


CHILE_ID_FRONT_TEXT = """REPUBLICA DE CHILE
CEDULA DE IDENTIDAD
SERVICIO DE REGISTRO CIVIL E IDENTIFICACION
APELLIDOS
YARUR
GONGORA
NOMBRES
NICOLAS FAELLES
NACIONALIDAD
CHILENA
SEXO
M
FECHA DE NACIMIENTO
13 OCT 2005
NUMERO DOCUMENTO
B64.872.150
FECHA DE EMISION
02 DIC 2025
FECHA DE VENCIMIENTO
13 OCT 2035
RUN
21.952.550-8"""


CHILE_ID_BACK_TEXT = """NACICAN
438584
Nacio en:
PROVIDENCIA
INCHLB648721500S13<<<<<<<<<<<<
0510132M3510133CHL21952550<8<9
YARURKGONGORAK<NICOLASKFAELLES"""


class IdentitySideAwareRuleTests(unittest.TestCase):
    def test_front_side_does_not_require_mrz(self) -> None:
        normalized = normalize_identity_text(
            CHILE_ID_FRONT_TEXT,
            "CL",
            "front.jpeg",
            assumptions=[],
            pack_id="identity-cl-front",
            document_side="front",
        )
        evaluation = evaluate_normalized_document(
            normalized,
            pack_id="identity-cl-front",
            classification_confidence=0.97,
            document_side="front",
            decision_profile="balanced",
        )

        self.assertFalse(any(issue.field == "mrz" for issue in evaluation.issues))

    def test_back_side_can_auto_accept_with_mrz_evidence(self) -> None:
        normalized = normalize_identity_text(
            CHILE_ID_BACK_TEXT,
            "CL",
            "back.jpeg",
            assumptions=[],
            pack_id="identity-cl-back",
            document_side="back",
        )
        evaluation = evaluate_normalized_document(
            normalized,
            pack_id="identity-cl-back",
            classification_confidence=0.97,
            document_side="back",
            decision_profile="balanced",
        )

        self.assertEqual(evaluation.decision, "auto_accept")


if __name__ == "__main__":
    unittest.main()
