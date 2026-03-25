# Production Runbook

## Pre-deploy

1. Apply SQL migrations in order:
   - `infra/sql/001_initial_schema.sql`
   - `infra/sql/002_auth_rls.sql`
   - `infra/sql/003_processing_metadata.sql`
   - `infra/sql/004_processing_jobs_runtime.sql`
2. Configure secrets:
   - Supabase keys and bucket
   - `OCR_API_KEY`
   - `OCR_PUBLIC_API_KEY` or `OCR_PUBLIC_API_KEYS`
   - `OCR_PUBLIC_DEFAULT_TENANT_ID`
   - `OCR_PUBLIC_WEBHOOK_SECRET` if client callbacks are enabled
   - `OPENAI_API_KEY` if using structured normalization
   - `OCR_RESULT_WEBHOOK_URL` and `OCR_RESULT_WEBHOOK_SECRET` if webhooks are enabled
   - optional cloud OCR credentials for Azure/Google
3. Configure runtime selectors:
     - `OCR_VISUAL_ENGINE`
     - `OCR_TENANT_PROCESSING_CONFIG`
     - `OCR_DECISION_POLICY_CONFIG`
     - `OCR_DEFAULT_VISUAL_ENGINE`
     - `OCR_DEFAULT_DECISION_PROFILE`
     - optional cost selectors: `OCR_COST_GOOGLE_DOCUMENTAI`, `OCR_COST_AZURE_DOCUMENT_INTELLIGENCE`, `OCR_COST_OPENAI_FIELD_ADJUDICATION`
4. Ensure mobile-image dependencies are available for HEIC/HEIF ingest (`pillow-heif` in the OCR API environment)

## Deploy validation

1. Run CI (`typecheck`, `tests`, `build`)
2. Start web and OCR API
3. Run smoke checks:

```bash
node scripts/smoke-check.mjs
```

4. Verify protected routes redirect correctly to `/login`
5. Verify `/api/metrics?format=json`
6. Verify `/api/datasets/golden-set?evaluate=1`
7. Verify `/api/datasets/learning-loop?persist=1`
8. Verify `/api/benchmarks/routing?decision_profile=balanced&persist=1`
9. Verify `/api/ops/audit?action_prefix=snapshot.`
10. Verify `/api/ops/calibration/recommendation`
11. Verify `/api/ops/snapshots/compare?action=snapshot.learning_loop`
12. Verify `/api/datasets/registry`
13. Verify `/api/datasets/registry/<dataset-name>` for a registered synthetic dataset
13. Generate a synthetic dataset smoke sample with `python scripts/generate-synthetic-dataset.py synthetic-data/smoke --count-per-combination 2 --register`
14. Evaluate a tiny manifest locally with `python scripts/evaluate-dataset.py synthetic-data/smoke/manifest.jsonl --limit 2 --visual-engine rapidocr --ensemble-mode single --ensemble-engines rapidocr --field-adjudication-mode off`
15. Verify a sample document reaches `completed`, `review`, and `rejected` paths

## Incident triage

- Check `/api/health` and `/v1/health`
- Check `/api/metrics?format=json`
- Review latest failed jobs in `/jobs`
- Inspect webhook delivery metadata in the latest job `result.webhook`
- If OCR quality degrades, benchmark engines with `/api/benchmarks/golden-set`
- Compare routing precision/cost with `/api/benchmarks/routing`
- Review persisted snapshots and audit trail with `/api/ops/audit`
- Export threshold overrides with `/api/ops/calibration/recommendation`
- Compare latest operational snapshots with `/api/ops/snapshots/compare`
- Inspect registered local/synthetic datasets with `/api/datasets/registry`
- Re-run targeted mobile capture checks with `python scripts/run-batch-ocr.py test-data --pattern "IMG_08*" --limit 6 --visual-engine auto --structured-mode auto --ensemble-mode always --ensemble-engines rapidocr,google-documentai,azure-document-intelligence --field-adjudication-mode auto`

## PII and retention

- External payloads are redacted unless `OCR_WEBHOOK_REDACT_PII=false`
- API logs redact sensitive identifiers unless `OCR_LOG_REDACT_PII=false`
- Retention preview/apply:

```bash
curl -X POST http://127.0.0.1:3000/api/admin/retention
curl -X POST http://127.0.0.1:3000/api/admin/retention?apply=1
```
