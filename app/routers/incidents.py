import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.user import User
from app.models.incident import Incident
from app.models.device import Device
from app.models.event import Event
from fastapi.responses import Response
from app.schemas.incident import IncidentCreate, IncidentResponse, IncidentUpdate, PaginatedIncidentResponse, IncidentValidate
from app.services.auth_service import get_current_user
from app.services.license_service import verify_license_dependency
from app.services.audit_service import create_audit_log
from app.services.report_service import generate_validation_conformity_pdf
from app.utils.timezone import get_local_now

router = APIRouter(prefix="/api/incidents", tags=["Incidentes"])

@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(
    incident_in: IncidentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Registra una nueva novedad o incidente.
    Verifica licencia activa y genera ticket único con título automático.
    """
    if current_user.role == "Supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: El rol Supervisor tiene perfil de solo lectura y no puede registrar incidentes."
        )
    year = get_local_now().year
    count = db.query(Incident).filter(Incident.ticket_number.like(f"TKT-{year}-%")).count()
    ticket_number = f"TKT-{year}-{count + 1:04d}"
    while db.query(Incident).filter(Incident.ticket_number == ticket_number).first():
        count += 1
        ticket_number = f"TKT-{year}-{count + 1:04d}"

    fault_type = incident_in.fault_type or "Falla Menor"
    location_detail = incident_in.location_detail or "General"
    
    if incident_in.title and incident_in.title.strip():
        title = incident_in.title.strip()
    else:
        title = f"Mantenimiento Correctivo - {fault_type} - {location_detail}"

    resolved_device_id = incident_in.device_id
    if not resolved_device_id and location_detail:
        candidate_dev = (
            db.query(Device).filter(
                Device.sede == incident_in.sede,
                Device.location_detail.ilike(f"%{location_detail}%"),
                Device.device_type.ilike("%cámara%")
            ).first()
            or db.query(Device).filter(
                Device.sede == incident_in.sede,
                Device.location_detail.ilike(f"%{location_detail}%")
            ).first()
            or db.query(Device).filter(
                Device.location_detail.ilike(f"%{location_detail}%")
            ).first()
        )
        if candidate_dev:
            resolved_device_id = candidate_dev.id

    new_incident = Incident(
        ticket_number=ticket_number,
        title=title,
        description=incident_in.description,
        priority=incident_in.priority,
        fault_type=fault_type,
        location_detail=location_detail,
        sede=incident_in.sede,
        device_id=resolved_device_id,
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
        description=f"Ticket {ticket_number} reportado por {current_user.username}."
    )
    db.add(creation_event)
    
    # Registro en la Auditoría General
    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="INCIDENT_CREATED",
        details={"incident_id": new_incident.id, "ticket_number": ticket_number, "title": new_incident.title}
    )
    
    db.commit()
    return new_incident

@router.get("", response_model=PaginatedIncidentResponse)
def get_incidents(
    page: int = Query(1, ge=1, description="Número de página actual"),
    page_size: int = Query(20, ge=1, le=100, description="Cantidad de registros por página"),
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assigned_to_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Lista los incidentes con paginación obligatoria y filtros opcionales.
    Verifica licencia activa y retorna estructura estandarizada con metadatos.
    """
    query = db.query(Incident)
    if status:
        query = query.filter(Incident.status == status)
    if priority:
        query = query.filter(Incident.priority == priority)
    if assigned_to_id:
        query = query.filter(Incident.assigned_to_id == assigned_to_id)
        
    total = query.count()
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    offset = (page - 1) * page_size
    items = query.order_by(Incident.created_at.desc()).offset(offset).limit(page_size).all()

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    }

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

    if current_user.role == "Supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: El rol Supervisor tiene perfil de solo lectura y no puede modificar incidentes."
        )

    # Bloqueo de edición técnica si está en validación o ya validado
    if incident.status in ["Pendiente de Validación", "Validado / Conforme", "Conforme / Validado"] and current_user.role not in ["Admin", "Validador"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"La orden de trabajo {incident.ticket_code} se encuentra en estado '{incident.status}' y la edición técnica se encuentra bloqueada."
        )

    changes = []
    
    # 1. Validar cambio de estado y trazabilidad
    if incident_in.status and incident_in.status != incident.status:
        target_status = incident_in.status
        allowed_roles = ["Admin", "Supervisor", "Operario", "Responsable", "Empresa de Mantenimiento"]
        if target_status in ["Cerrado", "Pendiente de Validación"] and current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permisos para cerrar este incidente."
            )
            
        old_status = incident.status
        
        # Transición automática a Pendiente de Validación al marcar como completado/cerrado
        if target_status in ["Cerrado", "Pendiente de Validación"]:
            if old_status in ["Abierto", "Rechazado"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Debe iniciar primero la atención del ticket {incident.ticket_code} (estado 'En Proceso') antes de finalizar y remitir a validación."
                )
            resolved_root_cause = incident_in.root_cause or incident.root_cause
            resolved_solution = incident_in.solution or incident.solution
            if not resolved_root_cause or not resolved_solution:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Debe proporcionar el diagnóstico de causa raíz y la solución técnica aplicada para finalizar y remitir a validación."
                )
            target_status = "Pendiente de Validación"
            incident.status = "Pendiente de Validación"
            incident.validation_status = "Pendiente"
            incident.closed_at = get_local_now()
            incident.closed_by_id = current_user.id
            incident.root_cause = resolved_root_cause.strip()
            incident.solution = resolved_solution.strip()
            changes.append(f"status: {old_status} -> Pendiente de Validación")
            changes.append("root_cause and solution updated")
        else:
            incident.status = target_status
            changes.append(f"status: {old_status} -> {target_status}")
            if target_status == "En Proceso" and not incident.attended_at:
                incident.attended_at = get_local_now()
                if not incident.assigned_to_id:
                    incident.assigned_to_id = current_user.id
        
        # Registrar evento de cambio de estado
        desc_event = f"Estado cambiado de '{old_status}' a '{incident.status}' por {current_user.username}."
        if incident.status == "Pendiente de Validación":
            desc_event = f"Ticket finalizado por técnico {current_user.username} y remitido a Pendiente de Validación Policial."
        db.add(Event(
            incident_id=incident.id,
            user_id=current_user.id,
            event_type="STATUS_CHANGE",
            description=desc_event
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


@router.post("/{incident_id}/validate", response_model=IncidentResponse)
def validate_incident(
    incident_id: int,
    val_in: IncidentValidate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Dictamen formal del Validador sobre un incidente:
    - 'approve': Certifica conformidad técnica ('Validado / Conforme').
    - 'reject': Devuelve al equipo técnico con observaciones y tiempo cero ('Rechazado').
    """
    if current_user.role != "Validador":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un usuario con rol Validador (Policía Nacional) tiene permisos para revisar y validar órdenes de trabajo."
        )

    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incidente no encontrado."
        )

    now = get_local_now()

    if val_in.action == "approve":
        incident.status = "Validado / Conforme"
        incident.validation_status = "Conforme"
        incident.validator_id = current_user.id
        incident.validated_at = now
        incident.validation_notes = (
            val_in.validation_notes.strip()
            if val_in.validation_notes and val_in.validation_notes.strip()
            else "Trabajo verificado y aprobado formalmente conforme a los estándares técnicos."
        )

        badge_txt = f" (Placa #{current_user.badge_number})" if current_user.badge_number else ""
        db.add(Event(
            incident_id=incident.id,
            user_id=current_user.id,
            event_type="INCIDENT_VALIDATED",
            description=f"Ticket {incident.ticket_code} aprobado con visto bueno técnico y conformidad por Validador {current_user.full_name or current_user.username}{badge_txt}."
        ))

        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="INCIDENT_VALIDATED_API",
            details={
                "incident_id": incident.id,
                "ticket_code": incident.ticket_code,
                "validator": current_user.username,
                "badge_number": current_user.badge_number,
                "status": incident.status,
                "notes": incident.validation_notes
            }
        )
        db.commit()
        db.refresh(incident)
        return incident

    elif val_in.action == "reject":
        if not val_in.validation_notes or not val_in.validation_notes.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe especificar las observaciones técnicas de rechazo para la subsanación."
            )

        incident.status = "Rechazado"
        incident.validation_status = "Rechazado"
        incident.validator_id = current_user.id
        incident.validated_at = now
        incident.validation_notes = val_in.validation_notes.strip()
        incident.timer_reset_at = now  # TIEMPO CERO
        incident.closed_at = None     # Reabierto para corrección técnica
        if val_in.rejection_photo:
            incident.rejection_photo = val_in.rejection_photo

        badge_txt = f" (Placa #{current_user.badge_number})" if current_user.badge_number else ""
        db.add(Event(
            incident_id=incident.id,
            user_id=current_user.id,
            event_type="INCIDENT_REJECTED",
            description=f"Ticket {incident.ticket_code} rechazado y devuelto a subsanación técnica con tiempo cero por Validador {current_user.full_name or current_user.username}{badge_txt}. Obs: {(incident.validation_notes or '')[:100]}"
        ))

        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="INCIDENT_REJECTED_API",
            details={
                "incident_id": incident.id,
                "ticket_code": incident.ticket_code,
                "validator": current_user.username,
                "status": incident.status,
                "notes": incident.validation_notes,
                "rejection_photo": val_in.rejection_photo,
                "timer_reset": True
            }
        )
        db.commit()
        db.refresh(incident)
        return incident


@router.get("/{incident_id}/certificate.pdf")
def get_incident_certificate_pdf(
    incident_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """Descarga el Acta Oficial de Conformidad en PDF (Exclusivo: Admin, Validador, Supervisor)."""
    if current_user.role not in ["Admin", "Validador", "Supervisor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido: Solo Administrador, Validador y Supervisor pueden consultar el informe oficial."
        )

    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado.")

    if incident.status not in ["Validado / Conforme", "Conforme / Validado"] and incident.validation_status != "Conforme":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La orden aún no ha sido aprobada ni validada formalmente."
        )

    current_site = {"name": incident.sede or "General", "full_name": incident.sede or "Sede General"}
    validator_user = incident.validator or current_user
    pdf_bytes = generate_validation_conformity_pdf(
        item=incident,
        item_type="incident",
        validator=validator_user,
        current_site=current_site
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=Acta_Conformidad_{incident.ticket_code}.pdf"}
    )
