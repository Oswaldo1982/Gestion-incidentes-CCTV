import datetime
from app.models.device import Device
from app.models.incident import Incident
from app.models.maintenance import Maintenance
from app.auth import is_password_already_in_use, get_password_hash
from app.main import resolve_date_range


def test_device_calculated_status_operativo(db, sample_device):
    """Happy path: Un equipo sin incidentes ni mantenimientos activos debe reportar 'Operativo'."""
    assert sample_device.calculated_status == "Operativo"
    assert sample_device.active_incident is None


def test_device_calculated_status_en_falla_incident_abierto(db, sample_device, operario_user):
    """Regla de negocio: Si el equipo tiene un incidente 'Abierto', su estado calculado pasa a 'En Falla'."""
    incident = Incident(
        title="Pérdida de señal de video",
        description="La cámara no envía transmisión RTSP al VMS.",
        status="Abierto",
        priority="Alta",
        device_id=sample_device.id,
        created_by_id=operario_user.id
    )
    db.add(incident)
    db.commit()
    db.refresh(sample_device)

    assert sample_device.calculated_status == "En Falla"
    assert sample_device.active_incident is not None
    assert sample_device.active_incident.id == incident.id


def test_device_calculated_status_en_falla_incident_en_proceso(db, sample_device, operario_user):
    """Regla de negocio: Si el equipo tiene un incidente 'En Proceso', sigue en estado 'En Falla'."""
    incident = Incident(
        title="Falla de alimentación PoE",
        description="Switch no entrega potencia al puerto.",
        status="En Proceso",
        priority="Media",
        device_id=sample_device.id,
        created_by_id=operario_user.id
    )
    db.add(incident)
    db.commit()
    db.refresh(sample_device)

    assert sample_device.calculated_status == "En Falla"


def test_device_calculated_status_mantenimiento(db, sample_device, supervisor_user):
    """Regla de negocio: Si no hay incidentes pero sí un mantenimiento 'Programado', el estado es 'En Mantenimiento'."""
    maint = Maintenance(
        type="Preventivo",
        title="Limpieza de domo y lubricación de motor PTZ",
        description="Mantenimiento preventivo mensual.",
        scheduled_date=datetime.datetime.utcnow() + datetime.timedelta(days=1),
        status="Programado",
        device_id=sample_device.id,
        created_by_id=supervisor_user.id
    )
    db.add(maint)
    db.commit()
    db.refresh(sample_device)

    assert sample_device.calculated_status == "En Mantenimiento"


def test_device_calculated_status_inactivo_priority(db, sample_device, operario_user):
    """Regla de negocio: Si un equipo es desactivado ('Inactivo'), tiene prioridad sobre incidentes y mantenimientos."""
    sample_device.status = "Inactivo"
    incident = Incident(
        title="Incidente en equipo inactivo",
        description="Test",
        status="Abierto",
        device_id=sample_device.id,
        created_by_id=operario_user.id
    )
    db.add(incident)
    db.commit()
    db.refresh(sample_device)

    assert sample_device.calculated_status == "Inactivo"


def test_incident_sla_target_hours_mapping():
    """Valida los tiempos máximos permitidos por SLA según la tipología de falla CCTV."""
    inc_critica = Incident(fault_type="Falla Crítica")
    inc_inactivo = Incident(fault_type="Inactivo")
    inc_menor = Incident(fault_type="Falla Menor")
    inc_cambio = Incident(fault_type="Cambio")
    inc_default = Incident(fault_type=None)

    assert inc_critica.sla_target_hours == 4
    assert inc_inactivo.sla_target_hours == 12
    assert inc_menor.sla_target_hours == 24
    assert inc_cambio.sla_target_hours == 48
    assert inc_default.sla_target_hours == 24


