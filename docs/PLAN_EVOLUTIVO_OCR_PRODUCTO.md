# Plan Evolutivo de Implementacion - OCR Platform

## 1. Proposito de este archivo

Este archivo existe para que el equipo siga un modelo evolutivo de construccion sin perder la vision original completa del producto.

La referencia estrategica principal sigue siendo `Documento sin título (10).txt`, donde se define el producto objetivo como una plataforma de Intelligent Document Processing (IDP) lista para produccion, con:

- preprocesado serio,
- split/classify,
- extractores por familia y pais,
- normalizacion estructurada con LLM,
- validacion deterministica,
- decision engine,
- review humana,
- export,
- learning loop,
- seguridad PII-first,
- observabilidad y operacion productiva.

Este roadmap no reemplaza el plan original: lo aterriza por fases para que podamos construir valor real desde el repositorio actual.

## 2. Vision original completa que no debemos olvidar

El producto final sigue siendo:

1. aplicacion web en Next.js,
2. backend principal en FastAPI,
3. procesamiento documental con preproceso self-hosted,
4. clasificacion y splitting documental,
5. extraccion por familia documental,
6. normalizacion final con OpenAI Structured Outputs,
7. review console propia,
8. motor de reglas propio,
9. multi-tenant con RBAC y auditoria,
10. exports y learning loop,
11. engine abstraction para proveedores cloud/enterprise.

### Objetivo GA recomendado por el documento original

- Google Document AI + OpenAI + preprocesado self-hosted.

### Objetivo enterprise recomendado por el documento original

- misma app,
- mismo backend,
- mismo modelo de datos,
- adapter para Azure Document Intelligence containers.

## 3. Principios de implementacion

### 3.1 Modelo evolutivo

No implementaremos primero el stack mas pesado posible. Implementaremos una base que funcione en el repo actual, pero cada fase debe dejar contratos listos para evolucionar a la arquitectura objetivo.

### 3.2 Regla de oro

Todo lo que hagamos en MVP debe servir para:

- no romper la futura integracion con Google/Azure,
- no perder provenance por campo,
- no bloquear multi-tenant,
- no impedir auditabilidad,
- no obligarnos a reescribir la UI de review.

### 3.3 Lo que no se negocia

- provenance por campo,
- review humana integrada,
- decision engine,
- JSON canonico,
- seguridad PII-first,
- engine abstraction.

### 3.4 Adaptacion API-first

Aunque la vision original considera una aplicacion web completa, la interfaz principal del producto pasa a ser un endpoint OCR/IDP que recibe un documento o imagen y devuelve JSON canónico.

La UI queda como:

- playground de pruebas,
- consola interna de soporte/review,
- monitor de jobs y calidad.

Esto no elimina el plan original; solo cambia la prioridad de entrega para que el producto principal sea integrable por terceros desde el inicio.

## 4. Estado actual del repositorio

Hoy el repositorio ya tiene:

- monorepo con `apps/web`, `services/ocr-api`, `packages/shared`,
- app real con shell profesional,
- upload local,
- detalle de documento,
- HTML report preview,
- pipeline mock,
- esquema SQL inicial,
- primeras rutas de review y reportes,
- consola inicial de review humana,
- feed de jobs,
- capa de repositorio preparada para `local` o `supabase`,
- cola inicial de procesamiento con runner manual desde la UI de Jobs,
- FastAPI con extraccion de texto embebido para PDF, normalizacion heuristica y fallback opcional a OpenAI Structured Outputs.
- autenticacion Supabase, preview de documento original y base de RLS/tenant membership lista para aplicar en SQL.

Todavia faltan las piezas productivas centrales:

- auth real,
- storage real,
- jobs asincronos,
- OCR real,
- preprocess,
- split/classify,
- validacion por reglas,
- review console completa con evidencia visual,
- observabilidad,
- hardening,
- testing serio,
- integrations cloud.

## 5. Fases evolutivas de implementacion

## Fase 0 - Contratos y direccion tecnica

### Objetivo

Congelar los contratos canónicos antes de seguir agregando features.

### Entregables

- schema compartido de `DocumentRecord`, `ExtractedField`, `ValidationIssue`, `ReviewSession`, `ReportSection`,
- definicion de `DocumentEngine`, `NormalizerEngine`, `RulePack`,
- decision de runtime inicial: `Supabase + FastAPI + OpenAI + OCR self-hosted`,
- decision de arquitectura evolutiva: jobs desacoplados y adapters.

### Estado

- parcialmente implementado.

## Fase 1 - Foundation productizable

### Objetivo

Sacar la app del modo prototipo puro y dejar la base lista para datos reales.

### Alcance

- integrar Supabase Auth,
- integrar Supabase Postgres,
- integrar Supabase Storage,
- migrar persistencia local a repository pattern,
- agregar `tenant_id`, `source_hash`, `latest_job`, `review_sessions`, `extracted_fields`,
- preparar signed URLs y buckets privados,
- crear migraciones SQL alineadas al modelo canónico.

### Criterio de salida

- la app puede guardar y leer documentos desde infraestructura real,
- el modelo de datos soporta provenance y review.

## Fase 2 - Ingesta y orquestacion asincrona

### Objetivo

Desacoplar el procesamiento del request HTTP.

### Alcance

- `job_id` por documento,
- estado de cola,
- reintentos,
- idempotencia,
- errores persistidos,
- DLQ simple,
- colas iniciales sobre Postgres/Redis,
- preparar evolucion a Temporal/Kafka.

### Criterio de salida

- upload no bloquea el navegador,
- el pipeline puede correr por etapas,
- cada documento conserva trazabilidad por job.

