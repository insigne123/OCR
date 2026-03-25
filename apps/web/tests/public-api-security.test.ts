import test from "node:test";
import assert from "node:assert/strict";

import { normalizeCallbackUrl, normalizeManifestFileUrl } from "../src/lib/public-api-security.ts";

test("public api security accepts https callback URLs", () => {
  assert.equal(normalizeCallbackUrl("https://client.example.com/webhooks/ocr"), "https://client.example.com/webhooks/ocr");
  assert.equal(normalizeManifestFileUrl("https://client.example.com/files/doc.pdf"), "https://client.example.com/files/doc.pdf");
});

test("public api security blocks private network URLs by default", () => {
  assert.throws(() => normalizeCallbackUrl("http://localhost:3000/webhook"));
  assert.throws(() => normalizeManifestFileUrl("http://127.0.0.1:8000/doc.pdf"));
});

test("public api security can allow local development URLs explicitly", () => {
  process.env.OCR_PUBLIC_ALLOW_INSECURE_CALLBACKS = "true";
  process.env.OCR_PUBLIC_ALLOW_INSECURE_MANIFEST_FETCH = "true";
  process.env.OCR_PUBLIC_ALLOW_PRIVATE_NETWORK_URLS = "true";

  assert.equal(normalizeCallbackUrl("http://localhost:3000/webhook"), "http://localhost:3000/webhook");
  assert.equal(normalizeManifestFileUrl("http://127.0.0.1:8000/doc.pdf"), "http://127.0.0.1:8000/doc.pdf");

  delete process.env.OCR_PUBLIC_ALLOW_INSECURE_CALLBACKS;
  delete process.env.OCR_PUBLIC_ALLOW_INSECURE_MANIFEST_FETCH;
  delete process.env.OCR_PUBLIC_ALLOW_PRIVATE_NETWORK_URLS;
});