def test_incident_sla_info_statuses():
    """Valida el cálculo de semáforo SLA (Óptimo, Riesgo Inminente, Vencido, Cumplido y Fuera de Meta)."""
    now = datetime.datetime.utcnow()

    # 1. Óptimo (< 70% del tiempo transcurrido)
    inc_opt = Incident(
        fault_type="Falla Menor", # 24 horas meta
        status="Abierto",
        created_at=now - datetime.timedelta(hours=2)
    )
    assert inc_opt.sla_info["status"] == "optimal"
    assert "En Tiempo Óptimo" in inc_opt.sla_info["label"]

    # 2. Riesgo Inminente (>= 70% del SLA transcurrido)
    inc_warn = Incident(
        fault_type="Falla Menor",
        status="Abierto",
        created_at=now - datetime.timedelta(hours=18) # 18/24 = 75%
    )
    assert inc_warn.sla_info["status"] == "warning"
    assert "Riesgo Inminente" in inc_warn.sla_info["label"]

    # 3. Plazo Vencido (>= 100% transcurrido)
    inc_overdue = Incident(
        fault_type="Falla Menor",
        status="Abierto",
        created_at=now - datetime.timedelta(hours=25)
    )
    assert inc_overdue.sla_info["status"] == "expired"
    assert "Plazo Vencido" in inc_overdue.sla_info["label"]

    # 4. Cerrado a tiempo
    inc_closed_ok = Incident(
        fault_type="Falla Menor",
        status="Cerrado",
        created_at=now - datetime.timedelta(hours=10),
        closed_at=now - datetime.timedelta(hours=2) # tomó 8h <= 24h
    )
    assert inc_closed_ok.sla_info["status"] == "closed_on_time"
    assert "Cumplido a Tiempo" in inc_closed_ok.sla_info["label"]

    # 5. Cerrado fuera de meta
    inc_closed_late = Incident(
        fault_type="Falla Menor",
        status="Cerrado",
        created_at=now - datetime.timedelta(hours=30),
        closed_at=now - datetime.timedelta(hours=2) # tomó 28h > 24h
    )
    assert inc_closed_late.sla_info["status"] == "closed_late"
    assert "Cerrado Fuera de Meta" in inc_closed_late.sla_info["label"]


def test_maintenance_proactive_status_rules():
    """Valida el ciclo de vida proactivo de un mantenimiento programado."""
    now = datetime.datetime.utcnow()

    # Programado con más de 48 horas de anticipación
    m_schedule = Maintenance(
        status="Programado",
        scheduled_date=now + datetime.timedelta(days=5)
    )
    assert m_schedule.proactive_status["status"] == "on_schedule"

    # Próximo a vencer (<= 48h)
    m_impending = Maintenance(
        status="Programado",
        scheduled_date=now + datetime.timedelta(hours=24)
    )
    assert m_impending.proactive_status["status"] == "impending"

    # Atrasado / Vencido
    m_overdue = Maintenance(
        status="Programado",
        scheduled_date=now - datetime.timedelta(hours=5)
    )
    assert m_overdue.proactive_status["status"] == "overdue"

    # En Ejecución Técnica
    m_exec = Maintenance(status="En Ejecución")
    assert m_exec.proactive_status["status"] == "in_progress"

    # Completado a tiempo (dentro de tolerancia de 12 horas)
    m_comp_ok = Maintenance(
        status="Completado",
        scheduled_date=now - datetime.timedelta(hours=4),
        completed_date=now - datetime.timedelta(hours=2)
    )
    assert m_comp_ok.proactive_status["status"] == "completed_on_time"


def test_resolve_date_range_helper():
    """Valida los rangos predeterminados y personalizados de fechas para reportes."""
    # Rango 'weekly' (por defecto)
    start_week, end_week, label_week = resolve_date_range("weekly", None, None)
    assert (end_week - start_week).days >= 7
    assert "Semanal" in label_week

    # Rango 'monthly' (30 días)
    start_month, end_month, label_month = resolve_date_range("monthly", None, None)
    assert (end_month - start_month).days >= 30
    assert "Mensual" in label_month

    # Rango 'annual' (365 días)
    start_year, end_year, label_year = resolve_date_range("annual", None, None)
    assert (end_year - start_year).days >= 365
    assert "Anual" in label_year

    # Rango personalizado válido
    start_custom, end_custom, label_custom = resolve_date_range("custom", "2026-01-01", "2026-01-15")
    assert start_custom.strftime("%Y-%m-%d") == "2026-01-01"
    assert end_custom.strftime("%Y-%m-%d") == "2026-01-15"
    assert "Personalizado" in label_custom

    # Rango personalizado con fecha inválida (fallback a semanal)
    s_fallback, e_fallback, l_fallback = resolve_date_range("custom", "invalid-date", "2026-01-15")
    assert (e_fallback - s_fallback).days >= 7
    assert "Semanal" in l_fallback


def test_is_password_already_in_use(db, admin_user):
    """Regla de seguridad: Garantiza que no se reutilicen contraseñas idénticas entre usuarios."""
    # La contraseña del admin_user es 'AdminPass123!'
    assert is_password_already_in_use("AdminPass123!", db) is True
    assert is_password_already_in_use("CompletelyUniquePass999!", db) is False

    # Al excluir el propio usuario (edición de perfil), no debe reportar conflicto consigo mismo
    assert is_password_already_in_use("AdminPass123!", db, exclude_user_id=admin_user.id) is False
