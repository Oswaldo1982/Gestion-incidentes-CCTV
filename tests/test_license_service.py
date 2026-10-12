import datetime
import pytest
from fastapi import HTTPException

from app.utils.security import (
    get_password_hash,
    verify_password,
    generate_license_key,
    verify_license_key
)
from app.services.license_service import (
    get_active_license_payload,
    check_license_validity,
    activate_license
)
from app.models.license import License
from app.models.user import User
from app.config import settings


def test_password_hashing_and_verification():
    """Happy path y error cases para hashing con bcrypt."""
    pw = "CctvSecurePassword2026*"
    hashed = get_password_hash(pw)

    assert hashed != pw
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword123", hashed) is False
    assert verify_password("", hashed) is False


def test_license_signature_and_tampering():
    """Valida la generación de licencias con HMAC-SHA256 y detección de manipulaciones indebidas."""
    payload = {
        "client": "Alcaldía Municipal",
        "expires": "2028-12-31",
        "max_users": 20
    }
    key = generate_license_key(payload, settings.LICENSE_SECRET_KEY)
    assert "." in key

    # Verificación válida
    decoded = verify_license_key(key, settings.LICENSE_SECRET_KEY)
    assert decoded is not None
    assert decoded["client"] == "Alcaldía Municipal"
    assert decoded["max_users"] == 20

    # Clave con firma alterada
    parts = key.split(".")
    tampered_sig = parts[0] + ".abcdef1234567890badsignature"
    assert verify_license_key(tampered_sig, settings.LICENSE_SECRET_KEY) is None

    # Clave verificada con secreto erróneo
    assert verify_license_key(key, "wrong-secret-key-123") is None

    # Formato corrupto sin punto
    assert verify_license_key("corrupt_key_without_delimiter", settings.LICENSE_SECRET_KEY) is None


def test_activate_license_success(db):
    """Happy path: Activación exitosa de una nueva licencia en base de datos."""
    db.query(License).delete()
    payload = {
        "client": "Gobernación Guaviare",
        "expires": (datetime.datetime.utcnow() + datetime.timedelta(days=180)).strftime("%Y-%m-%d"),
        "max_users": 15
    }
    key = generate_license_key(payload, settings.LICENSE_SECRET_KEY)
    result = activate_license(db, key)

    assert result["client"] == "Gobernación Guaviare"
    assert result["max_users"] == 15

    # Comprobar en base de datos
    active_lic = db.query(License).filter(License.is_active == True).first()
    assert active_lic is not None
    assert active_lic.license_key == key


def test_activate_license_invalid_signature(db):
    """Error esperado: Intento de activar una clave inválida o alterada lanza HTTP 400."""
    with pytest.raises(HTTPException) as exc_info:
        activate_license(db, "fake.invalid.signature")
    assert exc_info.value.status_code == 400
    assert "firma válida" in exc_info.value.detail


def test_activate_license_expired(db):
    """Error esperado: Intento de activar una licencia vencida lanza HTTP 400."""
    payload = {
        "client": "Cliente Expirado",
        "expires": "2020-01-01",
        "max_users": 5
    }
    key = generate_license_key(payload, settings.LICENSE_SECRET_KEY)
    with pytest.raises(HTTPException) as exc_info:
        activate_license(db, key)
    assert exc_info.value.status_code == 400
    assert "ha expirado" in exc_info.value.detail


def test_check_license_validity_user_limit(db):
    """Límite de negocio: Valida que check_license_validity detecte el exceso de usuarios activos."""
    db.query(License).delete()
    # Licencia con límite de 2 usuarios estándar
    payload = {
        "client": "Sede Limitada",
        "expires": (datetime.datetime.utcnow() + datetime.timedelta(days=90)).strftime("%Y-%m-%d"),
        "max_users": 2
    }
    key = generate_license_key(payload, settings.LICENSE_SECRET_KEY)
    lic = License(license_key=key, is_active=True)
    db.add(lic)
    db.commit()

    # Agregar 3 usuarios activos no-Admin
    for i in range(3):
        u = User(
            username=f"user_limit_{i}",
            email=f"user{i}@test.com",
            hashed_password="hashed_pw",
            role="Operario",
            is_active=True
        )
        db.add(u)
    db.commit()

    is_valid, reason = check_license_validity(db)
    assert is_valid is False
    assert "Límite de usuarios excedido" in reason
