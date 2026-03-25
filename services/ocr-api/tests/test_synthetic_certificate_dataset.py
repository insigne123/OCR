from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.synthetic_documents import build_manifest_entry, generate_synthetic_record, render_synthetic_document_bytes


class SyntheticCertificateDatasetTests(unittest.TestCase):
    def test_generates_certificate_afp_record_with_expected_tables(self) -> None:
        record = generate_synthetic_record("certificate", "CL", 1, condition="clean", seed=7)

        self.assertEqual(record.pack_id, "certificate-cl-previsional")
        self.assertIn("rut", record.expected_fields)
        self.assertIn("certificate_number", record.expected_fields)
        self.assertIsNotNone(record.expected_tables)
        self.assertGreaterEqual(len((record.expected_tables or {}).get("movements", [])), 12)

    def test_build_manifest_entry_preserves_expected_tables(self) -> None:
        record = generate_synthetic_record("certificate", "CL", 2, condition="clean", seed=11)
        manifest_entry = build_manifest_entry(record, "images/certificate.png")

        self.assertIn("expected_tables", manifest_entry)
        self.assertIn("movements", manifest_entry["expected_tables"])

    def test_render_synthetic_certificate_bytes(self) -> None:
        record = generate_synthetic_record("certificate", "CL", 3, condition="jpeg", seed=19)
        payload = render_synthetic_document_bytes(record)

        self.assertGreater(len(payload), 2000)


if __name__ == "__main__":
    unittest.main()
