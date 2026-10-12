"""
Servicio de Sincronización y Garantía de Homogeneidad Multi-Sede.
Garantiza que la lógica, estructura de inventario, protocolos de mantenimiento e incidentes
registrados en San Agustín se encuentren siempre reflejados y disponibles de manera idéntica
y contextualizada en las cuatro sedes territoriales:
1. San Agustín (Huila)
2. San José del Guaviare (Guaviare)
3. El Retorno (Guaviare)
4. Calamar (Guaviare)
"""
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.device import Device
from app.models.incident import Incident
from app.models.maintenance import Maintenance
from app.models.user import User


# Configuración canónica de las 4 Sedes Territoriales
TARGET_SITES: List[Dict[str, Any]] = [
    {
        "id": "san-agustin",
        "name": "San Agustín",
        "full_name": "San Agustín (Huila)",
        "code_prefix": "SA"
    },
    {
        "id": "san-jose-guaviare",
        "name": "San José del Guaviare",
        "full_name": "San José del Guaviare (Guaviare)",
        "code_prefix": "SJG"
    },
    {
        "id": "el-retorno",
        "name": "El Retorno",
        "full_name": "El Retorno (Guaviare)",
        "code_prefix": "RET"
    },
    {
        "id": "calamar",
        "name": "Calamar",
        "full_name": "Calamar (Guaviare)",
        "code_prefix": "CAL"
    }
]


def get_canonical_site_filter(model_cls, current_site: Dict[str, Any]):
    """
    Construye condiciones OR exhaustivas para filtrar registros por la sede/municipio activo
    garantizando aislamiento y coincidencia insensible a tildes o variaciones de nombre.
    """
    site_id = current_site.get("id", "")
    site_name = current_site.get("name", "")
    site_full = current_site.get("full_name", "")

    keywords = set()
    if site_name:
        keywords.add(site_name)
    if site_full:
        keywords.add(site_full)

    # Variaciones específicas por municipio para garantizar match al 100%
    if "san-agustin" in site_id or "agustin" in site_name.lower() or "agustín" in site_name.lower():
        keywords.update(["San Agustín", "San Agustin", "San Agustín (Huila)", "San Agustin (Huila)"])
    elif "guaviare" in site_id or "josé" in site_name.lower() or "jose" in site_name.lower():
        keywords.update([
            "San José del Guaviare", "San Jose del Guaviare",
            "San José del Guaviare (Guaviare)", "San Jose del Guaviare (Guaviare)",
            "San José", "San Jose"
        ])
    elif "retorno" in site_id or "retorno" in site_name.lower():
        keywords.update(["El Retorno", "El Retorno (Guaviare)", "Retorno"])
    elif "calamar" in site_id or "calamar" in site_name.lower():
        keywords.update(["Calamar", "Calamar (Guaviare)"])

    conds = []
    for kw in keywords:
        conds.append(model_cls.sede == kw)
        conds.append(model_cls.sede.ilike(f"%{kw}%"))

    return or_(*conds)


def find_matching_device_in_site(
    db: Session,
    ref_device: Optional[Device],
    target_site_full_name: str
) -> Optional[Device]:
    """
    Localiza en la sede destino el equipo equivalente al de referencia
    (por nombre, tipo de equipo o ubicación física en ese municipio).
    """
    if not ref_device:
        return None

    # 1. Búsqueda exacta por nombre y sede destino
    match = db.query(Device).filter(
        Device.sede == target_site_full_name,
        Device.name == ref_device.name
    ).first()
    if match:
        return match

    # 2. Búsqueda por ubicación y tipo
    match = db.query(Device).filter(
        Device.sede == target_site_full_name,
        Device.location_detail == ref_device.location_detail,
        Device.device_type == ref_device.device_type
    ).first()
    if match:
        return match

    # 3. Búsqueda por tipo de equipo en la sede
    match = db.query(Device).filter(
        Device.sede == target_site_full_name,
        Device.device_type == ref_device.device_type
    ).first()
    if match:
        return match

    # 4. Fallback al primer equipo disponible de esa sede
    return db.query(Device).filter(Device.sede == target_site_full_name).first()


