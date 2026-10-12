from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.license import LicenseActivate, LicenseStatusResponse
from app.services.auth_service import get_current_user, RoleChecker
from app.services.license_service import check_license_validity, get_active_license_payload, activate_license
from app.services.audit_service import create_audit_log

router = APIRouter(prefix="/api/license", tags=["Licenciamiento"])

@router.get("/status", response_model=LicenseStatusResponse)
def get_license_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene el estado de la licencia actual (Cualquier usuario autenticado).
    """
    payload = get_active_license_payload(db)
    active_users = db.query(User).filter(
        User.is_active == True,
        User.role != "Admin"
    ).count()
    
    if not payload:
        return {
            "is_active": False,
            "client": None,
            "expires": None,
            "max_users": 0,
            "active_users": active_users,
            "message": "No hay una licencia activa o la firma es inválida."
        }
        
    is_valid, reason = check_license_validity(db)
    
    return {
        "is_active": is_valid,
        "client": payload.get("client"),
        "expires": payload.get("expires"),
        "max_users": payload.get("max_users"),
        "active_users": active_users,
        "message": reason
    }

@router.post("/activate", response_model=dict)
def activate(
    license_in: LicenseActivate,
    db: Session = Depends(get_db),
    admin: User = Depends(RoleChecker(["Admin"]))
):
    """
    Activa una nueva licencia en el sistema (Solo Administrador).
    """
    payload = activate_license(db, license_in.license_key)
    
    create_audit_log(
        db,
        user_id=admin.id,
        username=admin.username,
        action="LICENSE_ACTIVATED",
        details={
            "client": payload.get("client"),
            "expires": payload.get("expires"),
            "max_users": payload.get("max_users")
        }
    )
    
    return {
        "status": "success",
        "message": "Licencia activada con éxito.",
        "details": payload
    }
