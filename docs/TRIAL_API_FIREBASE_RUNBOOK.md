# Trial API Runbook

## Objetivo

Exponer una API de prueba segura para una empresa evaluadora, limitada a `50` documentos por token, usando:

- `apps/web` en Firebase App Hosting
- `services/ocr-api` en Cloud Run
- Supabase para persistencia y control de cuota

## Endpoints de trial

- `GET /api/public/trial/v1/health`
- `GET /api/public/trial/v1/usage`
- `POST /api/public/trial/v1/submissions`
- `GET /api/public/trial/v1/submissions`
- `GET /api/public/trial/v1/submissions/{submissionId}`
- `GET /api/public/trial/v1/submissions/{submissionId}/result`

## Seguridad del trial

- autenticacion por `x-api-key` o `Authorization: Bearer <token>`
- cuota por token/cliente
- limite por defecto de `50` documentos
- expiracion opcional por token
- `sync` obligatorio para evitar dependencia de workers en el trial
- callbacks deshabilitados por defecto

## Variables de entorno recomendadas

### Web app

- `OCR_API_URL=https://<ocr-api-cloud-run-url>`
- `NEXT_PUBLIC_SUPABASE_URL=...`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY=...`
- `SUPABASE_SERVICE_ROLE_KEY=...`
- `SUPABASE_STORAGE_BUCKET=documents`
- `OCR_TRIAL_API_KEYS=[...]`
- `OCR_PUBLIC_ALLOW_DEV_AUTH=false`

Ejemplo de `OCR_TRIAL_API_KEYS`:

```json
[
  {
    "id": "trial-empresa-a",
    "name": "Empresa A Trial",
    "tenantId": "trial-empresa-a",
    "apiKey": "reemplaza-por-un-token-largo-y-aleatorio",
    "documentLimit": 50,
    "expiresAt": "2026-05-31T23:59:59Z",
    "allowCallbacks": false,
    "forceProcessingMode": "sync",
    "accessMode": "trial"
  }
]
```

### OCR API en Cloud Run

- `OCR_API_KEY=<token-interno-opcional>`
- `OCR_VISUAL_ENGINE=rapidocr`
- `OCR_STRUCTURED_NORMALIZER_MODE=auto`
- `OPENAI_API_KEY=...` si usaras normalizacion avanzada
- credenciales Azure/Google si quieres fallback premium

## Supabase

Aplicar migraciones en orden:

1. `infra/sql/001_initial_schema.sql`
2. `infra/sql/002_auth_rls.sql`
3. `infra/sql/003_processing_metadata.sql`
4. `infra/sql/004_processing_jobs_runtime.sql`
5. `infra/sql/005_public_api_operability.sql`
6. `infra/sql/006_public_api_runtime_store.sql`

## Despliegue recomendado

### 1. OCR API a Cloud Run

Usa el `Dockerfile` incluido en `services/ocr-api`, que ya queda alineado con Python `3.12` para mejor compatibilidad con OCR local.

Desde la raiz del repo:

```bash
gcloud run deploy ocr-api-trial \
  --source services/ocr-api \
  --region us-central1 \
  --allow-unauthenticated
```

Si prefieres Dockerfile:

```bash
gcloud builds submit --tag gcr.io/<PROJECT_ID>/ocr-api-trial ./services/ocr-api
gcloud run deploy ocr-api-trial \
  --image gcr.io/<PROJECT_ID>/ocr-api-trial \
  --region us-central1 \
  --allow-unauthenticated
```

### 2. Web app a Firebase App Hosting

- conecta el repo en Firebase App Hosting
- selecciona `apps/web`
- configura las variables de entorno listadas arriba
- asegúrate de que `OCR_API_URL` apunte al Cloud Run del OCR API

## Validacion post deploy

### Health

```bash
curl https://<WEB_URL>/api/public/trial/v1/health
curl https://<WEB_URL>/api/public/trial/v1/usage -H "x-api-key: <TRIAL_TOKEN>"
```

### Submission de prueba

```bash
curl -X POST "https://<WEB_URL>/api/public/trial/v1/submissions" \
  -H "x-api-key: <TRIAL_TOKEN>" \
  -F "file=@./test-data/AFP.pdf" \
  -F "document_family=certificate" \
  -F "country=CL"
```

### Resultado

```bash
curl "https://<WEB_URL>/api/public/trial/v1/submissions/<SUBMISSION_ID>/result" \
  -H "x-api-key: <TRIAL_TOKEN>"
```

## Recomendaciones operativas

- usa un token distinto por empresa
- fija `expiresAt` en cada trial
- no compartas el token por correo sin cifrado o canal seguro
- revisa `GET /api/public/trial/v1/usage` antes de ampliar la cuota
- para trials, evita batch y manifest; este flujo esta pensado para demostracion controlada
