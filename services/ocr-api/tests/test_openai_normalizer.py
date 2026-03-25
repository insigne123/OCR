from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.feature_flags import clear_feature_flags_cache
from app.services.openai_normalizer import _model, _pack_context


class OpenAINormalizerTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_feature_flags_cache()

    def test_identity_pack_prefers_mini_model_when_env_not_set(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            clear_feature_flags_cache()
            self.assertEqual(_model("identity", "identity-cl-front"), "gpt-4.1-mini")

    def test_passport_keeps_full_model_when_env_not_set(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            clear_feature_flags_cache()
            self.assertEqual(_model("passport", "passport-generic"), "gpt-4.1")

    def test_family_allowlist_can_restore_full_model(self) -> None:
        with patch.dict(os.environ, {"OCR_OPENAI_FULL_MODEL_FAMILIES": "passport,identity"}, clear=True):
            clear_feature_flags_cache()
            self.assertEqual(_model("identity", "identity-cl-front"), "gpt-4.1")

    def test_explicit_env_model_still_wins(self) -> None:
        with patch.dict(os.environ, {"OPENAI_MODEL": "gpt-4.1-mini"}, clear=True):
            clear_feature_flags_cache()
            self.assertEqual(_model("identity", "identity-cl-front"), "gpt-4.1-mini")

    def test_pack_context_includes_specialization_and_side(self) -> None:
        clear_feature_flags_cache()
        context = _pack_context("identity", "identity-cl-front", "front")
        self.assertIn("cedula de identidad chilena", context.lower())
        self.assertIn("Lado esperado del documento: front", context)

    def test_feature_flag_can_disable_pack_specialization(self) -> None:
        with patch.dict(os.environ, {"OCR_FEATURE_FLAGS": '{"pack_prompt_specialization": false}'}, clear=True):
            clear_feature_flags_cache()
            self.assertEqual(_model("identity", "identity-cl-front"), "gpt-4.1-mini")
            context = _pack_context("identity", "identity-cl-front", "front")
            self.assertNotIn("cedula de identidad chilena", context.lower())


if __name__ == "__main__":
    unittest.main()
