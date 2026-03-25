from __future__ import annotations

import base64
import json
import os
from typing import Any, cast

from openai import OpenAI

from app.core.feature_flags import feature_enabled
from app.schemas import NormalizedDocument


PACK_SPECIALIZATIONS = {
    "identity-cl-front": (
        "Estas analizando una cedula de identidad chilena por el frente. "
        "Extrae con especial cuidado RUN, nombres, apellidos, numero de documento, fecha de nacimiento, fecha de emision, fecha de vencimiento, sexo, nacionalidad y MRZ. "
        "No mezcles RUN con numero de documento si aparecen en campos distintos."
    ),
    "identity-cl-back": (
        "Estas analizando una cedula de identidad chilena por el dorso. "
        "Prioriza lugar de nacimiento, numero de documento, RUN, fechas codificadas en MRZ y nombres si aparecen en la zona legible por maquina. "
        "Si el archivo no contiene frente, no inventes direccion ni campos no visibles."
    ),
    "identity-pe-front": (
        "Estas analizando un DNI peruano por el frente. "
        "Extrae DNI de 8 digitos, nombres, apellidos, sexo, nacionalidad, fecha de nacimiento y fechas documentales visibles."
    ),
    "identity-pe-back": (
        "Estas analizando un DNI peruano por el dorso. "
        "Busca domicilio, estado civil, grado de instruccion, donacion de organos y restricciones."
    ),
    "identity-co-front": (
        "Estas analizando una cedula colombiana por el frente. "
        "Extrae numero de cedula o NUIP, nombres, apellidos, sexo y fecha de nacimiento si es visible."
    ),
    "identity-co-back": (
        "Estas analizando una cedula colombiana por el dorso. "
        "Busca lugar de nacimiento, estatura, grupo sanguineo y lugar o fecha de expedicion."
    ),
    "passport-generic": (
        "Estas analizando un pasaporte. "
        "Prioriza holder_name, document_number, birth_date, expiry_date, issue_date, nationality, sex, place_of_birth y MRZ completa en formato ICAO si es visible."
    ),
    "driver-license-generic": (
        "Estas analizando una licencia de conducir. "
        "Prioriza holder_name, document_number, birth_date, issue_date, expiry_date, categorias, autoridad y direccion."
    ),
    "certificate-cl-previsional": (
        "Estas analizando un certificado previsional chileno tipo AFP. "
        "Prioriza titular, RUT del afiliado, numero de certificado, fecha de emision, cuenta, emisor y la tabla de cotizaciones con periodo, renta imponible, fondo de pensiones, codigo, empleador, RUT empleador y fecha de pago. "
        "No confundas el RUT del afiliado con el RUT del empleador ni el nombre del certificado con el nombre del titular."
    ),
    "certificate-generic": (
        "Estas analizando un certificado o comprobante. "
        "Prioriza titular, emisor, identificadores, cuentas, periodos, fechas, montos y filas tabulares relevantes."
    ),
}

FAMILY_SPECIALIZATIONS = {
    "identity": "El documento es de identidad; prioriza identificadores, titular y fechas documentales.",
    "passport": "El documento es un pasaporte; prioriza zona MRZ y datos biograficos.",
    "driver_license": "El documento es una licencia de conducir; prioriza titular, numero, vigencia y categorias.",
    "certificate": "El documento es un certificado; prioriza titular, emisor, fechas, montos e identificadores.",
}

DEFAULT_FULL_MODEL_FAMILIES = {"passport"}


def has_openai_config() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _client() -> OpenAI:
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _parse_csv_env(name: str) -> set[str]:
    return {item.strip().lower() for item in (os.getenv(name, "") or "").split(",") if item.strip()}


def _should_use_full_model(document_family: str, pack_id: str | None = None) -> bool:
    configured_families = _parse_csv_env("OCR_OPENAI_FULL_MODEL_FAMILIES")
    configured_packs = _parse_csv_env("OCR_OPENAI_FULL_MODEL_PACKS")
    if configured_families or configured_packs:
        return document_family.lower() in configured_families or (pack_id or "").lower() in configured_packs
    return document_family.lower() in DEFAULT_FULL_MODEL_FAMILIES


def _model(document_family: str, pack_id: str | None = None) -> str:
    configured = os.getenv("OPENAI_MODEL")
    if configured:
        return configured
    if not feature_enabled("pack_prompt_specialization"):
        return "gpt-4.1-mini"
    if _should_use_full_model(document_family, pack_id):
        return "gpt-4.1"
    return "gpt-4.1-mini"


def _strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    def transform(node: Any) -> Any:
        if isinstance(node, dict):
            transformed = {key: transform(value) for key, value in node.items()}
            node_type = transformed.get("type")
            if node_type == "object":
                transformed.setdefault("additionalProperties", False)
                properties = cast(dict[str, Any], transformed.get("properties") or {})
                transformed["properties"] = {key: transform(value) for key, value in properties.items()}
                transformed["required"] = list(cast(dict[str, Any], transformed["properties"]).keys())
            if "anyOf" in transformed:
                transformed["anyOf"] = [transform(value) for value in transformed["anyOf"]]
            if "items" in transformed:
                transformed["items"] = transform(transformed["items"])
            return transformed
        if isinstance(node, list):
            return [transform(value) for value in node]
        return node

    return cast(dict[str, Any], transform(schema))


