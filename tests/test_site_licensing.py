import os
import json
import datetime
import pytest
from app.config import settings
from app.models.license import SiteLicenseKey, SiteActivationState, License
from app.models.user import User
from app.services.site_license_service import (
    OFFICIAL_SITES,
    load_or_create_developer_vault,
    generate_all_12_license_pdfs,
    ensure_all_site_licenses_initialized,
    get_site_license_status,
    record_site_first_access,
    activate_site_year_license,
    normalize_password,
    format_password_display,
    VAULT_PDF_DIR,
    ANTIGRAVITY_ARTIFACTS_DIR
)


def test_12_keys_and_12_pdfs_generated(db):
    """
    Regla 1: El sistema gestiona 4 sitios y genera exactamente 3 contraseñas
    ultra seguras de 16 caracteres por sitio (12 en total) y 12 archivos PDF independientes.
    """
    res = ensure_all_site_licenses_initialized(db)
    assert res is not None

    vault = load_or_create_developer_vault()
    assert len(vault["sites"]) == 4

    expected_sites = ["san-agustin", "san-jose-guaviare", "el-retorno", "calamar"]
    for s_id in expected_sites:
        assert s_id in vault["sites"]
        site_years = vault["sites"][s_id]["years"]
        assert len(site_years) == 3
        for y in ["1", "2", "3"]:
            key_data = site_years[y]
            clean_pwd = key_data["password"]
            assert len(clean_pwd) == 16
            assert clean_pwd.isalnum()
            assert key_data["formatted"] == format_password_display(clean_pwd)
            assert len(key_data["formatted"]) == 19  # 16 chars + 3 dashes

    # Validar que los 12 archivos PDF existen en la bóveda del desarrollador
    pdf_files = generate_all_12_license_pdfs()
    assert len(pdf_files) == 12
    for pdf_path in pdf_files:
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 1000

    # Validar que los 12 PDFs se copiaron a la carpeta de artefactos de Antigravity
    for s_id in expected_sites:
        for y in [1, 2, 3]:
            pdf_name = f"LICENCIA_{s_id.upper().replace('-', '_')}_ANO_{y}.pdf"
            artifact_file = os.path.join(ANTIGRAVITY_ARTIFACTS_DIR, pdf_name)
            assert os.path.exists(artifact_file), f"Falta el archivo {artifact_file}"


def test_24h_grace_period_logic(db):
    """
    Regla 2: Plazo inicial (24 horas). Al primer acceso, otorga 24 horas de operación libre.
    Transcurridas las 24 horas, bloquea y exige la contraseña del Año 1.
    """
    settings.DEV_MODE = False
    site_id = "san-agustin"

    # 1. Asegurar licencias inicializadas en BD
    ensure_all_site_licenses_initialized(db)

    # 2. Registrar primer acceso simulado hace 5 horas
    state = db.query(SiteActivationState).filter(SiteActivationState.site_id == site_id).first()
    state.first_access_at = datetime.datetime.utcnow() - datetime.timedelta(hours=5)
    db.commit()

    # Evaluar estado: Debe estar en período de gracia permitido
    status_info = get_site_license_status(db, site_id)
    assert status_info["is_allowed"] is True
    assert status_info["status"] == "GRACE_PERIOD"
    assert status_info["required_year"] == 1
    assert 18.0 <= status_info["hours_remaining_grace"] <= 19.5

    # 3. Simular que transcurrieron 25 horas desde el primer acceso sin activar Año 1
    state.first_access_at = datetime.datetime.utcnow() - datetime.timedelta(hours=25)
    db.commit()

    # Evaluar estado: Debe estar bloqueado esperando contraseña del Año 1
    status_expired = get_site_license_status(db, site_id)
    assert status_expired["is_allowed"] is False
    assert status_expired["status"] == "LOCKED_AWAITING_YEAR_1"
    assert status_expired["required_year"] == 1
    assert status_expired["hours_remaining_grace"] == 0.0


def test_year_1_activation_and_anti_tamper(db, admin_user):
    """
    Regla 3: Activación del Año 1 con contraseña de 16 caracteres,
    rechazo de contraseñas incorrectas y protección contra fuerza bruta tras 5 intentos.
    """
    settings.DEV_MODE = False
    site_id = "el-retorno"
    ensure_all_site_licenses_initialized(db)

    vault = load_or_create_developer_vault()
    correct_pwd = vault["sites"][site_id]["years"]["1"]["password"]

    # 1. Intento con clave incorrecta
    success, msg, details = activate_site_year_license(db, site_id, "WRONGPASSWORD123", admin_user)
    assert success is False
    assert "incorrecta" in msg

    # 2. Forzar 5 intentos erróneos consecutivos para verificar lockout
    for _ in range(4):
        activate_site_year_license(db, site_id, "BADKEY1234567890", admin_user)

    # 6to intento: debe estar suspendido por bloqueo de seguridad
    blocked_success, blocked_msg, _ = activate_site_year_license(db, site_id, correct_pwd, admin_user)
    assert blocked_success is False
    assert "suspendido" in blocked_msg or "bloqueo" in blocked_msg

    # 3. Levantar lockout para probar activación correcta
    state = db.query(SiteActivationState).filter(SiteActivationState.site_id == site_id).first()
    state.lockout_until = None
    state.failed_attempts = 0
    db.commit()

    # 4. Activar con la clave formateada con guiones (XXXX-XXXX-XXXX-XXXX)
    formatted_key = format_password_display(correct_pwd)
    ok, success_msg, res = activate_site_year_license(db, site_id, formatted_key, admin_user)
    assert ok is True
    assert "activada con éxito" in success_msg
    assert res["year"] == 1

    # 5. Comprobar que el sitio ahora está 100% activo y operativo
    status_active = get_site_license_status(db, site_id)
    assert status_active["is_allowed"] is True
    assert status_active["status"] == "ACTIVE_YEAR_1"
    assert status_active["days_remaining_active"] >= 364


