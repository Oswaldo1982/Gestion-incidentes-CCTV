import datetime
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status
from app.config import settings
from app.database import get_db
from app.models.license import License
from app.models.user import User
from app.utils.security import verify_license_key, generate_license_key

def get_active_license_payload(db: Session) -> dict | None:
    """
    Retrieves the active license from the database and verifies it.
    Returns the parsed payload if valid and active, else None.
    """
    db_license = db.query(License).filter(License.is_active == True).first()
    if not db_license:
        return None
    
    payload = verify_license_key(db_license.license_key, settings.LICENSE_SECRET_KEY)
    if not payload:
        return None
    
    # Check expiration date
    expires_str = payload.get("expires")
    if expires_str:
        try:
            expires_date = datetime.datetime.strptime(expires_str, "%Y-%m-%d")
            if datetime.datetime.utcnow() > expires_date:
                return None
        except ValueError:
            return None
            
    return payload

from app.services.site_license_service import get_site_license_status

def check_license_validity(db: Session, site_id: str | None = None) -> tuple[bool, str]:
    """
    Realiza la verificación de validez de la licencia:
    - Si DEV_MODE está activo, bypass total automático.
    - Si se especifica site_id, evalúa el estado del sitio (período de gracia 24h, año 1/2/3).
    - Mantiene compatibilidad con el modelo de licencia legacy.
    """
    if settings.DEV_MODE:
        return True, "Modo desarrollador activo (DEV_MODE=True). Todas las restricciones están desactivadas."

    if site_id:
        status_info = get_site_license_status(db, site_id)
        return status_info["is_allowed"], status_info["message"]

    # Comprobar si existe licencia por sitio activa (cualquiera de los 4 sitios)
    from app.models.license import SiteLicenseKey
    active_site_lic = db.query(SiteLicenseKey).filter(SiteLicenseKey.is_activated == True).first()
    if active_site_lic:
        return True, "Licencia multi-sede activa y válida."

    payload = get_active_license_payload(db)
    if not payload:
        return False, "Licencia no encontrada, inválida o expirada."
    
    # Validate user counts
    max_users = payload.get("max_users", 0)
    active_users = db.query(User).filter(
        User.is_active == True,
        User.role != "Admin"
    ).count()
    
    if active_users > max_users:
        return False, f"Límite de usuarios excedido ({active_users}/{max_users})."
        
    return True, "Licencia activa y válida."

def verify_user_limit(db: Session) -> dict:
    """
    Verifica si agregar o reactivar un usuario supera el límite criptográfico 'max_users'.
    Lanza HTTPException si se supera el límite o no hay licencia activa.
    En DEV_MODE, permite usuarios ilimitados.
    """
    if settings.DEV_MODE:
        return {"client": "Modo Desarrollador", "max_users": 99999}

    payload = get_active_license_payload(db)
    if not payload:
        # Si hay licencias de sitio activas, otorgar capacidad estándar
        from app.models.license import SiteLicenseKey
        if db.query(SiteLicenseKey).filter(SiteLicenseKey.is_activated == True).first():
            return {"client": "Institucional Multi-Sede", "max_users": 100}
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="No hay una licencia activa en el sistema. Debe activar una licencia primero."
        )
    max_users = payload.get("max_users", 0)
    active_users = db.query(User).filter(User.is_active == True, User.role != "Admin").count()
    if active_users >= max_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Límite de usuarios activos de la licencia excedido ({active_users}/{max_users})."
        )
    return payload

def verify_license_dependency(db: Session = Depends(get_db)) -> dict:
    """
    Dependency helper to raise exception if license is invalid.
    En DEV_MODE retorna payload inmediato sin bloqueos.
    """
    if settings.DEV_MODE:
        return {"client": "Modo Desarrollador", "is_dev_mode": True}

    is_valid, reason = check_license_validity(db)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=reason
        )
    payload = get_active_license_payload(db)
    return payload or {"client": "Institucional Multi-Sede", "is_active": True}

def activate_license(db: Session, license_key: str) -> dict:
    """
    Validates a license key and stores it as the active license in the DB.
    """
    # 1. Verify key structure and signature first
    payload = verify_license_key(license_key, settings.LICENSE_SECRET_KEY)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La clave de licencia provista no tiene una firma válida."
        )
    
    # 2. Check expiration date
    expires_str = payload.get("expires")
    if expires_str:
        try:
            expires_date = datetime.datetime.strptime(expires_str, "%Y-%m-%d")
            if datetime.datetime.utcnow() > expires_date:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La licencia ingresada ya ha expirado."
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato de fecha de expiración inválido en la licencia."
            )
            
    # 3. Deactivate old licenses
    db.query(License).update({License.is_active: False})
    
    # 4. Insert new license
    new_license = License(
        license_key=license_key,
        is_active=True
    )
    db.add(new_license)
    db.commit()
    db.refresh(new_license)
    
    return payload

def generate_dev_license(expires_days: int = 365, max_users: int = 5) -> str:
    """
    Utility helper to generate a local license for dev/testing.
    """
    expiry_date = (datetime.datetime.utcnow() + datetime.timedelta(days=expires_days)).strftime("%Y-%m-%d")
    payload = {
        "client": "Desarrollo Local",
        "expires": expiry_date,
        "max_users": max_users
    }
    return generate_license_key(payload, settings.LICENSE_SECRET_KEY)
