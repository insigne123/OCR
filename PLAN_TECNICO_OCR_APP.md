# Plan Tecnico - Plataforma OCR y Reportes

## 1. Objetivo del producto

Construir una aplicacion web que:

1. reciba documentos PDF e imagenes,
2. ejecute preproceso y OCR,
3. extraiga campos estructurados,
4. normalice e interprete los datos con IA controlada,
5. valide consistencia documental,
6. genere reportes HTML/JSON como `reporte_ocr (5).html`,
7. envie a revision humana los casos dudosos.

La meta no es un "OCR perfecto", sino una plataforma de Intelligent Document Processing (IDP) con trazabilidad por campo, scores de confianza y human-in-the-loop.

## 2. Alcance inicial

### MVP v1

- Carga de PDF, JPG, PNG, TIFF y HEIF.
- OCR de documentos simples y semiestructurados.
- Extraccion de datos para 2 familias iniciales:
  - certificados/comprobantes previsionales o laborales,
  - documentos de identidad de un pais objetivo inicial.
- Normalizacion con OpenAI Structured Outputs.
- Validacion deterministica de reglas basicas.
- Generacion de reporte HTML y JSON canonico.
- Consola interna de revision humana.
- Persistencia de documentos, jobs, campos, issues y auditoria.

### Fase 2

- Split y clasificacion de PDFs mixtos.
- Multiples familias documentales por pais.
- Motor de reglas por pais/variant.
- Reentrenamiento con correcciones humanas.
- Adapter para Google Document AI y Azure Document Intelligence.
- Export via webhook, CSV y API externa.

## 3. Decisiones tecnicas principales

### Stack de aplicacion

- Frontend: Next.js + React + TypeScript.
- UI: Tailwind + shadcn/ui.
- Backend de procesamiento: Python + FastAPI.
- Base de datos y auth: Supabase (Postgres + Auth + Storage).
- IA: OpenAI Responses API / Structured Outputs.
- Reportes: HTML server-side + JSON canonico.
- Observabilidad inicial: logs estructurados + Sentry + metricas basicas.

### Herramientas de apoyo

- Firebase Studio: para prototipado rapido, iteracion UI y asistentes de desarrollo.
- Vercel: despliegue del frontend Next.js.
- GitHub Actions: CI, tests, lint y deploy.

### OCR y procesamiento documental

- Preproceso visual: OpenCV + PaddleOCR preprocessing.
- OCR principal MVP: PaddleOCR / docTR como motores locales.
- Normalizacion y interpretacion: OpenAI con schema estricto.
- Diseno extensible: interfaz `DocumentEngine` para enchufar engines cloud mas adelante.

## 4. Arquitectura propuesta

```text
Cliente Web (Next.js)
  -> API App
  -> Supabase Auth
  -> Upload de documento
  -> Supabase Storage
  -> Job Orchestrator
  -> OCR API (FastAPI)
     -> Render de paginas
     -> Quality scoring
     -> Preprocess
     -> OCR / extraction
     -> OpenAI normalizer
     -> Rule engine
     -> Decision engine
  -> Postgres (metadata + resultados)
  -> Report generator
  -> Review console
```

## 5. Repositorio y estructura recomendada

```text
OCR/
  apps/
    web/
      app/
      components/
      lib/
      features/
  services/
    ocr-api/
      app/
        api/
        core/
        services/
        engines/
        schemas/
        workers/
  packages/
    shared/
      src/
        types/
        schemas/
        report-template/
  infra/
    sql/
    github-actions/
    vercel/
  docs/
    adr/
    api/
```

## 6. Flujo funcional del documento

1. Upload del documento.
2. Generacion de `document_id`, `tenant_id`, hash SHA-256 y metadatos.
3. Render a paginas si el archivo es PDF.
4. Deteccion de texto embebido y calidad base.
5. Preproceso visual:
   - deskew,
   - orientation correction,
   - denoise,
   - contrast enhancement,
   - crop/page boundary detection.
6. OCR/extraccion cruda.
7. Normalizacion con OpenAI a JSON canonico.
8. Validaciones deterministicas por tipo documental.
9. Calculo de confianza global y por campo.
10. Decision engine:
    - auto_accept,
    - accept_with_warning,
    - human_review,
    - reject.
11. Generacion de reporte HTML/JSON.
12. Revision humana y auditoria.

## 7. Modelo de datos inicial

### Tablas principales

- `tenants`
- `users`
- `documents`
- `document_pages`
- `processing_jobs`
- `document_classifications`
- `extracted_fields`
- `validation_issues`
- `generated_reports`
- `review_sessions`
- `review_edits`
- `audit_logs`

### Campos clave por entidad

#### `documents`

- `id`
- `tenant_id`
- `source_filename`
- `mime_type`
- `storage_path`
- `sha256`
- `status`
- `document_family`
- `country`
- `variant`
- `global_confidence`
- `decision`
- `created_at`

#### `document_pages`

- `id`
- `document_id`
- `page_number`
- `image_path`
- `width`
- `height`
- `orientation`
- `quality_score`

#### `extracted_fields`

- `id`
- `document_id`
- `page_number`
- `section`
- `field_name`
- `raw_text`
- `normalized_value`
- `value_type`
- `confidence`
- `engine`
- `bbox`
- `evidence_span`
- `validation_status`
- `review_status`
- `is_inferred`

#### `validation_issues`