def test_yearly_renewals_year_2_and_3(db, admin_user):
    """
    Regla 4: Renovación anual secuencial.
    Al expirar el Año 1, exige Año 2. Al expirar Año 2, exige Año 3.
    """
    settings.DEV_MODE = False
    site_id = "calamar"
    ensure_all_site_licenses_initialized(db)

    vault = load_or_create_developer_vault()
    pwd_y1 = vault["sites"][site_id]["years"]["1"]["password"]
    pwd_y2 = vault["sites"][site_id]["years"]["2"]["password"]
    pwd_y3 = vault["sites"][site_id]["years"]["3"]["password"]

    # Activar Año 1
    activate_site_year_license(db, site_id, pwd_y1, admin_user)

    # Simular que Año 1 ha expirado (hace 1 día)
    k1 = db.query(SiteLicenseKey).filter(SiteLicenseKey.site_id == site_id, SiteLicenseKey.year == 1).first()
    k1.expires_at = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    db.commit()

    # Comprobar que ahora está bloqueado requiriendo Año 2
    status_y2_req = get_site_license_status(db, site_id)
    assert status_y2_req["is_allowed"] is False
    assert status_y2_req["status"] == "LOCKED_AWAITING_YEAR_2"
    assert status_y2_req["required_year"] == 2

    # Activar Año 2 con clave válida
    ok_y2, msg_y2, _ = activate_site_year_license(db, site_id, pwd_y2, admin_user)
    assert ok_y2 is True
    status_y2_ok = get_site_license_status(db, site_id)
    assert status_y2_ok["is_allowed"] is True
    assert status_y2_ok["status"] == "ACTIVE_YEAR_2"

    # Simular que Año 2 ha expirado
    k2 = db.query(SiteLicenseKey).filter(SiteLicenseKey.site_id == site_id, SiteLicenseKey.year == 2).first()
    k2.expires_at = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    db.commit()

    # Debe exigir Año 3
    status_y3_req = get_site_license_status(db, site_id)
    assert status_y3_req["is_allowed"] is False
    assert status_y3_req["status"] == "LOCKED_AWAITING_YEAR_3"
    assert status_y3_req["required_year"] == 3

    # Activar Año 3 con clave válida
    ok_y3, msg_y3, _ = activate_site_year_license(db, site_id, pwd_y3, admin_user)
    assert ok_y3 is True
    status_y3_ok = get_site_license_status(db, site_id)
    assert status_y3_ok["is_allowed"] is True
    assert status_y3_ok["status"] == "ACTIVE_YEAR_3"


def test_dev_mode_bypass(client, db, admin_user, supervisor_user):
    """
    Regla 5: Modo Desarrollador (DEV_MODE=True).
    Bypass total de restricciones de licencia, temporizadores y contraseñas.
    """
    settings.DEV_MODE = True
    site_id = "san-jose-guaviare"

    # Comprobar que en DEV_MODE el estado siempre es permitido
    status_info = get_site_license_status(db, site_id)
    assert status_info["is_allowed"] is True
    assert status_info["status"] == "DEV_BYPASS"
    assert status_info["is_dev_mode"] is True

    # Restaurar DEV_MODE para los demás tests
    settings.DEV_MODE = False


def test_web_license_view_and_activation(client, db, admin_user):
    """
    Valida la interfaz web /license con aislamiento estricto por sede:
    - En San Agustín solo aparece San Agustín.
    - En Calamar solo aparece Calamar.
    - La activación opera exclusivamente sobre la sede activa.
    """
    settings.DEV_MODE = False
    ensure_all_site_licenses_initialized(db)

    vault = load_or_create_developer_vault()
    pwd_y1_sanagustin = vault["sites"]["san-agustin"]["years"]["1"]["password"]
    pwd_y1_calamar = vault["sites"]["calamar"]["years"]["1"]["password"]

    # Simular sesión autenticada como Admin
    from app.auth import create_access_token
    token = create_access_token({"sub": admin_user.username})
    client.cookies.set("access_token", f"Bearer {token}")

    # 1. Administrador en San Agustín
    client.cookies.set("active_site", "san-agustin")
    resp_sanagustin = client.get("/license")
    assert resp_sanagustin.status_code == 200
    assert "Licenciamiento de Sede: San Agustín" in resp_sanagustin.text
    assert "Sede Activa: San Agustín" in resp_sanagustin.text
    # No deben existir pestañas selectoras a otras sedes
    assert "href=\"/license?site=calamar\"" not in resp_sanagustin.text
    assert "href=\"/license?site=el-retorno\"" not in resp_sanagustin.text

    # 2. Administrador en Calamar
    client.cookies.set("active_site", "calamar")
    resp_calamar = client.get("/license")
    assert resp_calamar.status_code == 200
    assert "Licenciamiento de Sede: Calamar" in resp_calamar.text
    assert "Sede Activa: Calamar" in resp_calamar.text
    assert "href=\"/license?site=san-agustin\"" not in resp_calamar.text

    # 3. POST /license/activate en Calamar con contraseña de Calamar
    resp_post = client.post(
        "/license/activate",
        data={"password_key": pwd_y1_calamar},
        follow_redirects=False
    )
    assert resp_post.status_code == 303
    assert "msg=" in resp_post.headers["location"]

    # Verificar que Calamar quedó activo
    status_calamar = get_site_license_status(db, "calamar")
    assert status_calamar["is_allowed"] is True
    assert status_calamar["status"] == "ACTIVE_YEAR_1"
