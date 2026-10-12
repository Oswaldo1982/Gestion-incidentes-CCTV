import os
import re
import json
import secrets
import string
import hashlib
import datetime
import shutil
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from app.config import settings
from app.models.license import SiteLicenseKey, SiteActivationState
from app.models.audit import AuditLog
from app.utils.security import get_password_hash, verify_password

# Sedes Oficiales del Sistema de Gestión CCTV
OFFICIAL_SITES: List[Dict[str, str]] = [
    {
        "id": "san-agustin",
        "name": "San Agustín",
        "full_name": "San Agustín (Huila)",
        "region": "Huila"
    },
    {
        "id": "san-jose-guaviare",
        "name": "San José del Guaviare",
        "full_name": "San José del Guaviare (Guaviare)",
        "region": "Guaviare"
    },
    {
        "id": "el-retorno",
        "name": "El Retorno",
        "full_name": "El Retorno (Guaviare)",
        "region": "Guaviare"
    },
    {
        "id": "calamar",
        "name": "Calamar",
        "full_name": "Calamar (Guaviare)",
        "region": "Guaviare"
    }
]

# Rutas de almacenamiento seguro para las llaves y certificados PDF del desarrollador
SECURE_VAULT_DIR = os.path.join(os.getcwd(), "secure_vault")
VAULT_PDF_DIR = os.path.join(SECURE_VAULT_DIR, "licencias_pdf")
VAULT_KEYS_FILE = os.path.join(SECURE_VAULT_DIR, "developer_license_vault.json")

# Directorio de artefactos de Antigravity (Compartido exclusivamente al desarrollador)
ANTIGRAVITY_ARTIFACTS_DIR = r"C:\Users\oswal\.gemini\antigravity-ide\brain\f71fc4a1-a846-403e-923c-cc24667e7908\licencias_pdf"


def normalize_password(raw_pwd: str) -> str:
    """Elimina espacios, guiones y caracteres no alfanuméricos, convirtiendo a mayúsculas."""
    if not raw_pwd:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", raw_pwd).upper()


def format_password_display(clean_pwd: str) -> str:
    """Formatea una cadena de 16 caracteres en bloques de 4: XXXX-XXXX-XXXX-XXXX."""
    if len(clean_pwd) != 16:
        return clean_pwd
    return f"{clean_pwd[0:4]}-{clean_pwd[4:8]}-{clean_pwd[8:12]}-{clean_pwd[12:16]}"


def mask_password(clean_pwd: str) -> str:
    """Enmascara la contraseña dejando visibles únicamente los últimos 4 dígitos."""
    if len(clean_pwd) != 16:
        return "****-****-****-****"
    return f"****-****-****-{clean_pwd[12:16]}"


def generate_secure_16_digit_key() -> str:
    """Genera una contraseña criptográficamente segura de 16 caracteres alfanuméricos."""
    alphabet = string.ascii_uppercase + string.digits
    # Excluimos caracteres visualmente confusos si se desea, o alfabeto completo A-Z 0-9
    return "".join(secrets.choice(alphabet) for _ in range(16))


