from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.auth_service import RoleChecker, get_current_user
from app.services.license_service import get_active_license_payload
from app.services.audit_service import create_audit_log
from app.utils.security import get_password_hash

router = APIRouter(prefix="/api/users", tags=["Gestión de Usuarios"])

# Requiere ser Administrador
admin_required = RoleChecker(["Admin"])

def verify_user_limit(db: Session):
    """
    Checks if adding another active user exceeds the license limits.
    """
    payload = get_active_license_payload(db)
    if not payload:
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

@router.get("", response_model=List[UserResponse])
def get_users(
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required)
):
    """
    Lista todos los usuarios registrados (Solo Administrador).
    """
    return db.query(User).all()

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required)
):
    """
    Crea un nuevo usuario (Solo Administrador).
    Valida el límite de usuarios activos según la licencia.
    """
    # Verificar si el usuario ya existe
    existing_user = db.query(User).filter(
        (User.username == user_in.username) | (User.email == user_in.email)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario o correo electrónico ya está registrado."
        )
    
    # Si el usuario a crear va a estar activo y no es Admin, verificar el límite de la licencia
    if user_in.is_active and user_in.role != "Admin":
        verify_user_limit(db)
        
    hashed_pw = get_password_hash(user_in.password)
    new_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hashed_pw,
        role=user_in.role,
        is_active=user_in.is_active
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    create_audit_log(
        db,
        user_id=admin.id,
        username=admin.username,
        action="USER_CREATED",
        details={"created_user": new_user.username, "role": new_user.role}
    )
    
    return new_user

@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required)
):
    """
    Modifica un usuario existente o desactiva su cuenta (Solo Administrador).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado."
        )
        
    # Impedir que un administrador se desactive a sí mismo
    if user.id == admin.id and user_in.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta de administrador."
        )

    # Si se está activando la cuenta, verificar el límite de la licencia
    if user_in.is_active is True and not user.is_active and user.role != "Admin":
        verify_user_limit(db)
        
    # Aplicar cambios
    update_data = user_in.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"]:
        user.hashed_password = get_password_hash(update_data["password"])
        del update_data["password"]
        
    for key, value in update_data.items():
        setattr(user, key, value)
        
    db.commit()
    db.refresh(user)
    
    create_audit_log(
        db,
        user_id=admin.id,
        username=admin.username,
        action="USER_UPDATED",
        details={"updated_user": user.username, "changes": list(update_data.keys())}
    )
    
    return user
