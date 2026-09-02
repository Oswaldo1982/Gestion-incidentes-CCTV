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

def check_license_validity(db: Session) -> tuple[bool, str]:
    """
    Performs full validity checks and returns (is_valid, reason).
    """
    payload = get_active_license_payload(db)
    if not payload:
        return False, "Licencia no encontrada, inválida o expirada."
    
    # Validate user counts
    max_users = payload.get("max_users", 0)
    # Count active non-Admin users (or all active users).
    # Since Superadmin is seeded, usually max_users applies to normal accounts, but let's count all active users for simplicity, or all normal users. Let's count normal active users (Supervisor, Responsable).
    active_users = db.query(User).filter(
        User.is_active == True,
        User.role != "Admin"
    ).count()
    
    if active_users > max_users:
        return False, f"Límite de usuarios excedido ({active_users}/{max_users})."
        
    return True, "Licencia activa y válida."

def verify_license_dependency(db: Session = Depends(get_db)) -> dict:
    """
    Dependency helper to raise exception if license is invalid.
    """
    is_valid, reason = check_license_validity(db)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=reason
        )
    return get_active_license_payload(db)

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
