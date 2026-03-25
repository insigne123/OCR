from __future__ import annotations

from dataclasses import dataclass

AUTO_FAMILY_VALUES = {"", "auto", "unclassified"}
AUTO_COUNTRY_VALUES = {"", "AUTO", "XX"}


@dataclass(frozen=True)
class PackFieldDefinition:
    field_key: str
    label: str
    aliases: tuple[str, ...] = ()
    required: bool = False
    critical: bool = False


@dataclass(frozen=True)
class PackDecisionThresholds:
    auto_accept_confidence: float = 0.94
    auto_accept_agreement: float = 0.85
    accept_with_warning_confidence: float = 0.86
    review_agreement: float = 0.55


@dataclass(frozen=True)
class DocumentPack:
    pack_id: str
    document_family: str
    country: str
    variant: str
    version: str
    label: str
    document_side: str | None = None
    supported: bool = True
    classification_keywords: tuple[str, ...] = ()
    expected_fields: tuple[PackFieldDefinition, ...] = ()
    decision_thresholds: PackDecisionThresholds = PackDecisionThresholds()
    min_back_fields: int = 0


DOCUMENT_PACKS: tuple[DocumentPack, ...] = (
    DocumentPack(
        pack_id="identity-generic",
        document_family="identity",
        country="XX",
        variant="identity-text",
        version="2026-03",
        label="Documento de identidad generico",
        supported=True,
        classification_keywords=("CEDULA DE IDENTIDAD", "DOCUMENTO NACIONAL DE IDENTIDAD", "CEDULA DE CIUDADANIA"),
    ),
    DocumentPack(
        pack_id="certificate-generic",
        document_family="certificate",
        country="XX",
        variant="text-certificate",
        version="2026-03",
        label="Certificado generico",
        supported=True,
        classification_keywords=("CERTIFICADO", "CONSTANCIA LABORAL", "CERTIFICACION LABORAL", "COTIZACIONES"),
    ),
    DocumentPack(
        pack_id="identity-cl-front",
        document_family="identity",
        country="CL",
        variant="identity-cl-front-text",
        version="2026-03",
        label="Cedula Chile frente",
        document_side="front",
        classification_keywords=(
            "REPUBLICA DE CHILE",
            "REGISTRO CIVIL E IDENTIFICACION",
            "CEDULA DE IDENTIDAD",
            "RUN",
            "NOMBRES",
            "APELLIDOS",
        ),
        expected_fields=(
            PackFieldDefinition("holder_name", "Titular", aliases=("nombre-completo", "titular", "nombres", "apellidos"), required=True, critical=True),
            PackFieldDefinition("document_number", "Numero de documento", aliases=("numero-de-documento", "numero", "documento", "numero-documento"), required=True, critical=True),
            PackFieldDefinition("run", "RUN", aliases=("run",), required=True, critical=True),
            PackFieldDefinition("birth_date", "Fecha de nacimiento", aliases=("fecha-de-nacimiento",), required=True),
            PackFieldDefinition("expiry_date", "Fecha de vencimiento", aliases=("fecha-de-vencimiento",), required=True),
            PackFieldDefinition("mrz", "MRZ", aliases=("mrz",), required=False),
        ),
        decision_thresholds=PackDecisionThresholds(auto_accept_confidence=0.94, auto_accept_agreement=0.76, accept_with_warning_confidence=0.8, review_agreement=0.42),
    ),
    DocumentPack(
        pack_id="identity-cl-back",
        document_family="identity",
        country="CL",
        variant="identity-cl-back-text",
        version="2026-03",
        label="Cedula Chile dorso",
        document_side="back",
        classification_keywords=(
            "NACIO EN",
            "NACIONALIDAD",
            "INCHL",
            "I<CHL",
            "DOMICILIO",
            "COMUNA",
            "PROFESION",
            "CIRCUNSCRIPCION",
            "HUELLA",
        ),
        expected_fields=(
            PackFieldDefinition("holder_name", "Titular", aliases=("nombre-completo", "titular", "nombres", "apellidos"), required=True, critical=True),
            PackFieldDefinition("document_number", "Numero de documento", aliases=("numero-de-documento", "numero", "documento", "numero-documento"), required=True, critical=True),
            PackFieldDefinition("run", "RUN", aliases=("run",), required=False),
            PackFieldDefinition("birth_place", "Lugar de nacimiento", aliases=("lugar-de-nacimiento", "nacio-en"), required=True, critical=True),
            PackFieldDefinition("address", "Domicilio", aliases=("domicilio",), required=False),
            PackFieldDefinition("commune", "Comuna", aliases=("comuna",), required=False),
            PackFieldDefinition("profession", "Profesion", aliases=("profesion",), required=False),
            PackFieldDefinition("electoral_circ", "Circunscripcion", aliases=("circunscripcion",), required=False),
            PackFieldDefinition("mrz", "MRZ", aliases=("mrz",), required=False),
        ),
        decision_thresholds=PackDecisionThresholds(auto_accept_confidence=0.93, auto_accept_agreement=0.76, accept_with_warning_confidence=0.84, review_agreement=0.5),
        min_back_fields=1,
    ),
    DocumentPack(
        pack_id="identity-pe-front",
        document_family="identity",
        country="PE",
        variant="identity-pe-front-text",
        version="2026-03",
        label="DNI Peru frente",
        document_side="front",
        classification_keywords=(
            "REPUBLICA DEL PERU",
            "DOCUMENTO NACIONAL DE IDENTIDAD",
            "DNI",
            "APELLIDOS",
            "NOMBRES",
        ),
        expected_fields=(
            PackFieldDefinition("holder_name", "Titular", aliases=("nombre-completo", "titular", "nombres", "apellido", "apellidos", "given-name", "surname"), required=True, critical=True),
            PackFieldDefinition("document_number", "DNI", aliases=("numero-de-documento", "numero", "documento", "dni", "numero-de-identidad", "document-number"), required=True, critical=True),
            PackFieldDefinition("birth_date", "Fecha de nacimiento", aliases=("fecha-de-nacimiento", "date-of-birth"), required=True),
            PackFieldDefinition("issue_date", "Fecha de emision", aliases=("fecha-de-emision", "fecha-de-expedicion", "document-issue-date"), required=False),
            PackFieldDefinition("expiry_date", "Fecha de vencimiento", aliases=("fecha-de-vencimiento", "fecha-de-expiracion", "fecha-de-caducidad", "document-expiry-date"), required=False),
        ),
        decision_thresholds=PackDecisionThresholds(auto_accept_confidence=0.93, auto_accept_agreement=0.74, accept_with_warning_confidence=0.82, review_agreement=0.42),
    ),
    DocumentPack(
        pack_id="identity-pe-back",
        document_family="identity",
        country="PE",
        variant="identity-pe-back-text",
        version="2026-03",
        label="DNI Peru dorso",
        document_side="back",
        classification_keywords=(
            "DOMICILIO",
            "ESTADO CIVIL",
            "GRADO DE INSTRUCCION",
            "DONACION DE ORGANOS",
            "RESTRICCION",
        ),
        expected_fields=(
            PackFieldDefinition("address", "Domicilio", aliases=("domicilio",), required=True, critical=True),
            PackFieldDefinition("civil_status", "Estado civil", aliases=("estado-civil",), required=False),
            PackFieldDefinition("education", "Grado de instruccion", aliases=("grado-de-instruccion",), required=False),
            PackFieldDefinition("donor", "Donacion de organos", aliases=("donacion-de-organos",), required=False),
            PackFieldDefinition("restriction", "Restriccion", aliases=("restriccion",), required=False),
        ),
        decision_thresholds=PackDecisionThresholds(auto_accept_confidence=0.94, auto_accept_agreement=0.8, accept_with_warning_confidence=0.85, review_agreement=0.5),
        min_back_fields=2,
    ),
    DocumentPack(
        pack_id="identity-co-front",
        document_family="identity",
        country="CO",
        variant="identity-co-front-text",
        version="2026-03",
        label="Cedula Colombia frente",
        document_side="front",
        classification_keywords=(
            "REPUBLICA DE COLOMBIA",
            "REGISTRADURIA",
            "CEDULA DE CIUDADANIA",
            "APELLIDOS",
            "NOMBRES",
        ),
        expected_fields=(
            PackFieldDefinition("holder_name", "Titular", aliases=("nombre-completo", "titular", "nombres", "nombre", "apellido", "apellidos", "given-name", "surname"), required=True, critical=True),
            PackFieldDefinition("document_number", "Cedula", aliases=("numero-de-documento", "numero", "documento", "numero-de-identificacion", "cedula", "numero-de-identidad", "nuip", "nuip-number"), required=True, critical=True),
            PackFieldDefinition("birth_date", "Fecha de nacimiento", aliases=("fecha-de-nacimiento", "date-of-birth"), required=True),
            PackFieldDefinition("issue_date", "Fecha de expedicion", aliases=("fecha-de-emision", "fecha-de-expedicion", "document-issue-date"), required=False),
        ),
        decision_thresholds=PackDecisionThresholds(auto_accept_confidence=0.92, auto_accept_agreement=0.72, accept_with_warning_confidence=0.8, review_agreement=0.4),
    ),
    DocumentPack(
        pack_id="identity-co-back",
        document_family="identity",
        country="CO",
        variant="identity-co-back-text",
        version="2026-03",
        label="Cedula Colombia dorso",
        document_side="back",
        classification_keywords=(
            "ESTATURA",
            "G.S. RH",
            "LUGAR DE NACIMIENTO",
            "FECHA Y LUGAR DE EXPEDICION",
            "HUELLA",
        ),
        expected_fields=(
            PackFieldDefinition("birth_place", "Lugar de nacimiento", aliases=("lugar-de-nacimiento",), required=True, critical=True),
            PackFieldDefinition("height", "Estatura", aliases=("estatura",), required=False),
            PackFieldDefinition("blood_type", "Grupo sanguineo", aliases=("grupo-sanguineo",), required=False),
            PackFieldDefinition("issue_place", "Lugar de expedicion", aliases=("lugar-de-expedicion",), required=True),
        ),
        decision_thresholds=PackDecisionThresholds(auto_accept_confidence=0.94, auto_accept_agreement=0.8, accept_with_warning_confidence=0.85, review_agreement=0.5),
        min_back_fields=2,
    ),
    DocumentPack(
        pack_id="certificate-cl-previsional",
        document_family="certificate",
        country="CL",
        variant="certificate-cl-previsional-text",
        version="2026-03",
        label="Certificado previsional Chile",
        classification_keywords=(
            "CERTIFICADO",
            "COTIZACIONES",
            "AFP",
            "RUT",
            "CUENTA",
            "CERTIFICADO DE COTIZACIONES",
            "NUMERO DE CERTIFICADO",
        ),
        expected_fields=(
            PackFieldDefinition("holder_name", "Titular", aliases=("titular", "nombre-completo"), required=True, critical=True),
            PackFieldDefinition("rut", "RUT", aliases=("rut",), required=True, critical=True),
            PackFieldDefinition("certificate_number", "Numero de certificado", aliases=("numero-de-certificado",), required=True, critical=True),
            PackFieldDefinition("issue_date", "Fecha de emision", aliases=("fecha-de-emision",), required=True),
            PackFieldDefinition("account", "Cuenta", aliases=("cuenta",), required=True),
            PackFieldDefinition("issuer", "Emisor", aliases=("emisor",), required=True),
        ),
        decision_thresholds=PackDecisionThresholds(auto_accept_confidence=0.9, auto_accept_agreement=0.78, accept_with_warning_confidence=0.76, review_agreement=0.5),
    ),
    DocumentPack(
        pack_id="certificate-pe-laboral",
        document_family="certificate",
        country="PE",
        variant="certificate-pe-laboral-text",
        version="2026-03",
        label="Certificado laboral Peru",
        classification_keywords=(
            "CERTIFICADO DE TRABAJO",
            "CONSTANCIA LABORAL",
            "REPUBLICA DEL PERU",
            "DNI",
        ),
    ),
    DocumentPack(
        pack_id="certificate-co-laboral",
        document_family="certificate",
        country="CO",
        variant="certificate-co-laboral-text",
        version="2026-03",
        label="Certificacion laboral Colombia",
        classification_keywords=(
            "CERTIFICACION LABORAL",
            "REPUBLICA DE COLOMBIA",
            "CEDULA",
            "NIT",
        ),
    ),
    DocumentPack(
        pack_id="passport-generic",
        document_family="passport",
        country="XX",
        variant="passport-text",
        version="2026-03",
        label="Pasaporte generico",
        supported=True,
        classification_keywords=("PASSPORT", "PASAPORTE"),
        expected_fields=(
            PackFieldDefinition("holder_name", "Titular", aliases=("nombre-completo", "holder", "name"), required=True, critical=True),
            PackFieldDefinition("document_number", "Numero de documento", aliases=("passport-number", "numero-de-documento"), required=True, critical=True),
            PackFieldDefinition("birth_date", "Fecha de nacimiento", aliases=("date-of-birth", "fecha-de-nacimiento"), required=True),
            PackFieldDefinition("expiry_date", "Fecha de vencimiento", aliases=("date-of-expiry", "fecha-de-vencimiento"), required=True),
            PackFieldDefinition("mrz", "MRZ", aliases=("mrz",), required=False, critical=True),
        ),
        decision_thresholds=PackDecisionThresholds(auto_accept_confidence=0.93, auto_accept_agreement=0.8, accept_with_warning_confidence=0.82, review_agreement=0.45),
    ),
    DocumentPack(
        pack_id="driver-license-generic",
        document_family="driver_license",
        country="XX",
        variant="driver-license-text",
        version="2026-03",
        label="Licencia generica",
        supported=True,
        classification_keywords=("LICENCIA", "CONDUC", "DRIVER LICENSE"),
        expected_fields=(
            PackFieldDefinition("holder_name", "Titular", aliases=("nombre-completo", "holder", "name"), required=True, critical=True),
            PackFieldDefinition("document_number", "Numero de documento", aliases=("license-number", "numero-de-documento", "numero"), required=True, critical=True),
            PackFieldDefinition("birth_date", "Fecha de nacimiento", aliases=("date-of-birth", "fecha-de-nacimiento"), required=False),
            PackFieldDefinition("issue_date", "Fecha de emision", aliases=("issue-date", "fecha-de-emision"), required=False),
            PackFieldDefinition("expiry_date", "Fecha de vencimiento", aliases=("expiry-date", "fecha-de-vencimiento"), required=False),
            PackFieldDefinition("categories", "Categorias", aliases=("categories", "class"), required=False),
        ),
        decision_thresholds=PackDecisionThresholds(auto_accept_confidence=0.92, auto_accept_agreement=0.76, accept_with_warning_confidence=0.8, review_agreement=0.42),
    ),
    DocumentPack(
        pack_id="invoice-generic",
        document_family="invoice",
        country="XX",
        variant="invoice-text",
        version="2026-03",
        label="Factura generica",
        supported=False,
        classification_keywords=("FACTURA", "INVOICE", "RUC", "NIT"),
    ),
)

