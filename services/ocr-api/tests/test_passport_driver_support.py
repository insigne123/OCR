from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.field_value_utils import validate_chile_run_checksum, validate_mrz_check_digits
from app.services.heuristic_normalizer import normalize_text_with_heuristics
from app.services.rule_packs import evaluate_normalized_document
from app.services.supplemental_field_extractors import _cleanup_driver_address
from app.services.synthetic_documents import generate_synthetic_record


PASSPORT_TEXT = """
PASSPORT
P<CHLPEREZ<<SOFIA<MATEO<<<<<<<<<<<<<<<<<<<<
AB1234567<3CHL9001012F3201019<<<<<<<<<<<<<<02
"""

DRIVER_TEXT = """
DRIVER LICENSE
NAME SOFIA MATEO PEREZ RAMOS
LICENSE NO B12345678
DATE OF BIRTH 1990-01-01
ISSUE DATE 2020-04-02
EXPIRY 2030-04-02
CLASS B
"""


class PassportDriverSupportTests(unittest.TestCase):
    def test_passport_heuristics_extract_mrz_and_holder(self) -> None:
        normalized = normalize_text_with_heuristics("passport", "CHL", "passport.png", PASSPORT_TEXT, assumptions=[])
        self.assertEqual(normalized.document_family, "passport")
        self.assertEqual(normalized.holder_name, "SOFIA MATEO PEREZ")
        self.assertGreaterEqual(normalized.global_confidence, 0.6)
        self.assertTrue(any(section.id == "passport" for section in normalized.report_sections))

    def test_driver_license_rules_accept_warning_when_core_fields_present(self) -> None:
        normalized = normalize_text_with_heuristics("driver_license", "CO", "license.png", DRIVER_TEXT, assumptions=[])
        evaluation = evaluate_normalized_document(normalized, pack_id="driver-license-generic", classification_confidence=0.9)
        self.assertIn(evaluation.decision, {"accept_with_warning", "auto_accept"})

    def test_validators_accept_known_good_values(self) -> None:
        passport = generate_synthetic_record("passport", "CHL", 1, seed=10)
        self.assertTrue(validate_mrz_check_digits(passport.expected_fields["mrz"]))
        self.assertTrue(validate_chile_run_checksum("21.952.550-8"))

    def test_passport_rules_detect_mrz_cross_field_mismatch(self) -> None:
        normalized = normalize_text_with_heuristics("passport", "CHL", "passport.png", PASSPORT_TEXT, assumptions=[])
        for section in normalized.report_sections:
            if section.id == "passport" and section.rows:
                for row in section.rows:
                    if row[0] == "Numero de documento":
                        row[1] = "AB1234568"

        evaluation = evaluate_normalized_document(normalized, pack_id="passport-generic", classification_confidence=0.95)
        self.assertEqual(evaluation.decision, "human_review")
        self.assertTrue(any(issue.id == "passport-mrz-document-mismatch" for issue in evaluation.issues))

    def test_driver_address_cleanup_recovers_street(self) -> None:
        cleaned = _cleanup_driver_address("24326012 21.952.550-8 ENCIA PAL DAD LA REINA NICOLAS FAELLES YARUR GONGORA DOS ALVARO CASANOVA 0360 CASA J 20/08/2024 B")
        self.assertEqual(cleaned, "ALVARO CASANOVA 0360 CASA J")


if __name__ == "__main__":
    unittest.main()
