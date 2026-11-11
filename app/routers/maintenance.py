import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.user import User
from app.models.maintenance import Maintenance
from app.models.event import Event
from app.schemas.maintenance import MaintenanceCreate, MaintenanceResponse, MaintenanceUpdate, MaintenanceValidate
from app.services.auth_service import get_current_user, RoleChecker
from app.services.license_service import verify_license_dependency
from app.services.audit_service import create_audit_log
from app.services.report_service import generate_validation_conformity_pdf
from app.utils.timezone import get_local_now

router = APIRouter(prefix="/api/maintenance", tags=["Mantenimientos"])

# Para crear programaciones se requiere Admin o Empresa de Mantenimiento
admin_or_tech = RoleChecker(["Admin", "Empresa de Mantenimiento"])
validator_only = RoleChecker(["Validador"])

@router.post("", response_model=MaintenanceResponse, status_code=status.HTTP_201_CREATED)
def create_maintenance(
    maint_in: MaintenanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_or_tech),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Programa un nuevo mantenimiento preventivo (Administradores y Técnicos).
    Verifica licencia activa.
    """
    sched_dt = maint_in.scheduled_date
    if sched_dt.tzinfo is not None:
        sched_dt = sched_dt.replace(tzinfo=None)
    if sched_dt.date() < get_local_now().date():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permite programar una inspección rutinaria o un mantenimiento preventivo con fecha anterior a la fecha actual."
        )

    # Generar protocol_code si no viene especificado
    protocol_code = maint_in.protocol_code
    if not protocol_code:
        year = get_local_now().year
        count = db.query(Maintenance).filter(Maintenance.protocol_code.like(f"MP-{year}-%")).count()
        protocol_code = f"MP-{year}-{count + 1:04d}"

    new_maint = Maintenance(
        type=maint_in.type,
        protocol_code=protocol_code,
        title=maint_in.title or f"Mantenimiento {maint_in.type} - {protocol_code}",
        description=maint_in.description,
        scheduled_date=maint_in.scheduled_date,
        sede=maint_in.sede,
        location_detail=maint_in.location_detail,
        device_id=maint_in.device_id,
        incident_id=maint_in.incident_id,
        maintenance_type=maint_in.maintenance_type or "Preventivo Mensual",
        priority=maint_in.priority or "Media",
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
        description=f"Protocolo preventivo {protocol_code} programado como {new_maint.type} por {current_user.username}."
    ))

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="MAINTENANCE_CREATED",
        details={"maintenance_id": new_maint.id, "type": new_maint.type, "protocol_code": protocol_code, "title": new_maint.title}
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
    Restricción de Estado: Cualquier Admin o Técnico de mantenimiento (Admin, Supervisor, Operario, Responsable) puede ejecutar o completar.
    """
    maint = db.query(Maintenance).filter(Maintenance.id == maintenance_id).first()
    if not maint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mantenimiento no encontrado."
        )

    if current_user.role == "Supervisor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: El rol Supervisor tiene perfil de solo lectura y no puede modificar mantenimientos."
        )

    # 0. Bloqueo de edición técnica si está pendiente de validación o validado conforme
    if maint.status in ["Pendiente de Validación", "Validado / Conforme", "Conforme / Validado"] and current_user.role not in ["Admin", "Validador"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"La orden de trabajo está en estado '{maint.status}' y la edición técnica se encuentra bloqueada."
        )

    changes = []
    allowed_closing_roles = ["Admin", "Empresa de Mantenimiento", "Operario", "Responsable"]
    
    # 1. Validar restricción de estado Completado/Pendiente de Validación/Cancelado
    if maint_in.status and maint_in.status != maint.status:
        target_status = maint_in.status
        # Si el técnico marca como terminado/completado, la orden pasa a Pendiente de Validación
        if target_status == "Completado":
            target_status = "Pendiente de Validación"

        if target_status in ["Pendiente de Validación", "Cancelado"] and current_user.role not in allowed_closing_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Solo los perfiles técnicos y administradores pueden cambiar el estado a '{target_status}'."
            )
            
        old_status = maint.status
        maint.status = target_status
        changes.append(f"status: {old_status} -> {target_status}")
        
        # Si pasa a Pendiente de Validación, registrar fecha de finalización y técnico
        if target_status == "Pendiente de Validación":
            maint.completed_date = get_local_now()
            maint.completed_by_id = current_user.id
            maint.validation_status = "Pendiente"
            changes.append("completed_date: set to now, validation_status: Pendiente")
        elif target_status == "En Ejecución" and not maint.execution_date:
            maint.execution_date = get_local_now()
            changes.append("execution_date: set to now")
            
        db.add(Event(
            maintenance_id=maint.id,
            user_id=current_user.id,
            event_type="STATUS_CHANGE",
            description=f"Estado de mantenimiento cambiado de '{old_status}' a '{target_status}' por {current_user.username}."
        ))

    # 2. Aplicar otros campos
    if maint_in.title and maint_in.title != maint.title:
        maint.title = maint_in.title
        changes.append("title updated")
    if maint_in.description and maint_in.description != maint.description:
        maint.description = maint_in.description
        changes.append("description updated")
    if maint_in.scheduled_date and maint_in.scheduled_date != maint.scheduled_date:
        sched_dt = maint_in.scheduled_date
        if sched_dt.tzinfo is not None:
            sched_dt = sched_dt.replace(tzinfo=None)
        if sched_dt.date() < get_local_now().date():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se permite programar una inspección rutinaria o un mantenimiento preventivo con fecha anterior a la fecha actual."
            )
        old_date = maint.scheduled_date
        maint.scheduled_date = maint_in.scheduled_date
        changes.append(f"scheduled_date: {old_date} -> {maint_in.scheduled_date}")
    if maint_in.incident_id is not None and maint_in.incident_id != maint.incident_id:
        maint.incident_id = maint_in.incident_id
        changes.append(f"incident_id: {maint.incident_id} -> {maint_in.incident_id}")
    if maint_in.location_detail is not None:
        maint.location_detail = maint_in.location_detail
    if maint_in.device_id is not None:
        maint.device_id = maint_in.device_id
    if maint_in.priority is not None:
        maint.priority = maint_in.priority
    if maint_in.maintenance_type is not None:
        maint.maintenance_type = maint_in.maintenance_type
    if maint_in.checklist_results is not None:
        maint.checklist_results = maint_in.checklist_results
    if maint_in.technical_findings is not None:
        maint.technical_findings = maint_in.technical_findings
    if maint_in.actions_taken is not None:
        maint.actions_taken = maint_in.actions_taken
    if maint_in.recommendations is not None:
        maint.recommendations = maint_in.recommendations

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


