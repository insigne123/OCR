# OCR API

FastAPI scaffold for document ingestion, preprocessing, extraction and normalization.

## Run

```bash
pip install -e services/ocr-api
python -m uvicorn app.main:app --reload --app-dir services/ocr-api
```

Optional local visual OCR with RapidOCR is available from a Python 3.12 environment:

```bash
pip install -e "services/ocr-api[rapidocr]"
```

Additional optional engines:

```bash
pip install -e "services/ocr-api[paddleocr]"
pip install -e "services/ocr-api[doctr]"
pip install -e "services/ocr-api[azure]"
pip install -e "services/ocr-api[google]"
```

`rapidocr-onnxruntime` does not currently publish Python 3.13-compatible distributions, so the base install keeps local OCR optional.

## Endpoints

- `GET /v1/health`
- `POST /v1/process`
- `POST /v1/preprocess`
- `POST /v1/split`
- `POST /v1/extract`
- `POST /v1/normalize`
- `POST /v1/validate`

The current implementation now supports:

- PDF embedded-text extraction via `pypdf`
- per-page preprocessing metadata with rendered page resolution, blur/glare estimation and quality scoring
- advanced mobile rescue profiles with denoise, CLAHE, adaptive binarization and aggressive low-quality fallback gated by capture quality
- selectable OCR via `OCR_VISUAL_ENGINE=rapidocr|paddleocr|doctr|azure-document-intelligence|google-documentai|auto` (`rapidocr` by default)
- adaptive premium gating via `OCR_PREMIUM_ROUTING_MODE=adaptive|force|off` (`adaptive` recomendado para ahorrar sin bajar cobertura)
- fallback premium opcional via `OCR_ENABLE_VISUAL_FALLBACK=true` y `OCR_PREMIUM_FALLBACK_ENGINE=google-documentai`
- conservative structured normalization via `OCR_STRUCTURED_NORMALIZER_MODE=heuristic|openai|auto` (`auto` by default to use OpenAI solo cuando la heuristica quede corta)
- selective full-model OpenAI via `OCR_OPENAI_FULL_MODEL_FAMILIES` y `OCR_OPENAI_FULL_MODEL_PACKS` (por defecto solo `passport` usa `gpt-4.1`)
- field adjudication model override via `OCR_FIELD_ADJUDICATION_MODEL` (`gpt-4.1-mini` recomendado)
- lightweight layout extraction for key-value candidates and table-like rows in `/v1/extract`
- heuristic normalization for certificate and identity flows
- optional OpenAI structured normalization when `OPENAI_API_KEY` is configured
- unsupported-document fallback when the file does not match a supported pack or extractor

## API-first contract

`POST /v1/process` accepts multipart form data:

- `file`
- `document_family`
- `country`
- `response_mode` = `json` or `full`

If `OCR_API_KEY` is configured, send:

```bash
-H "x-api-key: <OCR_API_KEY>"
```

Default recommendation:

- external integrations -> `response_mode=json`
- internal control plane -> `response_mode=full`