def _variant_line(variant: str | None) -> str:
    return f"Variante detectada: {variant}\n" if variant else ""


def _pack_context(document_family: str, pack_id: str | None, document_side: str | None, visual: bool = False) -> str:
    specialization = (
        (PACK_SPECIALIZATIONS.get(pack_id or "") or FAMILY_SPECIALIZATIONS.get(document_family, ""))
        if feature_enabled("pack_prompt_specialization")
        else FAMILY_SPECIALIZATIONS.get(document_family, "")
    )
    side_context = f"Lado esperado del documento: {document_side}. " if document_side else ""
    visual_context = (
        "Trabaja directamente sobre el contenido visual y recupera campos aunque el OCR textual previo haya sido incompleto. "
        if visual
        else "Trabaja sobre texto OCR y corrige fragmentacion o labels rotos sin inventar contenido. "
    )
    return (
        f"{specialization} {side_context}{visual_context}"
        "Si un campo no es visible o no es confiable, devuelve null o '-' segun corresponda. "
        "No inventes, no combines candidatos incompatibles y conserva formato documental cuando aporte valor operacional."
    ).strip()


def normalize_text_with_openai(
    document_family: str,
    country: str,
    filename: str,
    source_text: str,
    variant: str | None = None,
    pack_id: str | None = None,
    document_side: str | None = None,
) -> NormalizedDocument:
    client = _client()
    schema = _strict_json_schema(NormalizedDocument.model_json_schema())
    request_input: list[Any] = [
        {
            "role": "system",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Eres un normalizador documental. "
                        f"{_pack_context(document_family, pack_id, document_side)} "
                        "Devuelve una estructura util para OCR operational reporting."
                    ),
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        f"Documento: {filename}\n"
                        f"Familia declarada: {document_family}\n"
                        f"Pais: {country}\n"
                        f"Pack: {pack_id or '-'}\n"
                        f"Lado documental: {document_side or '-'}\n"
                        f"{_variant_line(variant)}\n"
                        f"Texto extraido:\n{source_text[:18000]}"
                    ),
                }
            ],
        },
    ]

    response = client.responses.create(
        model=_model(document_family, pack_id),
        input=cast(Any, request_input),
        text={
            "format": {
                "type": "json_schema",
                "name": "normalized_document",
                "schema": schema,
                "strict": True,
            }
        },
    )

    return NormalizedDocument.model_validate(json.loads(response.output_text))


def normalize_image_with_openai(
    document_family: str,
    country: str,
    filename: str,
    mime_type: str,
    file_bytes: bytes,
    variant: str | None = None,
    pack_id: str | None = None,
    document_side: str | None = None,
) -> NormalizedDocument:
    client = _client()
    schema = _strict_json_schema(NormalizedDocument.model_json_schema())
    image_data = base64.b64encode(file_bytes).decode("utf-8")
    request_input: list[Any] = [
        {
            "role": "system",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Extrae y normaliza el documento visual. "
                        f"{_pack_context(document_family, pack_id, document_side, visual=True)}"
                    ),
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        f"Documento: {filename}\n"
                        f"Familia declarada: {document_family}\n"
                        f"Pais: {country}\n"
                        f"Pack: {pack_id or '-'}\n"
                        f"Lado documental: {document_side or '-'}\n"
                        f"{_variant_line(variant)}"
                    ),
                },
                {
                    "type": "input_image",
                    "image_url": f"data:{mime_type};base64,{image_data}",
                },
            ],
        },
    ]

    response = client.responses.create(
        model=_model(document_family, pack_id),
        input=cast(Any, request_input),
        text={
            "format": {
                "type": "json_schema",
                "name": "normalized_document_from_image",
                "schema": schema,
                "strict": True,
            }
        },
    )

    return NormalizedDocument.model_validate(json.loads(response.output_text))


def normalize_rendered_pages_with_openai(
    document_family: str,
    country: str,
    filename: str,
    images: list[bytes],
    variant: str | None = None,
    pack_id: str | None = None,
    document_side: str | None = None,
) -> NormalizedDocument:
    client = _client()
    schema = _strict_json_schema(NormalizedDocument.model_json_schema())

    content: list[Any] = [
        {
            "type": "input_text",
            "text": (
                f"Documento: {filename}\n"
                f"Familia declarada: {document_family}\n"
                f"Pais: {country}\n"
                f"Pack: {pack_id or '-'}\n"
                f"Lado documental: {document_side or '-'}\n"
                f"{_variant_line(variant)}"
            ),
        }
    ]

    for image_bytes in images[:3]:
        image_data = base64.b64encode(image_bytes).decode("utf-8")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{image_data}",
            }
        )

    request_input: list[Any] = [
        {
            "role": "system",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Extrae y normaliza un documento renderizado desde PDF escaneado. "
                        f"{_pack_context(document_family, pack_id, document_side, visual=True)}"
                    ),
                }
            ],
        },
        {
            "role": "user",
            "content": content,
        },
    ]

    response = client.responses.create(
        model=_model(document_family, pack_id),
        input=cast(Any, request_input),
        text={
            "format": {
                "type": "json_schema",
                "name": "normalized_document_from_pdf_images",
                "schema": schema,
                "strict": True,
            }
        },
    )

    return NormalizedDocument.model_validate(json.loads(response.output_text))