@router.post("/{maintenance_id}/validate", response_model=MaintenanceResponse)
def validate_maintenance(
    maintenance_id: int,
    val_in: MaintenanceValidate,
    db: Session = Depends(get_db),
    current_user: User = Depends(validator_only),
    license_payload: dict = Depends(verify_license_dependency)
):
    """
    Dictamen formal del Validador sobre una orden de mantenimiento:
    - 'approve': Certifica conformidad técnica ('Conforme / Validado').
    - 'reject': Devuelve al técnico con observaciones para su subsanación ('Rechazado').
    """
    maint = db.query(Maintenance).filter(Maintenance.id == maintenance_id).first()
    if not maint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mantenimiento no encontrado."
        )

    now = get_local_now()

    if val_in.action == "approve":
        maint.status = "Validado / Conforme"
        maint.validation_status = "Conforme"
        maint.validator_id = current_user.id
        maint.validated_at = now
        maint.validation_notes = (
            val_in.validation_notes.strip()
            if val_in.validation_notes and val_in.validation_notes.strip()
            else "Trabajo revisado y validado formalmente conforme a los estándares técnicos."
        )

        db.add(Event(
            maintenance_id=maint.id,
            user_id=current_user.id,
            event_type="MAINTENANCE_VALIDATED",
            description=f"Protocolo {maint.code} aprobado con visto bueno técnico por {current_user.full_name or current_user.username}."
        ))

        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="MAINTENANCE_VALIDATED",
            details={
                "maintenance_id": maint.id,
                "protocol_code": maint.code,
                "validator": current_user.username,
                "status": maint.status,
                "notes": maint.validation_notes
            }
        )
    elif val_in.action == "reject":
        if not val_in.validation_notes or not val_in.validation_notes.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe proporcionar las observaciones técnicas de rechazo para devolver la orden al contratista."
            )

        maint.status = "Rechazado"
        maint.validation_status = "Rechazado"
        maint.validator_id = current_user.id
        maint.validated_at = now
        maint.validation_notes = val_in.validation_notes.strip()
        maint.timer_reset_at = now  # TIEMPO CERO
        maint.scheduled_date = now   # Reactivado desde cero
        maint.completed_date = None  # Reabierto para subsanación técnica

        db.add(Event(
            maintenance_id=maint.id,
            user_id=current_user.id,
            event_type="MAINTENANCE_REJECTED",
            description=f"Protocolo {maint.code} devuelto a subsanación técnica con tiempo cero por {current_user.full_name or current_user.username}. Obs: {(maint.validation_notes or '')[:100]}"
        ))

        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="MAINTENANCE_REJECTED",
            details={
                "maintenance_id": maint.id,
                "protocol_code": maint.code,
                "validator": current_user.username,
                "status": maint.status,
                "notes": maint.validation_notes,
                "timer_reset": True
            }
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Acción no válida. Utilice 'approve' o 'reject'."
        )

    db.commit()
    db.refresh(maint)
    return maint


@router.get("/{maintenance_id}/certificate.pdf")
def get_maintenance_certificate_pdf(
    maintenance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_payload: dict = Depends(verify_license_dependency)
):
    """Descarga el Acta Oficial de Conformidad en PDF para un mantenimiento (Exclusivo: Admin, Validador, Supervisor)."""
    if current_user.role not in ["Admin", "Validador", "Supervisor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido: Solo Administrador, Validador y Supervisor pueden consultar el informe oficial."
        )

    maint = db.query(Maintenance).filter(Maintenance.id == maintenance_id).first()
    if not maint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mantenimiento no encontrado.")

    if not maint.is_validated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La orden preventiva aún no ha sido aprobada ni validada formalmente."
        )

    current_site = {"name": maint.sede or "General", "full_name": maint.sede or "Sede General"}
    validator_user = maint.validator or db.query(User).filter(User.role == "Validador").first() or current_user
    pdf_bytes = generate_validation_conformity_pdf(
        item=maint,
        item_type="maintenance",
        validator=validator_user,
        current_site=current_site
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=Acta_Conformidad_{maint.code}.pdf"}
    )
