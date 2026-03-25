from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.synthetic_documents import build_manifest_entry, generate_synthetic_record, render_synthetic_document_bytes


class SyntheticDocumentsTests(unittest.TestCase):
    def test_generates_passport_with_mrz(self) -> None:
        record = generate_synthetic_record("passport", "CHL", 1, seed=10)
        self.assertEqual(record.family, "passport")
        self.assertIn("mrz", record.expected_fields)
        self.assertEqual(len((record.expected_fields["mrz"] or "").splitlines()), 2)

    def test_renders_identity_document_bytes(self) -> None:
        record = generate_synthetic_record("identity", "CL", 2, seed=10)
        image_bytes = render_synthetic_document_bytes(record)
        self.assertGreater(len(image_bytes), 1000)
        manifest = build_manifest_entry(record, "images/sample.png")
        self.assertEqual(manifest["pack_id"], "identity-cl-front")
        self.assertEqual(manifest["filename"], "images/sample.png")


if __name__ == "__main__":
    unittest.main()