def build_pdf_license_certificate(
    output_path: str,
    site_info: Dict[str, str],
    year: int,
    raw_password: str,
    certificate_code: str,
    emission_date: datetime.datetime
) -> str:
    """
    Genera un archivo PDF institucional e independiente con la credencial de activación.
    Diseñado con altos estándares de seguridad confidencial para el desarrollador.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CertTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#0f172a'),
        alignment=1
    )
    subtitle_style = ParagraphStyle(
        'CertSub',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#2563eb'),
        alignment=1
    )
    confidential_style = ParagraphStyle(
        'CertConf',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#991b1b'),
        alignment=1
    )
    body_style = ParagraphStyle(
        'CertBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#334155')
    )
    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0f172a')
    )
    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0f172a')
    )
    key_display_style = ParagraphStyle(
        'KeyDisplay',
        parent=styles['Normal'],
        fontName='Courier-Bold',
        fontSize=19,
        leading=22,
        textColor=colors.HexColor('#1e3a8a'),
        alignment=1
    )

    story = []

    # 1. Encabezado Institucional
    story.append(Paragraph("SISTEMA INTEGRAL DE SEGURIDAD CIUDADANA CCTV", title_style))
    story.append(Spacer(1, 3))
    story.append(Paragraph("DIRECCIÓN DE CONTROL OPERATIVO Y SEGURIDAD TECNOLÓGICA", subtitle_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1e40af'), spaceAfter=8))

    # 2. Cinta de Confidencialidad
    conf_table_data = [[
        Paragraph("🔒 DOCUMENTO ESTRICTAMENTE CONFIDENCIAL — USO EXCLUSIVO DEL DESARROLLADOR PRINCIPAL<br/><font size='7.5' color='#7f1d1d'>PROHIBIDA SU DISTRIBUCIÓN PÚBLICA O ALMACENAMIENTO EN DIRECTORIOS WEB DE ADMINISTRADORES LOCALES</font>", confidential_style)
    ]]
    conf_table = Table(conf_table_data, colWidths=[540])
    conf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fee2e2')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#ef4444')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(conf_table)
    story.append(Spacer(1, 10))

    # 3. Datos del Certificado
    formatted_key = format_password_display(raw_password)
    year_label = f"AÑO {year} (Vigencia de 365 Días Calendario)"
    
    cert_metadata = [
        [
            Paragraph("Sede Territorial Asignada:", table_cell_bold),
            Paragraph(f"<b>{site_info['full_name']}</b> (ID: <font face='Courier'>{site_info['id']}</font>)", table_cell_style),
            Paragraph("Vigencia Operativa:", table_cell_bold),
            Paragraph(f"<b>{year_label}</b>", table_cell_style)
        ],
        [
            Paragraph("Código de Certificado:", table_cell_bold),
            Paragraph(f"<font face='Courier'>{certificate_code}</font>", table_cell_style),
            Paragraph("Fecha de Emisión:", table_cell_bold),
            Paragraph(emission_date.strftime("%d/%m/%Y %H:%M:%S UTC"), table_cell_style)
        ],
        [
            Paragraph("Tipo de Licencia:", table_cell_bold),
            Paragraph("Activación Anual Exclusiva por Sitio", table_cell_style),
            Paragraph("Nivel de Seguridad:", table_cell_bold),
            Paragraph("Alfanumérica Criptográfica 16 Dígitos", table_cell_style)
        ]
    ]

    t_meta = Table(cert_metadata, colWidths=[120, 160, 110, 150])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 14))

    # 4. Tarjeta Destacada con la Clave de 16 Dígitos
    key_box_data = [
        [Paragraph(f"CREDENCIAL MAESTRA DE ACTIVACIÓN — {year_label.upper()}", ParagraphStyle('KHead', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#1e40af'), alignment=1))],
        [Spacer(1, 4)],
        [Paragraph(f"[ {formatted_key} ]", key_display_style)],
        [Spacer(1, 4)],
        [Paragraph("Formato: 16 caracteres alfanuméricos continuos o agrupados con guiones", ParagraphStyle('KFoot', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=8, textColor=colors.HexColor('#64748b'), alignment=1))]
    ]
    t_key_box = Table(key_box_data, colWidths=[540])
    t_key_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#eff6ff')),
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#3b82f6')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(t_key_box)
    story.append(Spacer(1, 14))

    # 5. Instrucciones y Reglas de Negocio
    story.append(Paragraph("<b>PROTOCOLO OFICIAL DE ACTIVACIÓN Y CONTROL DE TIEMPOS:</b>", ParagraphStyle('ProtoHead', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9.5, textColor=colors.HexColor('#0f172a'))))
    story.append(Spacer(1, 4))
    
    proto_text = f"""
    <b>1. Plazo Inicial de 24 Horas:</b> Al desplegar e ingresar por primera vez al sitio <b>{site_info['name']}</b>, el sistema otorga un período de gracia de 24 horas de operación libre.<br/>
    <b>2. Notificación y Exigencia:</b> Transcurridas las 24 horas iniciales, el sistema bloquea preventivamente las operaciones y exige al Administrador del sitio ingresar la clave del <b>Año 1</b>.<br/>
    <b>3. Renovación Anual:</b> Cumplidos los 365 días del primer año, el sistema requerirá la contraseña del <b>Año 2</b>, y posteriormente la del <b>Año 3</b> para continuar el servicio.<br/>
    <b>4. Entrega de Credenciales:</b> Como desarrollador principal, conserve este documento seguro y proporcione la contraseña al Administrador local únicamente cuando corresponda la vigencia respectiva.
    """
    story.append(Paragraph(proto_text, body_style))
    story.append(Spacer(1, 12))

    # 6. Bloque Criptográfico de Integridad
    key_hash = hashlib.sha256(raw_password.encode('utf-8')).hexdigest()
    crypto_data = [
        [
            Paragraph("<b>Algoritmo de Validación:</b> PBKDF2 / SHA-256 Digest", table_cell_style),
            Paragraph(f"<b>Hash de Verificación:</b> <font face='Courier' size='7'>{key_hash[:32]}...</font>", table_cell_style)
        ],
        [
            Paragraph("<b>Ambiente:</b> Servidor Central CCTV", table_cell_style),
            Paragraph("<b>Bypass de Pruebas:</b> Disponible vía variable <font face='Courier'>DEV_MODE=true</font>", table_cell_style)
        ]
    ]
    t_crypto = Table(crypto_data, colWidths=[270, 270])
    t_crypto.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f1f5f9')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_crypto)
    story.append(Spacer(1, 16))

    # 7. Firma Digital del Desarrollador
    sig_data = [
        [
            Paragraph("<b>EMITIDO POR:</b><br/>Arquitectura de Software y Seguridad CCTV<br/><i>Desarrollador Principal</i>", table_cell_style),
            Paragraph(f"<b>DESTINATARIO:</b><br/>Custodia Exclusiva del Desarrollador<br/><i>Sede: {site_info['name']}</i>", table_cell_style),
            Paragraph(f"<b>CÓDIGO DE TRAZABILIDAD:</b><br/><font face='Courier'>{certificate_code}</font><br/><i>Estado: Generado Oficialmente</i>", table_cell_style)
        ]
    ]
    t_sig = Table(sig_data, colWidths=[180, 180, 180])
    t_sig.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, -1), 0.5, colors.HexColor('#94a3b8')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(t_sig)

    doc.build(story)
    return output_path


def load_or_create_developer_vault() -> Dict[str, Any]:
    """
    Carga o inicializa el almacén seguro de claves maestras del desarrollador.
    Genera 12 contraseñas alfanuméricas de 16 dígitos (4 sitios x 3 años) si no existen.
    """
    os.makedirs(SECURE_VAULT_DIR, exist_ok=True)
    os.makedirs(VAULT_PDF_DIR, exist_ok=True)
    os.makedirs(ANTIGRAVITY_ARTIFACTS_DIR, exist_ok=True)

    if os.path.exists(VAULT_KEYS_FILE):
        try:
            with open(VAULT_KEYS_FILE, "r", encoding="utf-8") as f:
                vault_data = json.load(f)
                if "sites" in vault_data and len(vault_data["sites"]) == 4:
                    return vault_data
        except Exception as e:
            print(f"[!] Error al leer almacén existente de licencias: {e}")

    # Generar nuevo almacén con 12 contraseñas independientes
    now_utc = datetime.datetime.utcnow()
    vault_data = {
        "created_at": now_utc.isoformat(),
        "total_keys": 12,
        "sites": {}
    }

    for site in OFFICIAL_SITES:
        site_id = site["id"]
        vault_data["sites"][site_id] = {
            "name": site["name"],
            "full_name": site["full_name"],
            "region": site["region"],
            "years": {}
        }
        for year in [1, 2, 3]:
            raw_pwd = generate_secure_16_digit_key()
            slug_site = site_id.upper().replace("-", "_")
            cert_code = f"LIC-{slug_site}-Y{year}-{raw_pwd[:4]}"
            pdf_name = f"LICENCIA_{slug_site}_ANO_{year}.pdf"

            vault_data["sites"][site_id]["years"][str(year)] = {
                "year": year,
                "password": raw_pwd,
                "formatted": format_password_display(raw_pwd),
                "mask": mask_password(raw_pwd),
                "certificate_code": cert_code,
                "pdf_filename": pdf_name
            }

    with open(VAULT_KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(vault_data, f, indent=2, ensure_ascii=False)

    return vault_data


def generate_all_12_license_pdfs() -> List[str]:
    """
    Genera los 12 archivos PDF de licencia (4 sitios x 3 años) y los guarda en
    la bóveda segura y en la carpeta de artefactos de Antigravity.
    Retorna la lista de rutas generadas.
    """
    vault = load_or_create_developer_vault()
    emission_date = datetime.datetime.fromisoformat(vault.get("created_at", datetime.datetime.utcnow().isoformat()))
    created_paths = []

    for site_id, site_data in vault["sites"].items():
        site_info = {
            "id": site_id,
            "name": site_data["name"],
            "full_name": site_data["full_name"],
            "region": site_data["region"]
        }
        for year_str, year_info in site_data["years"].items():
            year = int(year_str)
            raw_pwd = year_info["password"]
            cert_code = year_info["certificate_code"]
            pdf_filename = year_info["pdf_filename"]

            # 1. Guardar en bóveda local segura
            vault_pdf_path = os.path.join(VAULT_PDF_DIR, pdf_filename)
            build_pdf_license_certificate(
                output_path=vault_pdf_path,
                site_info=site_info,
                year=year,
                raw_password=raw_pwd,
                certificate_code=cert_code,
                emission_date=emission_date
            )
            created_paths.append(vault_pdf_path)

            # 2. Copiar a la carpeta de artefactos de Antigravity para compartir al usuario
            try:
                artifact_pdf_path = os.path.join(ANTIGRAVITY_ARTIFACTS_DIR, pdf_filename)
                shutil.copy2(vault_pdf_path, artifact_pdf_path)
            except Exception as e:
                print(f"[!] Aviso al copiar PDF a artefactos de Antigravity: {e}")

    return created_paths


def ensure_all_site_licenses_initialized(db: Session) -> Dict[str, Any]:
    """
    Inicializa en la base de datos los registros de licencias (hashes seguros)
    y el estado de activación para cada uno de los 4 sitios.
    Genera además los 12 PDFs de credenciales si no han sido creados.
    """
    vault = load_or_create_developer_vault()
    generate_all_12_license_pdfs()

    seeded_licenses = 0
    seeded_states = 0

    for site in OFFICIAL_SITES:
        site_id = site["id"]
        site_name = site["name"]

        # 1. Asegurar estado de activación del sitio
        state = db.query(SiteActivationState).filter(SiteActivationState.site_id == site_id).first()
        if not state:
            state = SiteActivationState(
                site_id=site_id,
                first_access_at=None,  # Se registrará en el primer acceso real
                current_year=1,
                status="GRACE_PERIOD",
                failed_attempts=0
            )
            db.add(state)
            seeded_states += 1

        # 2. Asegurar las 3 llaves (Años 1, 2 y 3) para este sitio
        site_vault = vault["sites"].get(site_id, {})
        for year in [1, 2, 3]:
            existing_key = db.query(SiteLicenseKey).filter(
                SiteLicenseKey.site_id == site_id,
                SiteLicenseKey.year == year
            ).first()

            if not existing_key:
                year_data = site_vault.get("years", {}).get(str(year), {})
                raw_pwd = year_data.get("password")
                if not raw_pwd:
                    raw_pwd = generate_secure_16_digit_key()
                
                hashed = get_password_hash(raw_pwd)
                mask = mask_password(raw_pwd)
                cert_code = year_data.get("certificate_code", f"LIC-{site_id.upper()}-Y{year}-{raw_pwd[:4]}")

                new_key = SiteLicenseKey(
                    site_id=site_id,
                    site_name=site_name,
                    year=year,
                    password_hash=hashed,
                    password_mask=mask,
                    certificate_code=cert_code,
                    is_activated=False
                )
                db.add(new_key)
                seeded_licenses += 1

    db.commit()
    return {
        "seeded_licenses": seeded_licenses,
        "seeded_states": seeded_states
    }


def record_site_first_access(db: Session, site_id: str) -> datetime.datetime:
    """
    Registra el timestamp del primer acceso al sitio si aún no ha sido registrado.
    Inicia la cuenta regresiva del período de gracia de 24 horas.
    """
    state = db.query(SiteActivationState).filter(SiteActivationState.site_id == site_id).first()
    now_utc = datetime.datetime.utcnow()

    if not state:
        state = SiteActivationState(
            site_id=site_id,
            first_access_at=now_utc,
            current_year=1,
            status="GRACE_PERIOD"
        )
        db.add(state)
        db.commit()
        return now_utc

    if not state.first_access_at:
        state.first_access_at = now_utc
        db.commit()
        return now_utc

    return state.first_access_at


def get_site_license_status(db: Session, site_id: str) -> Dict[str, Any]:
    """
    Evalúa el estado exhaustivo de la licencia para el sitio especificado:
    - Modo Desarrollador (DEV_MODE): Libre acceso sin bloqueos.
    - Período de gracia inicial (24h) desde el primer acceso.
    - Bloqueo y solicitud de contraseña de Año 1 tras las 24h.
    - Vigencia de 365 días por año y renovación para Año 2 y Año 3.
    """
    # 1. Modo Desarrollador (Bypass Total)
    if settings.DEV_MODE:
        return {
            "site_id": site_id,
            "is_allowed": True,
            "status": "DEV_BYPASS",
            "message": "🛠️ Modo Desarrollador activo (DEV_MODE=True): Restricciones y temporizadores desactivados.",
            "current_year": 1,
            "required_year": None,
            "hours_remaining_grace": 24.0,
            "days_remaining_active": 365,
            "first_access_at": None,
            "active_until": None,
            "is_dev_mode": True,
            "years_status": [
                {"year": 1, "is_activated": True, "badge": "Bypass Dev"},
                {"year": 2, "is_activated": True, "badge": "Bypass Dev"},
                {"year": 3, "is_activated": True, "badge": "Bypass Dev"}
            ]
        }

    # Normalizar site_id o asignar por defecto 'san-agustin'
    valid_ids = [s["id"] for s in OFFICIAL_SITES]
    clean_id = site_id if site_id in valid_ids else "san-agustin"
    site_obj = next((s for s in OFFICIAL_SITES if s["id"] == clean_id), OFFICIAL_SITES[0])
    site_name = site_obj["name"]

    state = db.query(SiteActivationState).filter(SiteActivationState.site_id == clean_id).first()
    now = datetime.datetime.utcnow()

    # Si no tiene estado previo, crearlo
    if not state:
        state = SiteActivationState(
            site_id=clean_id,
            first_access_at=now,
            current_year=1,
            status="GRACE_PERIOD"
        )
        db.add(state)
        db.commit()

    # Si aún no tiene first_access_at, registrarlo ahora
    if not state.first_access_at:
        state.first_access_at = now
        db.commit()

    # Consultar las llaves de los 3 años
    keys = db.query(SiteLicenseKey).filter(
        SiteLicenseKey.site_id == clean_id
    ).order_by(SiteLicenseKey.year.asc()).all()

    key_map = {k.year: k for k in keys}
    k1 = key_map.get(1)
    k2 = key_map.get(2)
    k3 = key_map.get(3)

    years_status = [
        {
            "year": 1,
            "is_activated": bool(k1 and k1.is_activated),
            "activated_at": k1.activated_at if k1 else None,
            "expires_at": k1.expires_at if k1 else None,
            "mask": k1.password_mask if k1 else "****"
        },
        {
            "year": 2,
            "is_activated": bool(k2 and k2.is_activated),
            "activated_at": k2.activated_at if k2 else None,
            "expires_at": k2.expires_at if k2 else None,
            "mask": k2.password_mask if k2 else "****"
        },
        {
            "year": 3,
            "is_activated": bool(k3 and k3.is_activated),
            "activated_at": k3.activated_at if k3 else None,
            "expires_at": k3.expires_at if k3 else None,
            "mask": k3.password_mask if k3 else "****"
        }
    ]

    # A. Caso 1: Año 1 NO está activado
    if not k1 or not k1.is_activated:
        elapsed = now - state.first_access_at
        grace_limit = datetime.timedelta(hours=24)

        if elapsed < grace_limit:
            hours_left = max(0.0, round((grace_limit - elapsed).total_seconds() / 3600.0, 1))
            mins_left = max(0, int(((grace_limit - elapsed).total_seconds() % 3600) // 60))
            return {
                "site_id": clean_id,
                "site_name": site_name,
                "is_allowed": True,
                "status": "GRACE_PERIOD",
                "message": f"⏳ Período de gracia inicial activo ({hours_left}h restantes). Ingrese la contraseña del Año 1 antes de finalizar las 24 horas.",
                "current_year": 1,
                "required_year": 1,
                "hours_remaining_grace": hours_left,
                "minutes_remaining_grace": mins_left,
                "days_remaining_active": None,
                "first_access_at": state.first_access_at,
                "active_until": state.first_access_at + grace_limit,
                "is_dev_mode": False,
                "years_status": years_status
            }
        else:
            # Período de gracia expirado -> Bloqueo
            return {
                "site_id": clean_id,
                "site_name": site_name,
                "is_allowed": False,
                "status": "LOCKED_AWAITING_YEAR_1",
                "message": f"🔒 El período de gracia de 24 horas ha finalizado para {site_name}. Ingrese la contraseña del Año 1 para continuar.",
                "current_year": 1,
                "required_year": 1,
                "hours_remaining_grace": 0.0,
                "days_remaining_active": 0,
                "first_access_at": state.first_access_at,
                "active_until": state.first_access_at + grace_limit,
                "is_dev_mode": False,
                "years_status": years_status
            }

    # B. Caso 2: Año 1 ESTÁ activado
    # Verificar vigencia de Año 1
    if k1.expires_at and now <= k1.expires_at:
        days_left = max(0, (k1.expires_at - now).days)
        return {
            "site_id": clean_id,
            "site_name": site_name,
            "is_allowed": True,
            "status": "ACTIVE_YEAR_1",
            "message": f"✅ Licencia de Año 1 Activa ({days_left} días restantes de vigencia).",
            "current_year": 1,
            "required_year": 2,  # Puede renovar para Año 2
            "hours_remaining_grace": 0.0,
            "days_remaining_active": days_left,
            "first_access_at": state.first_access_at,
            "active_until": k1.expires_at,
            "is_dev_mode": False,
            "years_status": years_status
        }

    # Año 1 expiró -> Verificar Año 2
    if not k2 or not k2.is_activated:
        return {
            "site_id": clean_id,
            "site_name": site_name,
            "is_allowed": False,
            "status": "LOCKED_AWAITING_YEAR_2",
            "message": f"🔒 La vigencia del Año 1 ha culminado para {site_name}. Ingrese la contraseña del Año 2 para renovar por 365 días.",
            "current_year": 2,
            "required_year": 2,
            "hours_remaining_grace": 0.0,
            "days_remaining_active": 0,
            "first_access_at": state.first_access_at,
            "active_until": k1.expires_at,
            "is_dev_mode": False,
            "years_status": years_status
        }

    # C. Caso 3: Año 2 ESTÁ activado
    if k2.expires_at and now <= k2.expires_at:
        days_left = max(0, (k2.expires_at - now).days)
        return {
            "site_id": clean_id,
            "site_name": site_name,
            "is_allowed": True,
            "status": "ACTIVE_YEAR_2",
            "message": f"✅ Licencia de Año 2 Activa ({days_left} días restantes de vigencia).",
            "current_year": 2,
            "required_year": 3,  # Puede renovar para Año 3
            "hours_remaining_grace": 0.0,
            "days_remaining_active": days_left,
            "first_access_at": state.first_access_at,
            "active_until": k2.expires_at,
            "is_dev_mode": False,
            "years_status": years_status
        }

    # Año 2 expiró -> Verificar Año 3
    if not k3 or not k3.is_activated:
        return {
            "site_id": clean_id,
            "site_name": site_name,
            "is_allowed": False,
            "status": "LOCKED_AWAITING_YEAR_3",
            "message": f"🔒 La vigencia del Año 2 ha culminado para {site_name}. Ingrese la contraseña del Año 3 para renovar por 365 días.",
            "current_year": 3,
            "required_year": 3,
            "hours_remaining_grace": 0.0,
            "days_remaining_active": 0,
            "first_access_at": state.first_access_at,
            "active_until": k2.expires_at,
            "is_dev_mode": False,
            "years_status": years_status
        }

    # D. Caso 4: Año 3 ESTÁ activado
    if k3.expires_at and now <= k3.expires_at:
        days_left = max(0, (k3.expires_at - now).days)
        return {
            "site_id": clean_id,
            "site_name": site_name,
            "is_allowed": True,
            "status": "ACTIVE_YEAR_3",
            "message": f"✅ Licencia de Año 3 Activa ({days_left} días restantes de vigencia).",
            "current_year": 3,
            "required_year": None,
            "hours_remaining_grace": 0.0,
            "days_remaining_active": days_left,
            "first_access_at": state.first_access_at,
            "active_until": k3.expires_at,
            "is_dev_mode": False,
            "years_status": years_status
        }

    # Ciclo de 3 años culminado
    return {
        "site_id": clean_id,
        "site_name": site_name,
        "is_allowed": False,
        "status": "EXPIRED_FINAL",
        "message": f"🔒 El ciclo de licenciamiento de 3 años para {site_name} ha culminado. Comuníquese con el desarrollador del sistema.",
        "current_year": 3,
        "required_year": None,
        "hours_remaining_grace": 0.0,
        "days_remaining_active": 0,
        "first_access_at": state.first_access_at,
        "active_until": k3.expires_at,
        "is_dev_mode": False,
        "years_status": years_status
    }


def activate_site_year_license(
    db: Session,
    site_id: str,
    password_input: str,
    user: Optional[Any] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Valida la contraseña alfanumérica de 16 dígitos para el año correspondiente
    del sitio especificado y aplica la activación de 365 días.
    Incluye protección contra fuerza bruta (bloqueo tras 5 intentos fallidos).
    """
    valid_ids = [s["id"] for s in OFFICIAL_SITES]
    clean_id = site_id if site_id in valid_ids else "san-agustin"
    site_obj = next((s for s in OFFICIAL_SITES if s["id"] == clean_id), OFFICIAL_SITES[0])
    site_name = site_obj["name"]

    state = db.query(SiteActivationState).filter(SiteActivationState.site_id == clean_id).first()
    now = datetime.datetime.utcnow()

    if not state:
        state = SiteActivationState(site_id=clean_id, first_access_at=now, current_year=1, status="GRACE_PERIOD")
        db.add(state)
        db.commit()

    # 1. Protección contra ataques de fuerza bruta (Lockout)
    if state.lockout_until and now < state.lockout_until:
        mins_remaining = int((state.lockout_until - now).total_seconds() // 60) + 1
        return False, f"Demasiados intentos erróneos. El ingreso está temporalmente suspendido por {mins_remaining} minutos.", {}

    # 2. Normalizar y verificar longitud de contraseña
    cleaned = normalize_password(password_input)
    if len(cleaned) != 16:
        return False, "La contraseña debe contener exactamente 16 dígitos alfanuméricos.", {}

    # 3. Determinar qué año corresponde activar
    status_info = get_site_license_status(db, clean_id)
    target_year = status_info.get("required_year") or 1

    target_key = db.query(SiteLicenseKey).filter(
        SiteLicenseKey.site_id == clean_id,
        SiteLicenseKey.year == target_year
    ).first()

    if not target_key:
        return False, f"No se encontró el registro de clave para el Año {target_year} de {site_name}.", {}

    # 4. Comprobar hash criptográfico
    is_valid = verify_password(cleaned, target_key.password_hash)
    username_audit = getattr(user, "username", "admin")
    user_id_audit = getattr(user, "id", None)

    if not is_valid:
        state.failed_attempts += 1
        if state.failed_attempts >= 5:
            state.lockout_until = now + datetime.timedelta(minutes=15)
            db.commit()
            AuditLog.create(
                db=db,
                user_id=user_id_audit,
                username=username_audit,
                action="SITE_LICENSE_LOCKOUT",
                details={"site_id": clean_id, "year": target_year, "failed_attempts": state.failed_attempts}
            ) if hasattr(AuditLog, 'create') else None
            return False, "Contraseña incorrecta. Se ha activado un bloqueo de seguridad de 15 minutos por reiterados intentos.", {}

        db.commit()
        # Registrar intento fallido en auditoría
        try:
            from app.services.audit_service import create_audit_log
            create_audit_log(
                db,
                user_id=user_id_audit,
                username=username_audit,
                action="SITE_LICENSE_FAILED_ATTEMPT",
                details={"site_id": clean_id, "year": target_year, "failed_attempts": state.failed_attempts}
            )
        except Exception:
            pass

        return False, f"Contraseña incorrecta para el Año {target_year} del sitio {site_name}. Intento {state.failed_attempts}/5 registrado en auditoría.", {}

    # 5. Contraseña correcta -> Activar período de 365 días
    # Si renueva anticipadamente, el tiempo es acumulativo
    base_start = now
    prev_key = db.query(SiteLicenseKey).filter(
        SiteLicenseKey.site_id == clean_id,
        SiteLicenseKey.year == target_year - 1,
        SiteLicenseKey.is_activated == True
    ).first() if target_year > 1 else None

    if prev_key and prev_key.expires_at and prev_key.expires_at > now:
        base_start = prev_key.expires_at

    new_expiry = base_start + datetime.timedelta(days=365)

    target_key.is_activated = True
    target_key.activated_at = now
    target_key.expires_at = new_expiry

    state.failed_attempts = 0
    state.lockout_until = None
    state.current_year = target_year
    state.status = f"ACTIVE_YEAR_{target_year}"
    state.last_activated_at = now
    db.commit()

    # Registrar en auditoría
    try:
        from app.services.audit_service import create_audit_log
        create_audit_log(
            db,
            user_id=user_id_audit,
            username=username_audit,
            action="SITE_LICENSE_ACTIVATED",
            details={
                "site_id": clean_id,
                "site_name": site_name,
                "year": target_year,
                "expires_at": new_expiry.isoformat()
            }
        )
    except Exception:
        pass

    success_msg = f"¡Licencia del Año {target_year} activada con éxito para {site_name}! Servicio habilitado por 365 días hasta {new_expiry.strftime('%d/%m/%Y')}."
    return True, success_msg, {
        "site_id": clean_id,
        "year": target_year,
        "expires_at": new_expiry
    }