PACKS_BY_ID = {pack.pack_id: pack for pack in DOCUMENT_PACKS}


def normalize_requested_family(value: str) -> str:
    normalized = (value or "").strip().lower()
    return "unclassified" if normalized in AUTO_FAMILY_VALUES else normalized


def normalize_requested_country(value: str) -> str:
    normalized = (value or "").strip().upper()
    return "XX" if normalized in AUTO_COUNTRY_VALUES else normalized


def resolve_document_pack(pack_id: str | None = None, document_family: str | None = None, country: str | None = None, variant: str | None = None) -> DocumentPack | None:
    if pack_id and pack_id in PACKS_BY_ID:
        return PACKS_BY_ID[pack_id]

    normalized_family = normalize_requested_family(document_family or "")
    normalized_country = normalize_requested_country(country or "")

    matching_packs = [pack for pack in DOCUMENT_PACKS if pack.document_family == normalized_family and (not variant or pack.variant == variant)]

    if normalized_country != "XX":
        exact_country = next((pack for pack in matching_packs if pack.country == normalized_country), None)
        if exact_country:
            return exact_country

    return next((pack for pack in matching_packs if pack.country == "XX"), None)


def iter_pack_field_keys(pack: DocumentPack | None, field_key: str) -> tuple[str, ...]:
    if pack is None:
        return (field_key,)

    for field in pack.expected_fields:
        if field.field_key == field_key:
            return (field.field_key, *field.aliases)

    return (field_key,)
