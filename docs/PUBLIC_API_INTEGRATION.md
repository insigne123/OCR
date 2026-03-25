# Public API Integration

This repository now exposes a public integration layer on top of the OCR platform in the Next.js app.

## Authentication

- Header: `x-api-key: <client-key>`
- Alternative: `Authorization: Bearer <client-key>`

Runtime configuration:

- `OCR_PUBLIC_API_KEY` for a single default client
- `OCR_PUBLIC_API_KEYS` for multiple clients as JSON array
- `OCR_PUBLIC_DEFAULT_TENANT_ID`
- `OCR_PUBLIC_WEBHOOK_SECRET` for webhook signatures
- `OCR_PUBLIC_ALLOW_DEV_AUTH=false` to disable implicit local dev keys
- `OCR_PUBLIC_ALLOW_PRIVATE_NETWORK_URLS=true` only if you explicitly need localhost/private callbacks or manifest fetches
- `OCR_PUBLIC_CALLBACK_HOST_ALLOWLIST` and `OCR_PUBLIC_MANIFEST_HOST_ALLOWLIST` to restrict outbound destinations
- `OCR_TRIAL_API_KEY` or `OCR_TRIAL_API_KEYS` for trial-only tokens
- `OCR_TRIAL_DOCUMENT_LIMIT` to set the default cap per trial token (`50` recommended)
- `OCR_TRIAL_EXPIRES_AT` to set a hard expiration for a single trial token

Example multi-client config:

```json
[
  {
    "id": "client-retail-a",
    "name": "Retail A",
    "tenantId": "tenant-retail-a",
    "apiKey": "super-secret-a"
  },
  {
    "id": "client-retail-b",
    "name": "Retail B",
    "tenantId": "tenant-retail-b",
    "apiKey": "super-secret-b"
  }
]
```

## Limits

Defaults:

- single file: `15 MB`
- batch item count: `20`
- batch total size: `100 MB`
- manifest item count: `100`
- sync batch item count: `5`

Supported MIME types:

- `application/pdf`
- `image/jpeg`
- `image/png`
- `image/heic`
- `image/heif`
- `image/tiff`

## Endpoints

## Trial API

Dedicated trial endpoints for customer validation with token auth and capped usage.

- `GET /api/public/trial/v1/health`
- `GET /api/public/trial/v1/usage`
- `POST /api/public/trial/v1/submissions`
- `GET /api/public/trial/v1/submissions`
- `GET /api/public/trial/v1/submissions/{submissionId}`
- `GET /api/public/trial/v1/submissions/{submissionId}/result`

Trial behavior:

- single-document only
- forced `sync` processing
- callbacks disabled by default
- capped to `50` documents per token unless overridden in config

### Health

- `GET /api/public/v1/health`

### Single submission

- `POST /api/public/v1/submissions`
- `GET /api/public/v1/submissions`
- `GET /api/public/v1/submissions/{submissionId}`
- `GET /api/public/v1/submissions/{submissionId}/result`
- `GET /api/public/v1/submissions/{submissionId}/feedback`
- `POST /api/public/v1/submissions/{submissionId}/feedback`

Multipart fields:

- `file`
- `document_family`
- `country`
- `external_id`
- `callback_url`
- `metadata` JSON string
- `processing_mode=sync|queue`

### Batch upload

- `POST /api/public/v1/batches/upload`
- `GET /api/public/v1/batches`
- `GET /api/public/v1/batches/{batchId}`
- `GET /api/public/v1/batches/{batchId}/items`

Multipart fields:

- `files` repeated
- `document_family`
- `country`
- `external_id`
- `callback_url`
- `metadata` JSON string
- `processing_mode=sync|queue`

### Batch manifest

- `POST /api/public/v1/batches/manifest`

JSON body:

```json
{
  "external_id": "lote-001",
  "callback_url": "https://cliente.example.com/webhooks/ocr",
  "processing_mode": "queue",
  "defaults": {
    "document_family": "certificate",
    "country": "CL"
  },
  "items": [
    {
      "file_url": "https://cliente.example.com/docs/afp-001.pdf",
      "external_id": "afp-001"
    }
  ]
}
```

## Webhooks

Submission events:

- `submission.completed`
- `submission.review_required`
- `submission.rejected`
- `submission.failed`

Batch events:

- `batch.completed`
- `batch.partial`
- `batch.failed`

Webhook headers:

- `x-ocr-public-event`
- `x-ocr-public-delivered-at`
- `x-ocr-public-signature` when `OCR_PUBLIC_WEBHOOK_SECRET` is configured
- `x-ocr-public-delivery-id`
- `x-ocr-public-attempt`

Webhook operability endpoints:

- `GET /api/public/v1/webhooks/logs`
- `POST /api/public/v1/webhooks/logs` with `{ "action": "drain" }`
- `POST /api/public/v1/webhooks/logs/{deliveryId}/retry`

## Analytics

- `GET /api/public/v1/analytics/usage`
- `GET /api/public/v1/analytics/latency`
- `GET /api/public/v1/analytics/decisions`
- `GET /api/public/v1/analytics/accuracy`

## Notes

- `sync` mode processes the document before returning.
- `queue` mode leaves the item queued for the worker flow.
- Batch completion webhooks fire only after the batch is fully registered and all items are in terminal states.
- Callback and manifest URLs default to HTTPS-only and block obvious private-network targets unless explicitly allowed by env.
