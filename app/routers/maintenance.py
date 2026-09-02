import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.user import User
from app.models.maintenance import Maintenance
from app.models.event import Event
from app.schemas.maintenance import MaintenanceCreate, MaintenanceResponse, MaintenanceUpdate
from app.services.auth_service import get_current_user, RoleChecker
from app.services.license_service import verify_license_dependency
from app.services.audit_service import create_audit_log

router = APIRouter(prefix="/api/maintenance", tags=["Mantenimientos"])

# Para crear/modificar programaciones se requiere Supervisor o Admin
supervisor_or_admin = RoleChecker(["Admin", "Supervisor"])

@router.post("", response_model=MaintenanceResponse, status_code=status.HTTP_201_CREATED)
def create_maintenance(
    maint_in: MaintenanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(supervisor_or_admin),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Programa un nuevo mantenimiento preventivo o correctivo (Supervisores y Administradores).
    Verifica licencia activa.
    """
    new_maint = Maintenance(
        type=maint_in.type,
        title=maint_in.title,
        description=maint_in.description,
        scheduled_date=maint_in.scheduled_date,
        incident_id=maint_in.incident_id,
        status="Programado",
        created_by_id=current_user.id
    )
    db.add(new_maint)
    db.commit()
    db.refresh(new_maint)

    # Evento de creación
    db.add(Event(
        maintenance_id=new_maint.id,
        user_id=current_user.id,
        event_type="CREATION",
        description=f"Mantenimiento programado como {new_maint.type} por {current_user.username}."
    ))

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="MAINTENANCE_CREATED",
        details={"maintenance_id": new_maint.id, "type": new_maint.type, "title": new_maint.title}
    )
    
    db.commit()
    return new_maint

@router.get("", response_model=List[MaintenanceResponse])
def get_maintenances(
    type: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Lista todos los mantenimientos con filtros.
    """
    query = db.query(Maintenance)
    if type:
        query = query.filter(Maintenance.type == type)
    if status:
        query = query.filter(Maintenance.status == status)
        
    return query.all()

@router.get("/{maintenance_id}", response_model=MaintenanceResponse)
def get_maintenance_by_id(
    maintenance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Obtiene el detalle de un mantenimiento.
    """
    maint = db.query(Maintenance).filter(Maintenance.id == maintenance_id).first()
    if not maint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mantenimiento no encontrado."
        )
    return maint

@router.patch("/{maintenance_id}", response_model=MaintenanceResponse)
def update_maintenance(
    maintenance_id: int,
    maint_in: MaintenanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Modifica un mantenimiento.
    Restricción de Estado: Solo Supervisores y Admins pueden marcar como 'Completado' o 'Cancelado'.
    """
    maint = db.query(Maintenance).filter(Maintenance.id == maintenance_id).first()
    if not maint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mantenimiento no encontrado."
        )

    changes = []
    
    # 1. Validar restricción de estado Completado/Cancelado
    if maint_in.status and maint_in.status != maint.status:
        if maint_in.status in ["Completado", "Cancelado"] and current_user.role not in ["Admin", "Supervisor"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Solo los Supervisores y Administradores pueden cambiar el estado a '{maint_in.status}'."
            )
            
        old_status = maint.status
        maint.status = maint_in.status
        changes.append(f"status: {old_status} -> {maint_in.status}")
        
        # Si se completa, asignar fecha de completado
        if maint_in.status == "Completado":
            maint.completed_date = datetime.datetime.utcnow()
            changes.append("completed_date: set to now")
            
        db.add(Event(
            maintenance_id=maint.id,
            user_id=current_user.id,
            event_type="STATUS_CHANGE",
            description=f"Estado de mantenimiento cambiado de '{old_status}' a '{maint_in.status}' por {current_user.username}."
        ))

    # 2. Aplicar otros campos
    if maint_in.title and maint_in.title != maint.title:
        maint.title = maint_in.title
        changes.append("title updated")
    if maint_in.description and maint_in.description != maint.description:
        maint.description = maint_in.description
        changes.append("description updated")
    if maint_in.scheduled_date and maint_in.scheduled_date != maint.scheduled_date:
        old_date = maint.scheduled_date
        maint.scheduled_date = maint_in.scheduled_date
        changes.append(f"scheduled_date: {old_date} -> {maint_in.scheduled_date}")
    if maint_in.incident_id is not None and maint_in.incident_id != maint.incident_id:
        maint.incident_id = maint_in.incident_id
        changes.append(f"incident_id: {maint.incident_id} -> {maint_in.incident_id}")

    if changes:
        db.commit()
        db.refresh(maint)
        
        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="MAINTENANCE_UPDATED",
            details={"maintenance_id": maint.id, "changes": changes}
        )
        db.commit()

    return maint
