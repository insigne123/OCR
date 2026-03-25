from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.feature_flags import clear_feature_flags_cache, feature_enabled, feature_flags_snapshot


class FeatureFlagsTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_feature_flags_cache()

    def test_defaults_enable_operational_features(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            clear_feature_flags_cache()
            snapshot = feature_flags_snapshot()
            self.assertTrue(snapshot["adaptive_confidence_recalibration"])
            self.assertTrue(snapshot["certificate_pdf_visual_support"])
            self.assertTrue(snapshot["mrz_cross_validation"])
            self.assertTrue(snapshot["pack_prompt_specialization"])

    def test_env_config_can_disable_specific_features(self) -> None:
        with patch.dict(
            os.environ,
            {"OCR_FEATURE_FLAGS": '{"mrz_cross_validation": false, "adaptive_confidence_recalibration": false}'},
            clear=True,
        ):
            clear_feature_flags_cache()
            self.assertFalse(feature_enabled("mrz_cross_validation"))
            self.assertFalse(feature_enabled("adaptive_confidence_recalibration"))
            self.assertTrue(feature_enabled("pack_prompt_specialization"))


if __name__ == "__main__":
    unittest.main()
