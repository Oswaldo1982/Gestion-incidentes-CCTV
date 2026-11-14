import os
import json
import logging
import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.user import User
from app.models.device import Device
from app.models.incident import Incident
from app.models.maintenance import Maintenance
from app.models.event import Event
from app.models.site import Site
from app.models.license import License, SiteLicenseKey, SiteActivationState
from app.auth import get_password_hash
from app.utils.timezone import get_local_now

logger = logging.getLogger("seed_loader")


def parse_dt(val: Any) -> Optional[datetime.datetime]:
    if not val or not isinstance(val, str):
        return val if isinstance(val, datetime.datetime) else None
    try:
        return datetime.datetime.fromisoformat(val)
    except Exception:
        return None


def ensure_golden_data_seeded(db: Session) -> bool:
    """
    Garantiza que la base de datos persistente (PostgreSQL en Railway o SQLite en local)
    contenga el catálogo completo y original de usuarios, sedes, equipos, incidentes y mantenimientos
    (tanto para San Agustín como para el Sitio de Prueba / Demo).

    REGLAS ESTRICTAS DE INTEGRIDAD:
    1. NUNCA ejecuta DELETE sobre ninguna tabla. Los datos creados por el usuario permanecen seguros.
    2. Cada entidad se procesa de forma individual (por registro) con su propio commit/rollback para evitar
       que un conflicto en una fila aborte la siembra de los demás registros.
    3. Carga sin excepción los 20 tickets de incidente y 20 de mantenimiento del Demo.
    4. En PostgreSQL actualiza automáticamente el tamaño de columnas (VARCHAR 100) y las secuencias seriales.
    """
    seed_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seeds", "golden_seed.json")
    if not os.path.exists(seed_file):
        logger.warning(f"[!] Archivo de semillas no encontrado en: {seed_file}")
        return False

    try:
        with open(seed_file, "r", encoding="utf-8") as f:
            golden_data = json.load(f)
    except Exception as e:
        logger.error(f"[!] Error leyendo {seed_file}: {e}")
        return False

    # 0. En PostgreSQL: Asegurar tipos de columnas VARCHAR(100) y sincronizar secuencias al inicio
    try:
        bind = db.get_bind()
        if bind and bind.dialect.name == "postgresql":
            alter_queries = [
                "ALTER TABLE incidents ALTER COLUMN status TYPE VARCHAR(100);",
                "ALTER TABLE incidents ALTER COLUMN priority TYPE VARCHAR(50);",
                "ALTER TABLE maintenances ALTER COLUMN status TYPE VARCHAR(100);",
                "ALTER TABLE maintenances ALTER COLUMN priority TYPE VARCHAR(50);",
                "ALTER TABLE maintenances ALTER COLUMN type TYPE VARCHAR(50);",
                "ALTER TABLE devices ALTER COLUMN status TYPE VARCHAR(50);"
            ]
            for q in alter_queries:
                try:
                    db.execute(text(q))
                    db.commit()
                except Exception:
                    db.rollback()

            tables_with_id = [
                "users", "licenses", "site_licenses", "site_activation_states",
                "devices", "incidents", "maintenances", "events"
            ]
            for tbl in tables_with_id:
                try:
                    db.execute(text(f"""
                        SELECT setval(
                            pg_get_serial_sequence('{tbl}', 'id'),
                            COALESCE((SELECT MAX(id) FROM {tbl}), 1) + 1,
                            false
                        );
                    """))
                    db.commit()
                except Exception:
                    db.rollback()
    except Exception as e:
        logger.warning(f"Aviso en configuración inicial postgres: {e}")

    # 1. Sembrar Licencia Maestra si no existe
    try:
        existing_license = db.query(License).first()
        if not existing_license and golden_data.get("licenses"):
            lic_data = golden_data["licenses"][0]
            db.add(License(
                id=lic_data.get("id", 1),
                license_key=lic_data.get("license_key"),
                is_active=bool(lic_data.get("is_active", 1)),
                activated_at=parse_dt(lic_data.get("activated_at")) or get_local_now()
            ))
            db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Aviso sembrando licencia: {e}")

    # 2. Sembrar Sedes Oficiales (por registro)
    for s in golden_data.get("sites", []):
        try:
            existing_site = db.query(Site).filter(Site.id == s["id"]).first()
            if not existing_site:
                db.add(Site(
                    id=s["id"],
                    name=s["name"],
                    full_name=s.get("full_name", s["name"]),
                    region=s.get("region", ""),
                    badge=s.get("badge", ""),
                    description=s.get("description", ""),
                    icon=s.get("icon", "🏛️"),
                    cameras_count=s.get("cameras_count", 0),
                    status=s.get("status", "Operativo"),
                    color=s.get("color", "blue"),
                    default_supervisor=s.get("default_supervisor", ""),
                    is_active=bool(s.get("is_active", 1))
                ))
                db.commit()
        except Exception as e:
            db.rollback()
            logger.debug(f"Aviso sembrando sede {s.get('id')}: {e}")

    # 3. Sembrar Usuarios (San Agustín y Demo) - inserción segura por registro
    for u in golden_data.get("users", []):
        uname = u.get("username")
        if not uname:
            continue
        try:
            existing_u = db.query(User).filter(User.username == uname).first()
            if existing_u:
                continue
        except Exception:
            db.rollback()
            continue

        uid = u.get("id")
        user_kwargs: Dict[str, Any] = {
            "username": uname,
            "email": u.get("email", uname),
            "full_name": u.get("full_name", uname),
            "document_id": u.get("document_id", "0000000000"),
            "assigned_site": u.get("assigned_site", "Todas las Sedes"),
            "hashed_password": u.get("hashed_password") or get_password_hash("admin123"),
            "role": u.get("role", "Admin"),
            "is_active": bool(u.get("is_active", 1)),
            "must_change_password": bool(u.get("must_change_password", 0)),
            "temp_expires_at": parse_dt(u.get("temp_expires_at")),
            "badge_number": u.get("badge_number"),
            "signature_path": u.get("signature_path"),
            "is_executive_signatory": bool(u.get("is_executive_signatory", 0)),
            "is_deleted": bool(u.get("is_deleted", 0)),
            "deleted_at": parse_dt(u.get("deleted_at")),
            "created_at": parse_dt(u.get("created_at")) or get_local_now()
        }

        try:
            # Intentar con ID explícito si está libre
            if uid and not db.query(User).filter(User.id == uid).first():
                user_kwargs["id"] = uid

            db.add(User(**user_kwargs))
            db.commit()
        except Exception:
            db.rollback()
            try:
                # Reintentar sin id explícito si hubo colisión de clave primaria
                user_kwargs.pop("id", None)
                db.add(User(**user_kwargs))
                db.commit()
            except Exception as e_user2:
                db.rollback()
                logger.warning(f"Aviso sembrando usuario {uname}: {e_user2}")

    # 4. Sembrar Licenciamiento Multi-Sede (por registro)
    for sl in golden_data.get("site_licenses", []):
        try:
            cert = sl.get("certificate_code")
            if cert and not db.query(SiteLicenseKey).filter(SiteLicenseKey.certificate_code == cert).first():
                db.add(SiteLicenseKey(
                    site_id=sl.get("site_id"),
                    site_name=sl.get("site_name"),
                    year=sl.get("year", 1),
                    password_hash=sl.get("password_hash"),
                    password_mask=sl.get("password_mask"),
                    certificate_code=cert,
                    is_activated=bool(sl.get("is_activated", 0)),
                    activated_at=parse_dt(sl.get("activated_at")),
                    expires_at=parse_dt(sl.get("expires_at")),
                    created_at=parse_dt(sl.get("created_at")) or get_local_now()
                ))
                db.commit()
        except Exception:
            db.rollback()

    for sa in golden_data.get("site_activation_states", []):
        try:
            sid = sa.get("site_id")
            if sid and not db.query(SiteActivationState).filter(SiteActivationState.site_id == sid).first():
                db.add(SiteActivationState(
                    site_id=sid,
                    first_access_at=parse_dt(sa.get("first_access_at")),
                    current_year=sa.get("current_year", 1),
                    status=sa.get("status", "ACTIVE"),
                    failed_attempts=sa.get("failed_attempts", 0),
                    lockout_until=parse_dt(sa.get("lockout_until")),
                    last_activated_at=parse_dt(sa.get("last_activated_at")),
                    updated_at=parse_dt(sa.get("updated_at")) or get_local_now()
                ))
                db.commit()
        except Exception:
            db.rollback()

    # 5. Sembrar Equipos (Devices) faltantes (por registro)
    for d in golden_data.get("devices", []):
        did = d.get("id")
        dname = d.get("name")
        dsede = d.get("sede")
        try:
            existing_dev = None
            if did:
                existing_dev = db.query(Device).filter(Device.id == did).first()
            if not existing_dev and dname and dsede:
                existing_dev = db.query(Device).filter(Device.name == dname, Device.sede == dsede).first()

            if existing_dev:
                continue
        except Exception:
            db.rollback()
            continue

        device_kwargs: Dict[str, Any] = {
            "name": dname,
            "device_type": d.get("device_type"),
            "brand": d.get("brand"),
            "model": d.get("model"),
            "serial_number": d.get("serial_number"),
            "ip_address": d.get("ip_address"),
            "mac_address": d.get("mac_address"),
            "sede": dsede,
            "location_detail": d.get("location_detail"),
            "status": d.get("status", "Operativo"),
            "created_at": parse_dt(d.get("created_at")) or get_local_now()
        }

        try:
            if did and not db.query(Device).filter(Device.id == did).first():
                device_kwargs["id"] = did

            db.add(Device(**device_kwargs))
            db.commit()
        except Exception:
            db.rollback()
            try:
                device_kwargs.pop("id", None)
                db.add(Device(**device_kwargs))
                db.commit()
            except Exception as e_dev2:
                db.rollback()
                logger.warning(f"Aviso sembrando equipo {dname}: {e_dev2}")

    # 6. Sembrar Incidentes faltantes (San Agustín y Demo) - por registro individual
    for inc in golden_data.get("incidents", []):
        iid = inc.get("id")
        ticket_num = inc.get("ticket_number")
        isede = inc.get("sede")
        try:
            existing_inc = None
            if iid:
                existing_inc = db.query(Incident).filter(Incident.id == iid).first()
            if not existing_inc and ticket_num and isede:
                existing_inc = db.query(Incident).filter(
                    Incident.ticket_number == ticket_num,
                    Incident.sede == isede
                ).first()

            if existing_inc:
                continue
        except Exception:
            db.rollback()
            continue

        inc_kwargs: Dict[str, Any] = {
            "title": inc.get("title") or f"Incidente {ticket_num}",
            "description": inc.get("description") or "Descripción del incidente",
            "status": inc.get("status", "Abierto"),
            "priority": inc.get("priority", "Media"),
            "created_by_id": inc.get("created_by_id", 1),
            "assigned_to_id": inc.get("assigned_to_id"),
            "created_at": parse_dt(inc.get("created_at")) or get_local_now(),
            "updated_at": parse_dt(inc.get("updated_at")) or get_local_now(),
            "sede": isede,
            "image_path": inc.get("image_path"),
            "device_id": inc.get("device_id"),
            "ticket_number": ticket_num,
            "fault_type": inc.get("fault_type", "Falla Menor"),
            "location_detail": inc.get("location_detail"),
            "root_cause": inc.get("root_cause"),
            "solution": inc.get("solution"),
            "closed_by_id": inc.get("closed_by_id"),
            "attended_at": parse_dt(inc.get("attended_at")),
            "closed_at": parse_dt(inc.get("closed_at")),
            "closing_image_path": inc.get("closing_image_path"),
            "validator_id": inc.get("validator_id"),
            "validated_at": parse_dt(inc.get("validated_at")),
            "validation_status": inc.get("validation_status"),
            "validation_notes": inc.get("validation_notes"),
            "rejection_photo": inc.get("rejection_photo"),
            "timer_reset_at": parse_dt(inc.get("timer_reset_at"))
        }

        try:
            # Validar que foreign keys indispensables existan para evitar violación FK
            if inc_kwargs.get("device_id") and not db.query(Device).filter(Device.id == inc_kwargs["device_id"]).first():
                inc_kwargs["device_id"] = None

            if inc_kwargs.get("created_by_id") and not db.query(User).filter(User.id == inc_kwargs["created_by_id"]).first():
                inc_kwargs["created_by_id"] = 1

            if inc_kwargs.get("assigned_to_id") and not db.query(User).filter(User.id == inc_kwargs["assigned_to_id"]).first():
                inc_kwargs["assigned_to_id"] = None

            if inc_kwargs.get("validator_id") and not db.query(User).filter(User.id == inc_kwargs["validator_id"]).first():
                inc_kwargs["validator_id"] = None

            if inc_kwargs.get("closed_by_id") and not db.query(User).filter(User.id == inc_kwargs["closed_by_id"]).first():
                inc_kwargs["closed_by_id"] = None

            if iid and not db.query(Incident).filter(Incident.id == iid).first():
                inc_kwargs["id"] = iid

            db.add(Incident(**inc_kwargs))
            db.commit()
        except Exception:
            db.rollback()
            try:
                inc_kwargs.pop("id", None)
                db.add(Incident(**inc_kwargs))
                db.commit()
            except Exception as e_inc2:
                db.rollback()
                logger.warning(f"Aviso sembrando incidente {ticket_num}: {e_inc2}")

    # 7. Sembrar Mantenimientos faltantes (San Agustín y Demo) - por registro individual
    for m in golden_data.get("maintenances", []):
        mid = m.get("id")
        protocol_code = m.get("protocol_code")
        msede = m.get("sede")
        try:
            existing_m = None
            if mid:
                existing_m = db.query(Maintenance).filter(Maintenance.id == mid).first()
            if not existing_m and protocol_code and msede:
                existing_m = db.query(Maintenance).filter(
                    Maintenance.protocol_code == protocol_code,
                    Maintenance.sede == msede
                ).first()

            if existing_m:
                continue
        except Exception:
            db.rollback()
            continue

        maint_kwargs: Dict[str, Any] = {
            "type": m.get("type", "Preventivo"),
            "title": m.get("title") or f"Mantenimiento {protocol_code}",
            "description": m.get("description", "Mantenimiento preventivo programado"),
            "scheduled_date": parse_dt(m.get("scheduled_date")) or get_local_now(),
            "completed_date": parse_dt(m.get("completed_date")),
            "status": m.get("status", "Programado"),
            "sede": msede,
            "image_path": m.get("image_path"),
            "device_id": m.get("device_id"),
            "incident_id": m.get("incident_id"),
            "created_by_id": m.get("created_by_id", 1),
            "created_at": parse_dt(m.get("created_at")) or get_local_now(),
            "protocol_code": protocol_code,
            "maintenance_type": m.get("maintenance_type", "Preventivo Mensual"),
            "location_detail": m.get("location_detail"),
            "priority": m.get("priority", "Media"),
            "checklist_results": m.get("checklist_results"),
            "technical_findings": m.get("technical_findings"),
            "actions_taken": m.get("actions_taken"),
            "recommendations": m.get("recommendations"),
            "execution_date": parse_dt(m.get("execution_date")),
            "completed_by_id": m.get("completed_by_id"),
            "completion_photo": m.get("completion_photo"),
            "validator_id": m.get("validator_id"),
            "validated_at": parse_dt(m.get("validated_at")),
            "validation_status": m.get("validation_status"),
            "validation_notes": m.get("validation_notes"),
            "rejection_photo": m.get("rejection_photo"),
            "timer_reset_at": parse_dt(m.get("timer_reset_at")),
            "rca_cause_factor": m.get("rca_cause_factor"),
            "rca_failure_mechanism": m.get("rca_failure_mechanism"),
            "operating_condition": m.get("operating_condition"),
            "asset_component": m.get("asset_component")
        }

        try:
            # Validar foreign keys
            if maint_kwargs.get("device_id") and not db.query(Device).filter(Device.id == maint_kwargs["device_id"]).first():
                maint_kwargs["device_id"] = None

            if maint_kwargs.get("incident_id") and not db.query(Incident).filter(Incident.id == maint_kwargs["incident_id"]).first():
                maint_kwargs["incident_id"] = None

            if maint_kwargs.get("created_by_id") and not db.query(User).filter(User.id == maint_kwargs["created_by_id"]).first():
                maint_kwargs["created_by_id"] = 1

            if maint_kwargs.get("completed_by_id") and not db.query(User).filter(User.id == maint_kwargs["completed_by_id"]).first():
                maint_kwargs["completed_by_id"] = None

            if maint_kwargs.get("validator_id") and not db.query(User).filter(User.id == maint_kwargs["validator_id"]).first():
                maint_kwargs["validator_id"] = None

            if mid and not db.query(Maintenance).filter(Maintenance.id == mid).first():
                maint_kwargs["id"] = mid

            db.add(Maintenance(**maint_kwargs))
            db.commit()
        except Exception:
            db.rollback()
            try:
                maint_kwargs.pop("id", None)
                db.add(Maintenance(**maint_kwargs))
                db.commit()
            except Exception as e_m2:
                db.rollback()
                logger.warning(f"Aviso sembrando mantenimiento {protocol_code}: {e_m2}")

    # 8. Sembrar Eventos de Trazabilidad faltantes (por registro)
    for ev in golden_data.get("events", []):
        eid = ev.get("id")
        try:
            if eid and db.query(Event).filter(Event.id == eid).first():
                continue

            inc_id = ev.get("incident_id")
            maint_id = ev.get("maintenance_id")

            # Solo insertar si el incidente o mantenimiento referenciado existe
            if inc_id and not db.query(Incident).filter(Incident.id == inc_id).first():
                continue
            if maint_id and not db.query(Maintenance).filter(Maintenance.id == maint_id).first():
                continue

            u_id = ev.get("user_id")
            if u_id and not db.query(User).filter(User.id == u_id).first():
                u_id = 1

            event_kwargs: Dict[str, Any] = {
                "incident_id": inc_id,
                "maintenance_id": maint_id,
                "user_id": u_id,
                "event_type": ev.get("event_type", "LOG"),
                "description": ev.get("description", ""),
                "created_at": parse_dt(ev.get("created_at")) or get_local_now()
            }
            if eid and not db.query(Event).filter(Event.id == eid).first():
                event_kwargs["id"] = eid

            db.add(Event(**event_kwargs))
            db.commit()
        except Exception:
            db.rollback()

    # 9. En PostgreSQL: Sincronizar secuencias serial al final
    try:
        bind = db.get_bind()
        if bind and bind.dialect.name == "postgresql":
            tables_with_id = [
                "users", "licenses", "site_licenses", "site_activation_states",
                "devices", "incidents", "maintenances", "events"
            ]
            for tbl in tables_with_id:
                try:
                    db.execute(text(f"""
                        SELECT setval(
                            pg_get_serial_sequence('{tbl}', 'id'),
                            COALESCE((SELECT MAX(id) FROM {tbl}), 1) + 1,
                            false
                        );
                    """))
                    db.commit()
                except Exception:
                    db.rollback()
    except Exception as e:
        logger.warning(f"Aviso final en secuencias postgres: {e}")

    logger.info("[*] Verificación y siembra de catálogo completada exitosamente.")
    return True
