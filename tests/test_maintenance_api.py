import datetime
from fastapi import status
from app.models.maintenance import Maintenance
from app.models.event import Event


def test_create_maintenance_happy_path(client, admin_headers, active_license, sample_device):
    """Happy path: Administrador programa un mantenimiento preventivo con código de protocolo automático."""
    scheduled_dt = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).isoformat()
    payload = {
        "type": "Preventivo",
        "title": "Mantenimiento Preventivo Bimestral PTZ",
        "description": "Revisión de sellado estanco, conector RJ45 y firmware.",
        "scheduled_date": scheduled_dt,
        "sede": "San Agustín (Huila)",
        "location_detail": 'Cam 1 "Terminal"',
        "device_id": sample_device.id,
        "maintenance_type": "Preventivo Mensual",
        "priority": "Media"
    }
    response = client.post("/api/maintenance", json=payload, headers=admin_headers)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()

    assert data["id"] is not None
    assert data["protocol_code"].startswith("MP-")
    assert data["status"] == "Programado"
    assert data["device_id"] == sample_device.id


def test_create_maintenance_forbidden_for_supervisor(client, supervisor_headers, active_license, sample_device):
    """Control de acceso: Rol Supervisor no puede programar mantenimientos (HTTP 403)."""
    payload = {
        "type": "Preventivo",
        "title": "Intento Supervisor",
        "description": "Prueba",
        "scheduled_date": datetime.datetime.utcnow().isoformat()
    }
    response = client.post("/api/maintenance", json=payload, headers=supervisor_headers)
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_create_maintenance_forbidden_for_operario(client, operario_headers, active_license):
    """Control de acceso: Un usuario con rol Operario no tiene permisos para programar mantenimientos (HTTP 403)."""
    payload = {
        "type": "Preventivo",
        "title": "Intento no autorizado",
        "description": "Prueba",
        "scheduled_date": datetime.datetime.utcnow().isoformat()
    }
    response = client.post("/api/maintenance", json=payload, headers=operario_headers)
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_get_maintenances_filtering(client, db, supervisor_headers, active_license, supervisor_user):
    """Filtros: Consulta y filtra cronograma por tipo y estado."""
    now = datetime.datetime.utcnow()
    m1 = Maintenance(
        type="Preventivo",
        title="M1",
        description="D1",
        scheduled_date=now,
        status="Programado",
        created_by_id=supervisor_user.id
    )
    m2 = Maintenance(
        type="Correctivo",
        title="M2",
        description="D2",
        scheduled_date=now,
        status="Completado",
        created_by_id=supervisor_user.id
    )
    db.add_all([m1, m2])
    db.commit()

    # Filtrar por type=Preventivo
    r_type = client.get("/api/maintenance?type=Preventivo", headers=supervisor_headers)
    assert r_type.status_code == status.HTTP_200_OK
    items = r_type.json()
    assert all(m["type"] == "Preventivo" for m in items)

    # Filtrar por status=Completado
    r_status = client.get("/api/maintenance?status=Completado", headers=supervisor_headers)
    assert r_status.status_code == status.HTTP_200_OK
    items_s = r_status.json()
    assert all(m["status"] == "Completado" for m in items_s)


def test_update_maintenance_workflow(client, db, admin_headers, active_license, admin_user):
    """Flujo técnico: Transición de Programado -> En Ejecución -> Completado con checklist y hallazgos."""
    maint = Maintenance(
        type="Preventivo",
        title="Mantenimiento Gabinete UPS",
        description="Medición de baterías",
        scheduled_date=datetime.datetime.utcnow(),
        status="Programado",
        created_by_id=admin_user.id
    )
    db.add(maint)
    db.commit()

    # 1. Pasar a En Ejecución
    r_exec = client.patch(
        f"/api/maintenance/{maint.id}",
        json={"status": "En Ejecución"},
        headers=admin_headers
    )
    assert r_exec.status_code == status.HTTP_200_OK
    assert r_exec.json()["status"] == "En Ejecución"

    # 2. Completar con informe técnico
    r_comp = client.patch(
        f"/api/maintenance/{maint.id}",
        json={
            "status": "Completado",
            "technical_findings": "Baterías con 95% de vida útil, ventiladores lubricados.",
            "actions_taken": "Aspirado de polvo interno y prueba de autonomía de 20 minutos.",
            "recommendations": "Próxima revisión en 6 meses."
        },
        headers=admin_headers
    )
    assert r_comp.status_code == status.HTTP_200_OK
    data = r_comp.json()
    assert data["status"] == "Pendiente de Validación"
    assert data["validation_status"] == "Pendiente"
    assert "95% de vida útil" in data["technical_findings"]

    # Validar evento en timeline
    events = db.query(Event).filter(Event.maintenance_id == maint.id, Event.event_type == "STATUS_CHANGE").all()
    assert len(events) >= 2


def test_update_maintenance_forbidden_for_supervisor(client, db, supervisor_headers, active_license, admin_user):
    """Control de acceso: Supervisor no puede modificar el estado de mantenimientos."""
    maint = Maintenance(
        type="Preventivo",
        title="Mantenimiento Gabinete UPS",
        description="Medición de baterías",
        scheduled_date=datetime.datetime.utcnow(),
        status="Programado",
        created_by_id=admin_user.id
    )
    db.add(maint)
    db.commit()

    r = client.patch(
        f"/api/maintenance/{maint.id}",
        json={"status": "En Ejecución"},
        headers=supervisor_headers
    )
    assert r.status_code == status.HTTP_403_FORBIDDEN

