from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.user import User
from app.models.incident import Incident
from app.models.event import Event
from app.schemas.incident import IncidentCreate, IncidentResponse, IncidentUpdate
from app.services.auth_service import get_current_user
from app.services.license_service import verify_license_dependency
from app.services.audit_service import create_audit_log

router = APIRouter(prefix="/api/incidents", tags=["Incidentes"])

@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(
    incident_in: IncidentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Registra una nueva novedad o incidente (Cualquier usuario autenticado).
    Verifica licencia activa.
    """
    new_incident = Incident(
        title=incident_in.title,
        description=incident_in.description,
        priority=incident_in.priority,
        status="Abierto",
        created_by_id=current_user.id
    )
    db.add(new_incident)
    db.commit()
    db.refresh(new_incident)

    # Crear evento inicial en la línea de tiempo (timeline)
    creation_event = Event(
        incident_id=new_incident.id,
        user_id=current_user.id,
        event_type="CREATION",
        description=f"Incidente reportado por {current_user.username}."
    )
    db.add(creation_event)
    
    # Registro en la Auditoría General
    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="INCIDENT_CREATED",
        details={"incident_id": new_incident.id, "title": new_incident.title}
    )
    
    db.commit()
    return new_incident

@router.get("", response_model=List[IncidentResponse])
def get_incidents(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assigned_to_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Lista todos los incidentes con filtros opcionales.
    Verifica licencia activa.
    """
    query = db.query(Incident)
    if status:
        query = query.filter(Incident.status == status)
    if priority:
        query = query.filter(Incident.priority == priority)
    if assigned_to_id:
        query = query.filter(Incident.assigned_to_id == assigned_to_id)
        
    return query.all()

@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident_by_id(
    incident_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Obtiene el detalle de un incidente específico.
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incidente no encontrado."
        )
    return incident

@router.patch("/{incident_id}", response_model=IncidentResponse)
def update_incident(
    incident_id: int,
    incident_in: IncidentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Modifica un incidente.
    Restricción de Estado: Solo Supervisores y Admins pueden marcar como 'Cerrado'.
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incidente no encontrado."
        )

    changes = []
    
    # 1. Validar restricción de estado "Cerrado"
    if incident_in.status and incident_in.status != incident.status:
        if incident_in.status == "Cerrado" and current_user.role not in ["Admin", "Supervisor"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo los Supervisores y Administradores pueden cerrar incidentes."
            )
            
        old_status = incident.status
        incident.status = incident_in.status
        changes.append(f"status: {old_status} -> {incident_in.status}")
        
        # Registrar evento de cambio de estado
        db.add(Event(
            incident_id=incident.id,
            user_id=current_user.id,
            event_type="STATUS_CHANGE",
            description=f"Estado cambiado de '{old_status}' a '{incident_in.status}' por {current_user.username}."
        ))

    # 2. Validar asignación
    if incident_in.assigned_to_id is not None and incident_in.assigned_to_id != incident.assigned_to_id:
        # Verificar que el usuario asignado existe
        assignee = db.query(User).filter(User.id == incident_in.assigned_to_id).first()
        if not assignee:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El usuario asignado no existe."
            )
            
        old_assignee_id = incident.assigned_to_id
        incident.assigned_to_id = incident_in.assigned_to_id
        changes.append(f"assigned_to_id: {old_assignee_id} -> {incident_in.assigned_to_id}")
        
        db.add(Event(
            incident_id=incident.id,
            user_id=current_user.id,
            event_type="ASSIGNMENT",
            description=f"Incidente asignado a {assignee.username} por {current_user.username}."
        ))

    # 3. Aplicar otros campos (título, descripción, prioridad)
    if incident_in.title and incident_in.title != incident.title:
        incident.title = incident_in.title
        changes.append("title updated")
    if incident_in.description and incident_in.description != incident.description:
        incident.description = incident_in.description
        changes.append("description updated")
    if incident_in.priority and incident_in.priority != incident.priority:
        old_priority = incident.priority
        incident.priority = incident_in.priority
        changes.append(f"priority: {old_priority} -> {incident_in.priority}")
        db.add(Event(
            incident_id=incident.id,
            user_id=current_user.id,
            event_type="PRIORITY_CHANGE",
            description=f"Prioridad cambiada de '{old_priority}' a '{incident_in.priority}' por {current_user.username}."
        ))

    if changes:
        db.commit()
        db.refresh(incident)
        
        # Registrar en la Auditoría General
        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="INCIDENT_UPDATED",
            details={"incident_id": incident.id, "changes": changes}
        )
        db.commit()

    return incident
