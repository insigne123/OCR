# GrupoExpro Deploy Guide (`ocr1-491302`)

## Objetivo

Desplegar:

- `apps/web` en Firebase App Hosting
- `services/ocr-api` en Cloud Run
- trial token de `grupoexpro` con limite de `50` documentos

## Proyecto

- Project name: `OCR1`
- Project id: `ocr1-491302`
- Project number: `96696628584`

## Trial config para GrupoExpro

```json
[
  {
    "id": "trial-grupoexpro",
    "name": "GrupoExpro Trial",
    "tenantId": "trial-grupoexpro",
    "apiKey": "QpQSZxS2s8oPQOsR5CmTNA2rsBRouVs4DWYKlkflPso",
    "documentLimit": 50,
    "expiresAt": "2026-05-31T23:59:59Z",
    "allowCallbacks": false,
    "forceProcessingMode": "sync",
    "accessMode": "trial"
  }
]
```

## 1. Preparar IAM para Cloud Build / Artifact Registry / Cloud Run

Usa PowerShell.

```powershell
gcloud config set project ocr1-491302
gcloud config set account nicolas.yarur.g@yago.cl
gcloud auth application-default login
gcloud auth application-default set-quota-project ocr1-491302
```

Grant recomendado para la service account de build por defecto:

```powershell
$PROJECT="ocr1-491302"
$PROJECT_NUMBER="96696628584"
$BUILD_SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:$BUILD_SA" --role="roles/storage.admin"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:$BUILD_SA" --role="roles/artifactregistry.writer"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:$BUILD_SA" --role="roles/logging.logWriter"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:$BUILD_SA" --role="roles/run.builder"
```

Tambien asegura APIs habilitadas:

```powershell
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

## 2. Build y deploy del OCR API

Si el repo `ocr-trial` ya existe, no lo vuelvas a crear.

Build:

```powershell
gcloud builds submit --tag us-central1-docker.pkg.dev/ocr1-491302/ocr-trial/ocr-api:latest .\services\ocr-api
```

Opcional: verificar imagen

```powershell
gcloud artifacts docker images list us-central1-docker.pkg.dev/ocr1-491302/ocr-trial
```

Deploy:

```powershell
gcloud run deploy ocr-api-trial --image us-central1-docker.pkg.dev/ocr1-491302/ocr-trial/ocr-api:latest --region us-central1 --allow-unauthenticated --set-env-vars OCR_API_KEY=internal-ocr-token,OCR_VISUAL_ENGINE=rapidocr,OCR_STRUCTURED_NORMALIZER_MODE=auto
```

Cuando termine, guarda la URL del servicio, por ejemplo:

```text
https://ocr-api-trial-xxxxx-uc.a.run.app
```

## 3. Configurar Firebase App Hosting para `apps/web`

En Firebase Console:

1. Abre el proyecto `OCR1`
2. Entra a **App Hosting**
3. Conecta el repo `https://github.com/insigne123/OCR.git`
4. Selecciona la rama que quieras desplegar
5. Define el root app directory como `apps/web`

Variables de entorno de App Hosting:

```text
OCR_API_URL=https://<TU_CLOUD_RUN_URL>
OCR_API_KEY=internal-ocr-token
NEXT_PUBLIC_SUPABASE_URL=<tu-supabase-url>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<tu-supabase-anon-key>
SUPABASE_SERVICE_ROLE_KEY=<tu-supabase-service-role-key>
SUPABASE_STORAGE_BUCKET=documents
NEXT_PUBLIC_SITE_URL=https://<tu-app-hosting-url>
OCR_PUBLIC_ALLOW_DEV_AUTH=false
OCR_TRIAL_API_KEYS=[{"id":"trial-grupoexpro","name":"GrupoExpro Trial","tenantId":"trial-grupoexpro","apiKey":"QpQSZxS2s8oPQOsR5CmTNA2rsBRouVs4DWYKlkflPso","documentLimit":50,"expiresAt":"2026-05-31T23:59:59Z","allowCallbacks":false,"forceProcessingMode":"sync","accessMode":"trial"}]
```

## 4. Validacion post deploy

Health:

```powershell
curl https://<WEB_URL>/api/public/trial/v1/health
```

Uso:

```powershell
curl https://<WEB_URL>/api/public/trial/v1/usage -H "x-api-key: QpQSZxS2s8oPQOsR5CmTNA2rsBRouVs4DWYKlkflPso"
```

Submission de prueba:

```powershell
curl -X POST https://<WEB_URL>/api/public/trial/v1/submissions -H "x-api-key: QpQSZxS2s8oPQOsR5CmTNA2rsBRouVs4DWYKlkflPso" -F "file=@./test-data/AFP.pdf" -F "document_family=certificate" -F "country=CL"
```

Resultado:

```powershell
curl https://<WEB_URL>/api/public/trial/v1/submissions/<SUBMISSION_ID>/result -H "x-api-key: QpQSZxS2s8oPQOsR5CmTNA2rsBRouVs4DWYKlkflPso"
```

## 5. Que compartir con GrupoExpro

- Base URL trial: `https://<WEB_URL>/api/public/trial/v1`
- Token: `QpQSZxS2s8oPQOsR5CmTNA2rsBRouVs4DWYKlkflPso`
- Limite: `50 documentos`
- Fecha de expiracion: `2026-05-31T23:59:59Z`