- `id`
- `document_id`
- `field_name`
- `issue_type`
- `severity`
- `message`
- `suggested_action`
- `created_at`

## 8. JSON canonico del resultado

```json
{
  "document": {
    "type": "certificado_cotizaciones",
    "issuer": "AFP ProVida S.A.",
    "holder_name": "...",
    "global_confidence": 0.85,
    "decision": "PARTIAL"
  },
  "sections": {
    "summary": [],
    "dates": [],
    "amounts": [],
    "identifiers": [],
    "addresses": [],
    "contacts": [],
    "names": [],
    "others": []
  },
  "issues": [],
  "assumptions": [],
  "human_summary": "..."
}
```

## 9. Formato del reporte HTML

El generador de reportes debe producir una salida consistente con el ejemplo actual:

- Header con titulo, confianza global y decision.
- Seccion `Resumen`.
- Tablas por dominio de datos: fechas, montos, identificadores, contactos, etc.
- Seccion `Issues` con tipo, campo, mensaje y accion sugerida.
- Seccion `Asunciones`.
- Seccion `Resumen humano`.

Se recomienda generar el HTML a partir de un template unico versionado y alimentado por el JSON canonico.

## 10. API inicial

### Frontend / App API

- `POST /api/documents/upload`
- `GET /api/documents/:id`
- `GET /api/documents/:id/report`
- `GET /api/documents/:id/report.html`
- `GET /api/documents/:id/issues`
- `POST /api/documents/:id/review`
- `GET /api/jobs/:id`

### OCR API (FastAPI)

- `POST /v1/process`
- `POST /v1/preprocess`
- `POST /v1/extract`
- `POST /v1/normalize`
- `POST /v1/validate`
- `GET /v1/health`

## 11. Modulos de backend

### Ingestion service

- valida tipo de archivo,
- calcula hash,
- almacena original,
- crea job asincrono.

### Render service

- separa paginas,
- detecta texto embebido,
- genera imagenes derivadas.

### Quality scoring service

- blur,
- glare,
- resolucion minima,
- recorte,
- orientacion.

### Preprocess service

- deskew,
- denoise,
- contrast,
- rotation correction.

### OCR engine service

- wrapper para PaddleOCR,
- fallback con docTR,
- adapter listo para Google/Azure.

### Normalizer service

- prompt controlado,
- JSON Schema estricto,
- marcacion de inferidos,
- warnings semanticos.

### Rule engine

- validaciones de fecha,
- validaciones de identidad,
- checks de sumatoria,
- checks por pais y tipo.

### Report generator

- produce JSON final,
- renderiza HTML,
- guarda snapshot versionado.

## 12. Consola de revision humana

La UI de revision debe mostrar:

- imagen original o pagina,
- cajas o zonas detectadas,
- OCR crudo,
- valor normalizado,
- confianza por campo,
- regla que fallo,
- accion sugerida,
- historial de correcciones.

## 13. Seguridad y compliance

- autenticacion por Supabase Auth,
- aislamiento por tenant,
- buckets privados,
- URLs firmadas temporales,
- cifrado en reposo y en transito,
- no loggear PII completa,
- auditoria por accion y por correccion,
- retencion configurable por cliente.

## 14. Observabilidad minima

- logs estructurados por `document_id` y `job_id`,
- metricas de tiempo por etapa,
- errores por engine,
- tasa de autoaceptacion,
- tasa de revision,
- precision manual estimada por campo,
- capturas de excepcion en Sentry.

## 15. Estrategia de desarrollo por fases

### Fase 0 - Foundation

- crear monorepo,
- configurar Next.js, FastAPI y Supabase,
- definir schemas compartidos,
- preparar buckets y tablas base.

### Fase 1 - Upload y pipeline base

- upload de documentos,
- render de paginas,
- job queue simple,
- estado de procesamiento.

### Fase 2 - OCR y normalizacion

- integrar PaddleOCR/docTR,
- integrar OpenAI Structured Outputs,
- persistir campos y confidencias.

### Fase 3 - Reportes

- construir JSON canonico,
- generar HTML igual al modelo objetivo,
- vista de documento procesado en la app.

### Fase 4 - Validacion y review

- implementar rule engine,
- issues y decision engine,
- consola de revision humana.

### Fase 5 - Hardening

- tests E2E,
- observabilidad,
- hardening de seguridad,
- optimizacion de performance,
- adapters externos.

## 16. Testing

### Backend

- unit tests de normalizacion,
- tests de validadores,
- tests de adapters OCR,
- golden set de documentos.

### Frontend

- tests de componentes,
- tests de flujo de upload,
- tests de vista de reporte,
- tests de review console.

### E2E

- documento bueno -> auto_accept,
- documento incompleto -> partial / review,
- documento con baja calidad -> reject,
- correccion humana -> persistencia y auditoria.

## 17. Definicion de listo para MVP

- upload funcional de PDF e imagen,
- pipeline OCR end-to-end estable,
- JSON canonico persistido,
- HTML generado automaticamente,
- reglas basicas activas,
- revision humana disponible,
- trazabilidad por campo,
- auth y multi-tenant basico,
- logs y monitoreo inicial.

## 18. Siguiente recomendacion inmediata

Orden recomendado de ejecucion:

1. crear el monorepo base,
2. modelar la base de datos en Supabase,
3. implementar upload y storage,
4. implementar pipeline OCR minimo,
5. integrar OpenAI structured normalization,
6. generar el primer reporte HTML desde datos reales,
7. construir la consola de revision.
