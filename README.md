# OCR Platform

Base monorepo for the OCR application.

## Packages

- `apps/web`: Next.js application for upload, monitoring, review and reports.
- `packages/shared`: shared TypeScript types for documents and reports.
- `services/ocr-api`: FastAPI service for OCR and normalization pipeline.
- `infra/sql`: initial Supabase schema.

## Quick start

```bash
npm install
npm run dev:web
```

In another terminal:

```bash
python -m uvicorn app.main:app --reload --app-dir services/ocr-api
```

Optional environment variables:

```bash
cp .env.example .env.local
```

Relevant OCR runtime selector:

- `OCR_VISUAL_ENGINE=rapidocr|paddleocr|doctr|azure-document-intelligence|google-documentai|auto` (`rapidocr` by default for local stability)

Apply the Supabase SQL files in order when enabling production persistence/auth:

1. `infra/sql/001_initial_schema.sql`
2. `infra/sql/002_auth_rls.sql`
3. `infra/sql/003_processing_metadata.sql`
4. `infra/sql/004_processing_jobs_runtime.sql`
5. `infra/sql/005_public_api_operability.sql`
6. `infra/sql/006_public_api_runtime_store.sql`

If you enable Supabase mode, also review these values in `.env.local`:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_STORAGE_BUCKET`
- `SUPABASE_DEFAULT_TENANT_SLUG`
- `SUPABASE_DEFAULT_TENANT_NAME`
- `SUPABASE_BOOTSTRAP_TENANT_ACCESS` -> use `true` only for the first tenant bootstrap flow
- `NEXT_PUBLIC_SITE_URL`
- `OCR_RESULT_WEBHOOK_URL`
- `OCR_RESULT_WEBHOOK_SECRET`
- `OCR_PUBLIC_API_KEY` or `OCR_PUBLIC_API_KEYS`
- `OCR_PUBLIC_DEFAULT_TENANT_ID`
- `OCR_PUBLIC_WEBHOOK_SECRET`
- `OCR_WEBHOOK_REDACT_PII`
- `OCR_LOG_REDACT_PII`
- `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`
- `AZURE_DOCUMENT_INTELLIGENCE_KEY`
- `AZURE_DOCUMENT_INTELLIGENCE_MODEL`
- `GOOGLE_DOCUMENTAI_PROJECT_ID`
- `GOOGLE_DOCUMENTAI_LOCATION`
- `GOOGLE_DOCUMENTAI_PROCESSOR_ID`
- `OCR_TENANT_PROCESSING_CONFIG`
- `OCR_DEFAULT_VISUAL_ENGINE`
- `OCR_DEFAULT_DECISION_PROFILE`
- `OCR_DEFAULT_STRUCTURED_MODE`
- `OCR_DEFAULT_ENSEMBLE_MODE`
- `OCR_DEFAULT_ENSEMBLE_ENGINES`
- `OCR_DEFAULT_FIELD_ADJUDICATION_MODE`
- `OCR_ADAPTIVE_ROUTING_CONFIG`
- `OCR_STRUCTURED_NORMALIZER_MODE` (`auto` recomendado para activar OpenAI solo cuando aporte valor)
- `OCR_ENABLE_VISUAL_FALLBACK`
- `OCR_PREMIUM_FALLBACK_ENGINE` (`google-documentai` recomendado como fallback premium)
- `OCR_PREMIUM_ROUTING_MODE` (`adaptive` recomendado para mantener local-first y escalar solo cuando hace falta)
- `OCR_FIELD_ADJUDICATION_MODEL` (`gpt-4.1-mini` recomendado para conflictos criticos por campo)
- `OCR_OPENAI_FULL_MODEL_FAMILIES` / `OCR_OPENAI_FULL_MODEL_PACKS` (usar `gpt-4.1` solo en familias o packs de alto riesgo, por defecto `passport`)
- `OCR_RETENTION_DAYS_REPORTS`
- `OCR_RETENTION_DAYS_REVIEWS`

## Authentication

- If `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` are configured, the app enables Supabase Auth.
- Protected routes will redirect to `/login`.
- You can sign in with password or magic link.

## Health checks

- Web app: `GET /api/health`
- OCR API: `GET /v1/health`

## Ops

- Smoke checks: `npm run smoke`
- Supabase validation: `npm run validate:supabase`
- OCR provider validation: `npm run validate:providers`
- Synthetic dataset generation: `python scripts/generate-synthetic-dataset.py synthetic-data/demo-latam --count-per-combination 24 --register`
- Offline dataset evaluation: `python scripts/evaluate-dataset.py synthetic-data/demo-latam/manifest.jsonl --visual-engine rapidocr --ensemble-mode single --ensemble-engines rapidocr`
- Registered dataset evaluation: `python scripts/evaluate-dataset.py demo-latam --split test --group-by capture_condition,pack_id`
- Targeted mobile benchmark over new test captures: `python scripts/run-batch-ocr.py test-data --pattern "IMG_08*" --limit 6 --visual-engine auto --structured-mode auto --ensemble-mode always --ensemble-engines rapidocr,google-documentai,azure-document-intelligence --field-adjudication-mode auto`
- Regression over cedula, licencia y AFP: `python scripts/run_triplet_regression.py`
- Runbook: `docs/PRODUCTION_RUNBOOK.md`

## Current scope

- repository abstraction with local mode and Supabase-ready mode
- local upload persistence or Supabase Storage upload depending on server env
- FastAPI OCR API with embedded PDF text extraction, heuristic normalization and optional OpenAI structured normalization
- mobile-capture hardening with crop heuristics, glare/shadow rescue variants, denoise, CLAHE, adaptive binarization and OCR retry profiles
- HEIC intake support via Pillow/HEIF integration for mobile-origin captures
- review queue, report library and initial human review console
- job monitoring page and API endpoint for latest processing status
- queue-based processing flow with manual job runner from the Jobs view
- public integration API for single submissions, batch uploads and manifest batches
- original file preview from local storage or Supabase Storage
- derived page preprocessing metadata and persisted page previews for processed documents
- reviewed dataset export, golden set snapshot/evaluation and local metrics endpoint
- public API webhook log queue with retry/backoff, DLQ and manual redelivery
- public API usage ledger plus analytics endpoints for usage, accuracy, latency and decisions
- public feedback API that turns client corrections into review sessions and learning-loop inputs
- synthetic dataset generation and local dataset registry for IDs, passports and driver licenses
- offline evaluation tooling for manifests with capture-condition metrics
- registry-backed dataset inspection route for operational dataset discovery
- Supabase Auth login, logout and protected routes when public keys are configured
- standalone Next.js output, Dockerfiles and CI workflow baseline
- Supabase schema draft aligned more closely with provenance and review needs

## API-first usage

Primary product interface:

- `POST /v1/process` on the OCR API
- `POST /v1/classify`, `POST /v1/analyze/quality`, `POST /v1/extract/tables`, `POST /v1/extract/custom` on the OCR API
- `POST /api/public/v1/submissions` on the web app for external company integrations
- `POST /api/public/trial/v1/submissions` on the web app for controlled customer trials capped at 50 docs per token
- `GET /api/public/v1/analytics/*`, `GET /api/public/v1/webhooks/logs` and `POST /api/public/v1/submissions/{id}/feedback` on the web app for integration observability and learning loop

Request fields:

- `file`: document or image
- `document_family`: `certificate`, `identity`, `invoice`, `unclassified`
- also supports `passport` and `driver_license` in the OCR pipeline
- `country`: ISO-like country code, e.g. `CL`
- `response_mode`: `json` or `full`

Headers:

- `x-api-key: <OCR_API_KEY>` when `OCR_API_KEY` is configured in the OCR API

Example with `curl`:

```bash
curl -X POST "http://127.0.0.1:8000/v1/process" \
  -H "x-api-key: $OCR_API_KEY" \
  -F "file=@./sample.pdf" \
  -F "document_family=certificate" \
  -F "country=CL" \
  -F "response_mode=json"
```

The main output is canonical JSON containing:

- `document`
- `processing`
- `fields`
- `issues`
- `assumptions`
- `human_summary`

External integration guide:

- `docs/PUBLIC_API_INTEGRATION.md`
- `docs/TRIAL_API_FIREBASE_RUNBOOK.md`

## Playground

- Internal test UI: `/playground`
- Lets you upload a document/image and inspect the returned JSON from the OCR endpoint.

See `PLAN_TECNICO_OCR_APP.md` for the base technical architecture and `docs/PLAN_EVOLUTIVO_OCR_PRODUCTO.md` for the full evolutionary implementation roadmap.
