import time
import os
from uuid import uuid4

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware

from app.core_env import load_runtime_env
from app.core.telemetry import log_event
from app.routers.pipeline import router as pipeline_router
from app.services.visual_ocr import warm_visual_ocr_runtime


load_runtime_env()


def _resolve_cors_origins() -> tuple[list[str], bool]:
    raw = (os.getenv("OCR_API_CORS_ALLOW_ORIGINS") or "").strip()
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"], True

    origins = [value.strip() for value in raw.split(",") if value.strip()]
    if not origins:
        return ["http://localhost:3000", "http://127.0.0.1:3000"], True
    if origins == ["*"]:
        return origins, False
    return origins, True


cors_origins, cors_allow_credentials = _resolve_cors_origins()


app = FastAPI(
    title="OCR API",
    version="0.1.0",
    description="Document processing API for OCR, normalization, validation and report generation.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def telemetry_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log_event(
            "http_request_failed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            duration_ms=duration_ms,
        )
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["x-request-id"] = request_id
    log_event(
        "http_request_completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


@app.on_event("startup")
async def on_startup() -> None:
    warm_visual_ocr_runtime()
    log_event("service_startup", service="ocr-api")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    log_event("service_shutdown", service="ocr-api")

app.include_router(pipeline_router, prefix="/v1", tags=["pipeline"])
