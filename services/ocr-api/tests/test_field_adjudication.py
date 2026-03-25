from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.schemas import FieldCandidateResult, FieldConsensusResult
from app.services.document_packs import PackFieldDefinition, resolve_document_pack
from app.services.field_adjudication import adjudicate_field, should_adjudicate_pack


class FieldAdjudicationTests(unittest.TestCase):
    def test_deterministic_selects_high_support_value(self) -> None:
        decision = adjudicate_field(
            field=PackFieldDefinition("document_number", "Numero de documento", required=True, critical=True),
            current_value="12.345.678-5",
            candidates=[
                FieldCandidateResult(engine="google", source="google", value="12.345.678-5", confidence=0.98, selected=True, score=0.98),
                FieldCandidateResult(engine="azure", source="azure", value="12.345.678-5", confidence=0.95, selected=True, score=0.95),
                FieldCandidateResult(engine="rapidocr", source="rapidocr", value="12.345.678-K", confidence=0.65, selected=False, score=0.42),
            ],
            consensus=FieldConsensusResult(
                engines_considered=3,
                candidate_count=2,
                supporting_engines=["google", "azure"],
                agreement_ratio=0.67,
                disagreement=True,
            ),
        )

        self.assertFalse(decision.abstained)
        self.assertEqual(decision.selected_value, "12.345.678-5")

    def test_deterministic_abstains_on_critical_low_margin_conflict(self) -> None:
        decision = adjudicate_field(
            field=PackFieldDefinition("run", "RUN", required=True, critical=True),
            current_value="12.345.678-5",
            candidates=[
                FieldCandidateResult(engine="google", source="google", value="12.345.678-5", confidence=0.75, selected=True, score=0.72),
                FieldCandidateResult(engine="azure", source="azure", value="12.345.678-K", confidence=0.74, selected=False, score=0.71),
            ],
            consensus=FieldConsensusResult(
                engines_considered=2,
                candidate_count=2,
                supporting_engines=["google"],
                agreement_ratio=0.5,
                disagreement=True,
            ),
        )

        self.assertTrue(decision.abstained)
        self.assertIsNone(decision.selected_value)

    def test_certificate_pack_is_now_eligible_for_adjudication(self) -> None:
        pack = resolve_document_pack(pack_id="certificate-cl-previsional", document_family="certificate", country="CL", variant="certificate-cl-previsional-text")
        self.assertIsNotNone(pack)
        self.assertTrue(should_adjudicate_pack(pack, mode_override="deterministic"))


if __name__ == "__main__":
    unittest.main()
