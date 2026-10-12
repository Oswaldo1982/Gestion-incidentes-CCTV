import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.auth_service import RoleChecker
from app.services.license_service import get_active_license_payload, verify_user_limit
from app.services.audit_service import create_audit_log
from app.utils.security import get_password_hash
from app.auth import is_password_already_in_use

router = APIRouter(prefix="/api/users", tags=["Gestión de Usuarios"])

# Requiere ser Administrador
admin_required = RoleChecker(["Admin"])

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
    Valida el límite de usuarios activos según la licencia y asigna cambio obligatorio de contraseña (vigencia 24h).
    """
    # 1. Regla de Arquitectura: Estrictamente un (1) Administrador Principal en todo el sistema
    if user_in.role == "Admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No es posible registrar administradores adicionales. Únicamente puede existir un (1) Administrador Principal en todo el sistema."
        )

    # 2. Roles Operativos Permitidos gestionados por el Administrador
    valid_operational_roles = ["Validador", "Supervisor", "Empresa de Mantenimiento", "Operario", "Responsable"]
    if user_in.role not in valid_operational_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rol no válido. El Administrador Principal gestiona exclusivamente: Validador, Supervisor o Empresa de Mantenimiento."
        )

    # Validación específica para Validador: Número de placa policial obligatorio y estrictamente numérico
    clean_badge = user_in.badge_number.strip() if user_in.badge_number else None
    if user_in.role == "Validador":
        if not clean_badge:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El número de placa policial es obligatorio para el rol Validador."
            )
        if not clean_badge.isdigit():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El número de placa policial debe contener únicamente dígitos numéricos."
            )
        if db.query(User).filter(User.badge_number == clean_badge).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El número de placa policial ya se encuentra registrado para otro usuario."
            )
    elif clean_badge:
        if db.query(User).filter(User.badge_number == clean_badge).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El número de placa policial ya se encuentra registrado para otro usuario."
            )

    # Verificar si el usuario ya existe por nombre de usuario o correo
    existing_user = db.query(User).filter(
        (User.username == user_in.username) | (User.email == user_in.email)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario o correo electrónico ya está registrado."
        )

    # Verificar si el documento de identidad (cédula) ya existe
    if user_in.document_id and user_in.document_id.strip():
        clean_doc = user_in.document_id.strip()
        if db.query(User).filter(User.document_id == clean_doc).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El número de documento de identidad (cédula) ya se encuentra registrado para otro usuario."
            )

    # Verificar si la contraseña ya está en uso en el sistema
    if is_password_already_in_use(user_in.password, db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña ingresada ya se encuentra registrada en el sistema para otro usuario. Debe proporcionar una contraseña única."
        )
    
    # Si el usuario a crear va a estar activo y no es Admin, verificar el límite de la licencia
    if user_in.is_active and user_in.role != "Admin":
        verify_user_limit(db)
        
    hashed_pw = get_password_hash(user_in.password)
    temp_expires = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    new_user = User(
        username=user_in.username,
        email=user_in.email,
        full_name=user_in.full_name,
        document_id=user_in.document_id,
        badge_number=clean_badge,
        assigned_site=user_in.assigned_site,
        hashed_password=hashed_pw,
        role=user_in.role,
        is_active=user_in.is_active,
        must_change_password=True,  # Cambio obligatorio en primer ingreso (24h)
        temp_expires_at=temp_expires
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    create_audit_log(
        db,
        user_id=admin.id,
        username=admin.username,
        action="USER_CREATED",
        details={
            "created_user": new_user.username,
            "role": new_user.role,
            "badge_number": new_user.badge_number,
            "assigned_site": new_user.assigned_site,
            "temp_expires_at": temp_expires.isoformat()
        }
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

    # Impedir desactivar la cuenta del Administrador Principal
    if (user.id == 1 or user.username == "admin") and user_in.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cuenta del Administrador Principal no puede ser desactivada."
        )

    # Si se está activando la cuenta, verificar el límite de la licencia
    if user_in.is_active is True and not user.is_active and user.role != "Admin":
        verify_user_limit(db)
        
    # Aplicar cambios
    update_data = user_in.model_dump(exclude_unset=True)

    # Validar restricción de rol único de Superadmin
    if "role" in update_data and update_data["role"]:
        if update_data["role"] == "Admin" and user.role != "Admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No es posible asignar el rol Administrador. Únicamente puede existir un (1) Administrador Principal en todo el sistema."
            )
        if (user.id == 1 or user.username == "admin") and update_data["role"] != "Admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El rol del Administrador Principal no puede ser modificado."
            )

    # Validar documento de identidad si se está actualizando
    if "document_id" in update_data and update_data["document_id"]:
        clean_doc = str(update_data["document_id"]).strip()
        existing_doc = db.query(User).filter(User.document_id == clean_doc, User.id != user_id).first()
        if existing_doc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El número de documento de identidad (cédula) ya se encuentra registrado para otro usuario."
            )

    # Validar número de placa policial si se está actualizando
    if "badge_number" in update_data and update_data["badge_number"]:
        clean_badge = str(update_data["badge_number"]).strip()
        effective_role = update_data.get("role", user.role)
        if effective_role == "Validador" and not clean_badge.isdigit():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El número de placa policial debe contener únicamente dígitos numéricos."
            )
        existing_badge = db.query(User).filter(User.badge_number == clean_badge, User.id != user_id).first()
        if existing_badge:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El número de placa policial ya se encuentra registrado para otro usuario."
            )
        update_data["badge_number"] = clean_badge

    # Validar contraseña si se está actualizando
    if "password" in update_data and update_data["password"]:
        if is_password_already_in_use(update_data["password"], db, exclude_user_id=user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La nueva contraseña ya se encuentra registrada en el sistema para otro usuario. Debe proporcionar una contraseña única."
            )
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

@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required)
):
    """
    Elimina un usuario del sistema (Solo Administrador).
    """
    if admin.role != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un Administrador puede eliminar cuentas de usuario."
        )

    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminar tu propia cuenta de administrador."
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado."
        )

    if user_id == 1 or user.username == 'admin':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La cuenta del Administrador Inicial del sistema no puede ser eliminada."
        )

    username = user.username

    # Reasignar referencias en Incident, Maintenance y Event
    from app.models.incident import Incident
    from app.models.maintenance import Maintenance
    from app.models.event import Event

    db.query(Incident).filter(Incident.created_by_id == user_id).update({"created_by_id": admin.id})
    db.query(Incident).filter(Incident.assigned_to_id == user_id).update({"assigned_to_id": None})
    db.query(Maintenance).filter(Maintenance.created_by_id == user_id).update({"created_by_id": admin.id})
    db.query(Event).filter(Event.user_id == user_id).update({"user_id": admin.id})

    db.delete(user)
    db.commit()

    create_audit_log(
        db,
        user_id=admin.id,
        username=admin.username,
        action="USER_DELETED",
        details={"deleted_user_id": user_id, "deleted_username": username}
    )

    return {"message": f"Usuario {username} eliminado exitosamente."}