def ensure_all_sites_synchronized(db: Session) -> Dict[str, Any]:
    """
    Garantiza que la lógica, inventario de equipos y contenidos operativos (incidentes y mantenimientos)
    estén simétricamente reflejados y sincronizados en las 4 sedes territoriales.
    Si una sede carece de registros homólogos a los de la sede de referencia, los genera
    y asocia a sus propios equipos locales.
    """
    results = {
        "devices_synced": 0,
        "incidents_synced": 0,
        "maintenances_synced": 0
    }

    # Sede de referencia principal: San Agustín
    ref_site_full = "San Agustín (Huila)"

    # 1. Obtener incidentes y mantenimientos de referencia
    ref_incidents = db.query(Incident).filter(
        or_(
            Incident.sede == ref_site_full,
            Incident.sede.ilike("%San Agust%")
        )
    ).all()

    ref_maintenances = db.query(Maintenance).filter(
        or_(
            Maintenance.sede == ref_site_full,
            Maintenance.sede.ilike("%San Agust%")
        )
    ).all()

    # Usuario admin y validador por defecto para auditoría
    default_admin = db.query(User).filter(User.role == "Admin").first()
    admin_id = default_admin.id if default_admin else 1
    default_validador = db.query(User).filter(User.role == "Validador").first()
    validador_id = default_validador.id if default_validador else None

    # Las 3 sedes destino a sincronizar
    other_sites = [s for s in TARGET_SITES if s["full_name"] != ref_site_full]

    for site in other_sites:
        site_full = site["full_name"]
        prefix = site["code_prefix"]

        # A. Sincronización de Incidentes Correctivos
        existing_inc_count = db.query(Incident).filter(
            or_(
                Incident.sede == site_full,
                Incident.sede.ilike(f"%{site['name']}%")
            )
        ).count()

        if existing_inc_count < len(ref_incidents):
            for ref_inc in ref_incidents:
                # Generar ticket correlativo para la sede
                target_ticket = f"TKT-{prefix}-{ref_inc.id:04d}" if ref_inc.id else f"TKT-{prefix}-0001"
                existing = db.query(Incident).filter(
                    Incident.sede == site_full,
                    Incident.title == ref_inc.title
                ).first()

                if not existing:
                    # Mapear dispositivo en la sede destino
                    target_dev = find_matching_device_in_site(db, ref_inc.device, site_full)
                    target_dev_id = target_dev.id if target_dev else None

                    # Clonar incidente adaptado a la sede
                    cloned_inc = Incident(
                        ticket_number=target_ticket,
                        title=ref_inc.title,
                        description=ref_inc.description,
                        priority=ref_inc.priority,
                        fault_type=ref_inc.fault_type,
                        location_detail=ref_inc.location_detail,
                        sede=site_full,
                        device_id=target_dev_id,
                        image_path=ref_inc.image_path,
                        closing_image_path=ref_inc.closing_image_path,
                        root_cause=ref_inc.root_cause,
                        solution=ref_inc.solution,
                        status=ref_inc.status,
                        created_by_id=ref_inc.created_by_id or admin_id,
                        assigned_to_id=ref_inc.assigned_to_id or admin_id,
                        closed_by_id=ref_inc.closed_by_id,
                        closed_at=ref_inc.closed_at,
                        attended_at=ref_inc.attended_at,
                        validator_id=ref_inc.validator_id,
                        validated_at=ref_inc.validated_at,
                        validation_status=ref_inc.validation_status,
                        validation_notes=ref_inc.validation_notes,
                        created_at=ref_inc.created_at or datetime.datetime.utcnow(),
                        updated_at=ref_inc.updated_at or datetime.datetime.utcnow()
                    )
                    db.add(cloned_inc)
                    results["incidents_synced"] += 1

        # B. Sincronización de Mantenimientos Preventivos
        existing_maint_count = db.query(Maintenance).filter(
            or_(
                Maintenance.sede == site_full,
                Maintenance.sede.ilike(f"%{site['name']}%")
            )
        ).count()

        if existing_maint_count < len(ref_maintenances):
            for ref_m in ref_maintenances:
                target_code = f"MP-{prefix}-{ref_m.id:04d}" if ref_m.id else f"MP-{prefix}-0001"
                existing_m = db.query(Maintenance).filter(
                    Maintenance.sede == site_full,
                    Maintenance.title == ref_m.title
                ).first()

                if not existing_m:
                    target_dev = find_matching_device_in_site(db, ref_m.device, site_full)
                    target_dev_id = target_dev.id if target_dev else None

                    cloned_maint = Maintenance(
                        protocol_code=target_code,
                        type=ref_m.type,
                        maintenance_type=ref_m.maintenance_type,
                        title=ref_m.title,
                        description=ref_m.description,
                        scheduled_date=ref_m.scheduled_date,
                        execution_date=ref_m.execution_date,
                        completed_date=ref_m.completed_date,
                        status=ref_m.status,
                        sede=site_full,
                        location_detail=ref_m.location_detail,
                        priority=ref_m.priority,
                        device_id=target_dev_id,
                        image_path=ref_m.image_path,
                        completion_photo=ref_m.completion_photo,
                        checklist_results=ref_m.checklist_results,
                        technical_findings=ref_m.technical_findings,
                        actions_taken=ref_m.actions_taken,
                        recommendations=ref_m.recommendations,
                        created_by_id=ref_m.created_by_id or admin_id,
                        completed_by_id=ref_m.completed_by_id,
                        validator_id=ref_m.validator_id,
                        validated_at=ref_m.validated_at,
                        validation_status=ref_m.validation_status,
                        validation_notes=ref_m.validation_notes,
                        created_at=ref_m.created_at or datetime.datetime.utcnow()
                    )
                    db.add(cloned_maint)
                    results["maintenances_synced"] += 1

    db.commit()
    return results
