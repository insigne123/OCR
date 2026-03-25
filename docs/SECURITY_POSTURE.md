# Security Posture

## Current hardening

- OCR API CORS is now configurable through `OCR_API_CORS_ALLOW_ORIGINS` and no longer defaults to wildcard credentials.
- Public API dev keys are disabled automatically in `production` unless `OCR_PUBLIC_ALLOW_DEV_AUTH` is enabled.
- Callback and manifest URLs are validated before outbound fetches.
- Private-network, localhost and metadata-style targets are blocked by default.
- Public webhooks are signed with HMAC-SHA256 and tracked with retry/backoff plus DLQ-style dead-letter status.
- Usage events and feedback events are written to a ledger for auditability and customer-facing analytics.

## Operational controls exposed by API

- Webhook delivery logs: `GET /api/public/v1/webhooks/logs`
- Manual redelivery: `POST /api/public/v1/webhooks/logs/{deliveryId}/retry`
- Feedback ingestion: `POST /api/public/v1/submissions/{id}/feedback`
- Usage and latency analytics: `GET /api/public/v1/analytics/*`

## Next compliance steps

- Move public API runtime state from local JSON store to Postgres/Supabase tables in production.
- Add immutable audit retention and tenant-configurable data retention policies.
- Add tenant-level encryption key strategy and regional residency controls.
- Add SSO, scoped API keys and formal SOC 2 / ISO 27001 evidence collection.

## Runtime persistence

- Public API submissions, batches, webhook logs, usage ledger and feedback now support Supabase persistence when server credentials are configured.
- Local JSON fallback remains available for development environments without Supabase.