## Fase 3 - Render, quality scoring y preprocess

### Objetivo

Transformar el archivo original en un input limpio para OCR y clasificación.

### Alcance

- render por página de PDF,
- detección de texto embebido,
- quality scoring: blur, glare, crop, resolución, orientación,
- preprocess visual: deskew, orientation correction, denoise, contraste, page boundary detection,
- persistencia de páginas derivadas.

### Criterio de salida

- cada documento procesado tiene páginas derivadas y quality metadata.

## Fase 4 - OCR y extracción MVP real

### Objetivo

Reemplazar el pipeline mock por extracción real.

### Alcance

- PaddleOCR como OCR principal inicial,
- docTR como fallback,
- wrappers por engine,
- layout extraction básica,
- detección de tablas/pares clave,
- extracción inicial para:
  - certificados/comprobantes,
  - identidad.

### Criterio de salida

- tenemos campos reales extraidos con confidence y provenance.

## Fase 5 - Normalizacion estructurada con OpenAI

### Objetivo

Convertir salida OCR cruda en JSON canónico estricto.

### Alcance

- OpenAI Responses API,
- Structured Outputs con JSON Schema,
- normalización de fechas, moneda, nombres, identificadores,
- warnings semánticos,
- marcación de campos inferidos,
- fallback seguro cuando el modelo no puede validar.

### Criterio de salida

- la app entrega JSON programáticamente consistente y verificable.

## Fase 6 - Rule engine y decision engine

### Objetivo

Determinar automáticamente qué documentos pasan, cuáles requieren warning y cuáles deben ir a review.

### Alcance

- reglas determinísticas por familia documental,
- reglas iniciales para identidad y certificados,
- score por campo,
- score global,
- umbrales por flujo,
- decisiones:
  - `auto_accept`,
  - `accept_with_warning`,
  - `human_review`,
  - `reject`.

### Criterio de salida

- el sistema toma decisiones operativas basadas en evidencia y reglas.

## Fase 7 - Review console productiva

### Objetivo

Construir el módulo central de human-in-the-loop.

### Alcance

- cola de revisión,
- vista de documento con imagen/página,
- bounding boxes,
- OCR crudo,
- valor normalizado,
- issue linked por campo,
- edición con motivo,
- historial de cambios,
- auditoría por usuario,
- cierre de sesión de revisión.

### Criterio de salida

- un analista puede corregir y cerrar un caso sin salir de la app.

## Fase 8 - Reportes y exports

### Objetivo

Convertir el documento procesado en salidas operativas y de integración.

### Alcance

- JSON canónico persistido,
- HTML template versionado,
- export CSV,
- webhook,
- API pull,
- integración futura ERP/CRM/KYC.

### Criterio de salida

- el resultado se puede consumir tanto visualmente como por sistemas externos.

## Fase 9 - Split/classify y country packs

### Objetivo

Escalar el producto a PDFs mixtos y variantes reales por país/familia.

### Alcance

- clasificación por `document_family`, `country`, `variant`, `risk_level`,
- PDFs mixtos,
- country packs para identidad,
- custom extractor por familia/pais,
- reglas por pack,
- ejemplos etiquetados y tests por pack.

### Criterio de salida

- el sistema deja de depender de una sola plantilla documental.

## Fase 10 - Hardening productivo

### Objetivo

Preparar el sistema para clientes reales y operación sostenida.

### Alcance

- observabilidad por etapa y por campo,
- Sentry,
- OpenTelemetry,
- dashboards de auto-approval/review/precision,
- PII redaction,
- retention policies,
- auditoría inmutable,
- tests unitarios/integración/E2E,
- golden set,
- release strategy,
- CI/CD.

### Criterio de salida

- el producto cumple con una definición seria de producción.

## Fase 11 - Engines cloud y enterprise path

### Objetivo

Conectar los motores recomendados por el documento estratégico.

### Alcance

- adapter Google Document AI:
  - splitter/classifier,
  - invoice parser,
  - custom extractor,
- adapter Azure Document Intelligence containers,
- engine selection por tenant o por flujo,
- comparación de precisión/costo/latencia.

### Criterio de salida

- podemos cambiar proveedor sin reescribir la app.

## 6. Orden de implementacion recomendado desde el repo actual

1. cerrar contratos y migraciones,
2. migrar persistencia a modelo preparado para Supabase,
3. completar review workflow base,
4. introducir jobs asincronos,
5. integrar OCR real,
6. integrar OpenAI Structured Outputs,
7. agregar reglas y decision engine,
8. completar reportes/export,
9. agregar split/classify y country packs,
10. hardening productivo,
11. adapters cloud.

## 7. Definicion de exito por etapa

### Exito del MVP evolutivo

- documentos reales procesados,
- provenance por campo,
- HTML y JSON canónicos,
- review humana operativa,
- reglas iniciales productivas,
- auth y multi-tenant básico,
- app lista para sustituir engine local por Google/Azure.

### Exito del producto completo

- arquitectura desacoplada,
- engine abstraction real,
- split/classify productivo,
- extractores por familia y país,
- auditoría y compliance,
- observabilidad por campo,
- golden set y regresión,
- despliegue listo para producción.

## 8. Regla final

Si en algún punto una implementación rápida compromete alguno de estos puntos:

- provenance,
- review humana,
- engine abstraction,
- seguridad PII-first,
- contratos canónicos,

entonces esa implementación no debe considerarse aceptable, aunque acelere el desarrollo.

Este archivo debe mantenerse vivo y actualizarse al final de cada bloque importante de implementación.
