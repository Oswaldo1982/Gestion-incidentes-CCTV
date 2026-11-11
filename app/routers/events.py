from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.user import User
from app.models.incident import Incident
from app.models.maintenance import Maintenance
from app.models.event import Event
from app.schemas.event import EventCreate, EventResponse
from app.services.auth_service import get_current_user
from app.services.license_service import verify_license_dependency
from app.services.audit_service import create_audit_log

router = APIRouter(prefix="/api/events", tags=["Eventos / Timeline"])


@router.get("/incident/{incident_id}", response_model=List[EventResponse])
def get_incident_timeline(
    incident_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Obtiene el historial (timeline) completo de cambios y comentarios de un incidente.
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado.")
    
    events = (
        db.query(Event)
        .filter(Event.incident_id == incident_id)
        .order_by(Event.created_at.asc())
        .all()
    )
    return events


@router.post("/incident/{incident_id}/comment", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def add_incident_comment(
    incident_id: int,
    comment_in: EventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Agrega un comentario al timeline de un incidente (Cualquier usuario autenticado).
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado.")
    
    if incident.status in ["Cerrado", "Validado / Conforme", "Conforme / Validado"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pueden agregar comentarios a incidentes cerrados."
        )

    new_event = Event(
        incident_id=incident_id,
        user_id=current_user.id,
        event_type="COMMENT",
        description=f"[{current_user.username}]: {comment_in.description}"
    )
    db.add(new_event)
    
    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="INCIDENT_COMMENT_ADDED",
        details={"incident_id": incident_id}
    )
    
    db.commit()
    db.refresh(new_event)
    return new_event


@router.get("/maintenance/{maintenance_id}", response_model=List[EventResponse])
def get_maintenance_timeline(
    maintenance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Obtiene el historial (timeline) completo de cambios y comentarios de un mantenimiento.
    """
    maint = db.query(Maintenance).filter(Maintenance.id == maintenance_id).first()
    if not maint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mantenimiento no encontrado.")
    
    events = (
        db.query(Event)
        .filter(Event.maintenance_id == maintenance_id)
        .order_by(Event.created_at.asc())
        .all()
    )
    return events


@router.post("/maintenance/{maintenance_id}/comment", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def add_maintenance_comment(
    maintenance_id: int,
    comment_in: EventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Agrega un comentario al timeline de un mantenimiento (Cualquier usuario autenticado).
    """
    maint = db.query(Maintenance).filter(Maintenance.id == maintenance_id).first()
    if not maint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mantenimiento no encontrado.")
    
    if maint.status in ["Completado", "Cancelado", "Validado / Conforme", "Conforme / Validado"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se pueden agregar comentarios a mantenimientos en estado '{maint.status}'."
        )

    new_event = Event(
        maintenance_id=maintenance_id,
        user_id=current_user.id,
        event_type="COMMENT",
        description=f"[{current_user.username}]: {comment_in.description}"
    )
    db.add(new_event)
    
    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="MAINTENANCE_COMMENT_ADDED",
        details={"maintenance_id": maintenance_id}
    )
    
    db.commit()
    db.refresh(new_event)
    return new_event
