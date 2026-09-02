from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.token import Token
from app.utils.security import verify_password
from app.services.auth_service import create_access_token
from app.services.license_service import check_license_validity
from app.services.audit_service import create_audit_log

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])

@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Autenticación de usuario. Retorna un JWT de acceso.
    Nota: Los Administradores pueden iniciar sesión aun si la licencia no está activa
    para poder cargar una nueva licencia.
    """
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        create_audit_log(
            db,
            user_id=None,
            username=form_data.username,
            action="LOGIN_FAILED",
            details={"reason": "Credenciales inválidas"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        create_audit_log(
            db,
            user_id=user.id,
            username=user.username,
            action="LOGIN_FAILED",
            details={"reason": "Cuenta desactivada"}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta cuenta está desactivada."
        )

    # Validar licencia para usuarios que no sean Administradores
    if user.role != "Admin":
        is_valid, reason = check_license_validity(db)
        if not is_valid:
            create_audit_log(
                db,
                user_id=user.id,
                username=user.username,
                action="LOGIN_FAILED",
                details={"reason": f"Falta de licencia: {reason}"}
            )
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Acceso denegado. {reason}"
            )

    # Crear token
    access_token = create_access_token(data={"sub": user.username})
    
    create_audit_log(
        db,
        user_id=user.id,
        username=user.username,
        action="LOGIN_SUCCESS",
        details={"role": user.role}
    )
    
    return {"access_token": access_token, "token_type": "bearer"}
