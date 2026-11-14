import os
import json
import logging
import datetime
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

logger = logging.getLogger("seed_loader")


def parse_dt(val):
    if not val or not isinstance(val, str):
        return val
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
    2. Cada entidad se procesa en bloques aislados con su propio commit/rollback para evitar
       que un conflicto en una tabla (ej. id duplicado de usuario) aborte la siembra de incidentes o mantenimientos.
    3. Carga sin excepción los 20 tickets de incidente y 20 de mantenimiento del Demo.
    4. En PostgreSQL actualiza automáticamente las secuencias autoincrementales.
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

    # 1. Sembrar Licencia Maestra si no existe
    try:
        existing_license = db.query(License).first()
        if not existing_license and golden_data.get("licenses"):
            lic_data = golden_data["licenses"][0]
            db.add(License(
                id=lic_data.get("id", 1),
                license_key=lic_data.get("license_key"),
                is_active=bool(lic_data.get("is_active", 1)),
                activated_at=parse_dt(lic_data.get("activated_at")) or datetime.datetime.utcnow()
            ))
            db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Aviso sembrando licencia: {e}")

    # 2. Sembrar Sedes Oficiales
    try:
        existing_site_ids = {s.id for s in db.query(Site.id).all()}
        for s in golden_data.get("sites", []):
            if s["id"] not in existing_site_ids:
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
                existing_site_ids.add(s["id"])
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Aviso sembrando sedes: {e}")

    # 3. Sembrar Usuarios (San Agustín y Demo)
    try:
        existing_usernames = {u.username for u in db.query(User.username).all()}
        existing_user_ids = {u.id for u in db.query(User.id).all()}
        for u in golden_data.get("users", []):
            uname = u["username"]
            if uname not in existing_usernames:
                uid = u.get("id")
                kwargs = {
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
                    "created_at": parse_dt(u.get("created_at")) or datetime.datetime.utcnow()
                }
                # Solo asignar id explícito si no está ocupado
                if uid and uid not in existing_user_ids:
                    kwargs["id"] = uid
                    existing_user_ids.add(uid)
                db.add(User(**kwargs))
                existing_usernames.add(uname)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Aviso sembrando usuarios: {e}")

    # 4. Sembrar Licenciamiento Multi-Sede
    try:
        if db.query(SiteLicenseKey).count() == 0 and golden_data.get("site_licenses"):
            for sl in golden_data["site_licenses"]:
                db.add(SiteLicenseKey(
                    id=sl.get("id"),
                    site_id=sl.get("site_id"),
                    site_name=sl.get("site_name"),
                    year=sl.get("year", 1),
                    password_hash=sl.get("password_hash"),
                    password_mask=sl.get("password_mask"),
                    certificate_code=sl.get("certificate_code"),
                    is_activated=bool(sl.get("is_activated", 0)),
                    activated_at=parse_dt(sl.get("activated_at")),
                    expires_at=parse_dt(sl.get("expires_at")),
                    created_at=parse_dt(sl.get("created_at")) or datetime.datetime.utcnow()
                ))
            db.commit()

        if db.query(SiteActivationState).count() == 0 and golden_data.get("site_activation_states"):
            for sa in golden_data["site_activation_states"]:
                db.add(SiteActivationState(
                    id=sa.get("id"),
                    site_id=sa.get("site_id"),
                    first_access_at=parse_dt(sa.get("first_access_at")),
                    current_year=sa.get("current_year", 1),
                    status=sa.get("status", "ACTIVE"),
                    failed_attempts=sa.get("failed_attempts", 0),
                    lockout_until=parse_dt(sa.get("lockout_until")),
                    last_activated_at=parse_dt(sa.get("last_activated_at")),
                    updated_at=parse_dt(sa.get("updated_at")) or datetime.datetime.utcnow()
                ))
            db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Aviso sembrando licencias multi-sede: {e}")

    # 5. Sembrar Equipos (Devices) faltantes
    try:
        existing_dev_ids = {row[0] for row in db.query(Device.id).all()}
        for d in golden_data.get("devices", []):
            did = d.get("id")
            kwargs = {
                "name": d.get("name"),
                "device_type": d.get("device_type"),
                "brand": d.get("brand"),
                "model": d.get("model"),
                "serial_number": d.get("serial_number"),
                "ip_address": d.get("ip_address"),
                "mac_address": d.get("mac_address"),
                "sede": d.get("sede"),
                "location_detail": d.get("location_detail"),
                "status": d.get("status", "Operativo"),
                "created_at": parse_dt(d.get("created_at")) or datetime.datetime.utcnow()
            }
            if did and did not in existing_dev_ids:
                kwargs["id"] = did
                existing_dev_ids.add(did)
                db.add(Device(**kwargs))
            elif not did:
                db.add(Device(**kwargs))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Aviso sembrando equipos: {e}")

    # 6. Sembrar Incidentes faltantes (San Agustín y Demo)
    try:
        existing_inc_ids = {row[0] for row in db.query(Incident.id).all()}
        for inc in golden_data.get("incidents", []):
            iid = inc.get("id")
            kwargs = {
                "title": inc.get("title"),
                "description": inc.get("description"),
                "status": inc.get("status", "Abierto"),
                "priority": inc.get("priority", "Media"),
                "created_by_id": inc.get("created_by_id"),
                "assigned_to_id": inc.get("assigned_to_id"),
                "created_at": parse_dt(inc.get("created_at")) or datetime.datetime.utcnow(),
                "updated_at": parse_dt(inc.get("updated_at")) or datetime.datetime.utcnow(),
                "sede": inc.get("sede"),
                "image_path": inc.get("image_path"),
                "device_id": inc.get("device_id"),
                "ticket_number": inc.get("ticket_number"),
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
            if iid and iid not in existing_inc_ids:
                kwargs["id"] = iid
                existing_inc_ids.add(iid)
                db.add(Incident(**kwargs))
            elif not iid:
                db.add(Incident(**kwargs))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Aviso sembrando incidentes: {e}")

    # 7. Sembrar Mantenimientos faltantes (San Agustín y Demo)
    try:
        existing_maint_ids = {row[0] for row in db.query(Maintenance.id).all()}
        for m in golden_data.get("maintenances", []):
            mid = m.get("id")
            kwargs = {
                "type": m.get("type", "Preventivo"),
                "title": m.get("title"),
                "description": m.get("description", "Mantenimiento preventivo programado"),
                "scheduled_date": parse_dt(m.get("scheduled_date")) or datetime.datetime.utcnow(),
                "completed_date": parse_dt(m.get("completed_date")),
                "status": m.get("status", "Programado"),
                "sede": m.get("sede"),
                "image_path": m.get("image_path"),
                "device_id": m.get("device_id"),
                "incident_id": m.get("incident_id"),
                "created_by_id": m.get("created_by_id", 1),
                "created_at": parse_dt(m.get("created_at")) or datetime.datetime.utcnow(),
                "protocol_code": m.get("protocol_code"),
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
            if mid and mid not in existing_maint_ids:
                kwargs["id"] = mid
                existing_maint_ids.add(mid)
                db.add(Maintenance(**kwargs))
            elif not mid:
                db.add(Maintenance(**kwargs))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Aviso sembrando mantenimientos: {e}")

    # 8. Sembrar Eventos de Trazabilidad faltantes
    try:
        existing_ev_ids = {row[0] for row in db.query(Event.id).all()}
        for ev in golden_data.get("events", []):
            eid = ev.get("id")
            kwargs = {
                "incident_id": ev.get("incident_id"),
                "maintenance_id": ev.get("maintenance_id"),
                "user_id": ev.get("user_id"),
                "event_type": ev.get("event_type", "LOG"),
                "description": ev.get("description", ""),
                "created_at": parse_dt(ev.get("created_at")) or datetime.datetime.utcnow()
            }
            if eid and eid not in existing_ev_ids:
                kwargs["id"] = eid
                existing_ev_ids.add(eid)
                db.add(Event(**kwargs))
            elif not eid:
                db.add(Event(**kwargs))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Aviso sembrando eventos: {e}")

    # 9. En PostgreSQL: Sincronizar secuencias serial para evitar errores de clave duplicada
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
                except Exception as seq_err:
                    db.rollback()
                    logger.debug(f"Aviso actualizando secuencia para {tbl}: {seq_err}")
    except Exception as e:
        logger.warning(f"Aviso general en ajuste de secuencias postgres: {e}")

    logger.info("[*] Verificación y siembra de catálogo completada exitosamente.")
    return True
