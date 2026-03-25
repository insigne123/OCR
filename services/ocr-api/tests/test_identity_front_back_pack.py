from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.document_packs import resolve_document_pack
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


class IdentityFrontBackPackTests(unittest.TestCase):
    def test_front_back_pack_resolves_for_chile_identity(self) -> None:
        pack = resolve_document_pack(pack_id="identity-cl-front-back")
        self.assertIsNotNone(pack)
        self.assertEqual(pack.document_side, "front+back")
        self.assertEqual(pack.variant, "identity-cl-front-back-text")

    def test_front_missing_mrz_does_not_block_accept_with_warning(self) -> None:
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
        self.assertNotIn("mrz", [issue.field for issue in evaluation.issues])


if __name__ == "__main__":
    unittest.main()
