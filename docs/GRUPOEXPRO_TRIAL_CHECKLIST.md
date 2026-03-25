# Grupoexpro Trial Checklist

## Trial token

- Company: `grupoexpro`
- Client id: `trial-grupoexpro`
- Tenant id: `trial-grupoexpro`
- Document limit: `50`
- Processing mode: `sync`
- Callbacks: `disabled`

## Suggested trial client config

```json
[
  {
    "id": "trial-grupoexpro",
    "name": "GrupoExpro Trial",
    "tenantId": "trial-grupoexpro",
    "apiKey": "REPLACE_WITH_REAL_TOKEN",
    "documentLimit": 50,
    "expiresAt": "2026-05-31T23:59:59Z",
    "allowCallbacks": false,
    "forceProcessingMode": "sync",
    "accessMode": "trial"
  }
]
```

## Web env vars

```bash
OCR_API_URL=https://<ocr-api-cloud-run-url>
NEXT_PUBLIC_SUPABASE_URL=https://<your-supabase-project>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-anon-key>
SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>
SUPABASE_STORAGE_BUCKET=documents
OCR_PUBLIC_ALLOW_DEV_AUTH=false
OCR_TRIAL_API_KEYS='[{"id":"trial-grupoexpro","name":"GrupoExpro Trial","tenantId":"trial-grupoexpro","apiKey":"REPLACE_WITH_REAL_TOKEN","documentLimit":50,"expiresAt":"2026-05-31T23:59:59Z","allowCallbacks":false,"forceProcessingMode":"sync","accessMode":"trial"}]'
```

## Quick validation

```bash
curl https://<web-url>/api/public/trial/v1/health

curl https://<web-url>/api/public/trial/v1/usage \
  -H "x-api-key: <trial-token>"

curl -X POST https://<web-url>/api/public/trial/v1/submissions \
  -H "x-api-key: <trial-token>" \
  -F "file=@./test-data/AFP.pdf" \
  -F "document_family=certificate" \
  -F "country=CL"
```
