from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.schemas import NormalizedDocument, ReportSection, ValidationIssue
from app.services.cross_side_consistency import CrossSideConsistencySignal
from app.services.rule_packs import FieldDecisionSignal, evaluate_normalized_document


def _identity_document() -> NormalizedDocument:
    return NormalizedDocument(
        document_family="identity",
        country="CL",
        variant="identity-cl-front-text",
        issuer="Registro Civil e Identificacion",
        holder_name="JUAN PEREZ",
        global_confidence=0.98,
        assumptions=[],
        issues=[],
        report_sections=[
            ReportSection(
                id="identity",
                title="Identidad",
                variant="pairs",
                rows=[
                    ["Nombre completo", "JUAN PEREZ"],
                    ["Numero de documento", "12.345.678-5"],
                    ["RUN", "12.345.678-5"],
                    ["MRZ", "IDCHL123456789<<<<<<<<<<<<<<<"],
                ],
            ),
            ReportSection(
                id="dates",
                title="Fechas",
                variant="table",
                columns=["Campo", "Valor"],
                rows=[
                    ["Fecha de nacimiento", "1990-01-01"],
                    ["Fecha de emision", "2020-01-01"],
                    ["Fecha de vencimiento", "2030-01-01"],
                ],
            ),
        ],
        human_summary=None,
    )


class RulePackTests(unittest.TestCase):
    def test_identity_auto_accepts_with_high_confidence_and_agreement(self) -> None:
        result = evaluate_normalized_document(
            _identity_document(),
            pack_id="identity-cl-front",
            classification_confidence=0.97,
            document_side="front",
            decision_profile="balanced",
            field_signals={
                "holder_name": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                "document_number": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                "run": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                "birth_date": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                "expiry_date": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
            },
        )

        self.assertEqual(result.decision, "auto_accept")
        self.assertFalse(result.review_required)

    def test_identity_routes_to_review_when_critical_field_disagrees(self) -> None:
        result = evaluate_normalized_document(
            _identity_document(),
            pack_id="identity-cl-front",
            classification_confidence=0.97,
            document_side="front",
            decision_profile="balanced",
            field_signals={
                "holder_name": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                "document_number": FieldDecisionSignal(agreement_ratio=0.33, disagreement=True, candidate_count=3, supporting_engines=("google",)),
                "run": FieldDecisionSignal(agreement_ratio=0.33, disagreement=True, candidate_count=3, supporting_engines=("google",)),
            },
        )

        self.assertEqual(result.decision, "human_review")
        self.assertTrue(any(issue.type == "RULE_ENGINE_DISAGREEMENT" for issue in result.issues))

    def test_identity_low_evidence_warning_no_longer_blocks_auto_accept(self) -> None:
        document = _identity_document()
        document.issues = [
            ValidationIssue(
                id="identity-low-evidence",
                type="RULE_LOW_EVIDENCE",
                field="mrz",
                severity="low",
                message="MRZ parcial pero consistente.",
                suggestedAction="Mantener warning informativo.",
            )
        ]

        result = evaluate_normalized_document(
            document,
            pack_id="identity-cl-front",
            classification_confidence=0.97,
            document_side="front",
            decision_profile="balanced",
            field_signals={
                "holder_name": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                "document_number": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                "run": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                "birth_date": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                "expiry_date": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
            },
        )

        self.assertEqual(result.decision, "auto_accept")
        self.assertFalse(result.review_required)

    def test_identity_front_back_mismatch_forces_review(self) -> None:
        document = _identity_document()
        document.variant = "identity-cl-front-back-text"
        result = evaluate_normalized_document(
            document,
            pack_id="identity-cl-front",
            classification_confidence=0.97,
            document_side="front+back",
            decision_profile="balanced",
            field_signals={
                "holder_name": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                "document_number": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                "run": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                "birth_date": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                "expiry_date": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
            },
            cross_side_signal=CrossSideConsistencySignal(
                front_present=True,
                back_present=True,
                front_identifier="12.345.678-5",
                back_identifier="12.345.678-K",
                identifier_match=False,
                assumptions=["cross-side mismatch"],
            ),
        )

        self.assertEqual(result.decision, "human_review")
        self.assertTrue(any(issue.id == "rule-identity-cross-side-identifier-mismatch" for issue in result.issues))

    def test_tenant_threshold_override_can_downgrade_auto_accept(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OCR_DECISION_POLICY_CONFIG": '{"rules":[{"tenantId":"tenant-low-trust","packId":"identity-cl-front","thresholds":{"autoAcceptConfidence":0.995}}]}'
            },
            clear=False,
        ):
            result = evaluate_normalized_document(
                _identity_document(),
                pack_id="identity-cl-front",
                classification_confidence=0.97,
                document_side="front",
                decision_profile="balanced",
                tenant_id="tenant-low-trust",
                field_signals={
                    "holder_name": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                    "document_number": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                    "run": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                    "birth_date": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                    "expiry_date": FieldDecisionSignal(agreement_ratio=1.0, disagreement=False, candidate_count=1, supporting_engines=("google", "azure")),
                },
            )

        self.assertEqual(result.decision, "accept_with_warning")


if __name__ == "__main__":
    unittest.main()
