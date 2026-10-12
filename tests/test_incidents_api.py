from fastapi import status
from app.models.incident import Incident
from app.models.event import Event


def test_create_incident_happy_path(client, operario_headers, active_license, sample_device):
    """Happy path: Creación de incidente con generación automática de ticket único y evento en timeline."""
    payload = {
        "title": "Falla de infrarrojo nocturno",
        "description": "El sensor IR no conmuta al anochecer.",
        "priority": "Alta",
        "fault_type": "Falla Menor",
        "location_detail": 'Cam 1 "Terminal"',
        "sede": "San Agustín (Huila)",
        "device_id": sample_device.id
    }
    response = client.post("/api/incidents", json=payload, headers=operario_headers)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()

    assert data["id"] is not None
    assert data["ticket_number"].startswith("TKT-")
    assert data["status"] == "Abierto"
    assert data["priority"] == "Alta"
    assert data["device_id"] == sample_device.id


def test_create_incident_auto_title(client, operario_headers, active_license):
    """Regla de negocio: Genera título automático si el campo se deja vacío."""
    payload = {
        "description": "Switch PoE sin respuesta a ping.",
        "fault_type": "Falla Crítica",
        "location_detail": "Estación de Policía",
        "priority": "Crítica"
    }
    response = client.post("/api/incidents", json=payload, headers=operario_headers)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert "Mantenimiento Correctivo - Falla Crítica - Estación de Policía" in data["title"]


def test_get_incidents_filtering(client, db, supervisor_headers, active_license, operario_user):
    """Filtros: Lista incidentes y filtra por estado y prioridad con estructura paginada."""
    i1 = Incident(title="Inc 1", description="D1", status="Abierto", priority="Baja", created_by_id=operario_user.id)
    i2 = Incident(title="Inc 2", description="D2", status="Cerrado", priority="Crítica", created_by_id=operario_user.id)
    db.add_all([i1, i2])
    db.commit()

    # Filtrar por status=Abierto
    r_status = client.get("/api/incidents?status=Abierto", headers=supervisor_headers)
    assert r_status.status_code == status.HTTP_200_OK
    data_status = r_status.json()
    assert "items" in data_status
    assert data_status["total"] == 1
    items = data_status["items"]
    assert all(i["status"] == "Abierto" for i in items)

    # Filtrar por priority=Crítica
    r_prio = client.get("/api/incidents?priority=Crítica", headers=supervisor_headers)
    assert r_prio.status_code == status.HTTP_200_OK
    data_prio = r_prio.json()
    items_p = data_prio["items"]
    assert all(i["priority"] == "Crítica" for i in items_p)


def test_get_incidents_pagination_metadata(client, db, supervisor_headers, active_license, operario_user):
    """Paginación obligatoria: Valida page, page_size, total y total_pages."""
    incidents = [
        Incident(title=f"Incidente {i}", description=f"Desc {i}", created_by_id=operario_user.id)
        for i in range(1, 11)
    ]
    db.add_all(incidents)
    db.commit()

    # Consultar página 1 con page_size=4
    r_p1 = client.get("/api/incidents?page=1&page_size=4", headers=supervisor_headers)
    assert r_p1.status_code == status.HTTP_200_OK
    p1_data = r_p1.json()

    assert len(p1_data["items"]) == 4
    assert p1_data["total"] == 10
    assert p1_data["page"] == 1
    assert p1_data["page_size"] == 4
    assert p1_data["total_pages"] == 3
    assert p1_data["has_next"] is True
    assert p1_data["has_prev"] is False

    # Consultar página 3 (última página)
    r_p3 = client.get("/api/incidents?page=3&page_size=4", headers=supervisor_headers)
    assert r_p3.status_code == status.HTTP_200_OK
    p3_data = r_p3.json()

    assert len(p3_data["items"]) == 2
    assert p3_data["page"] == 3
    assert p3_data["has_next"] is False
    assert p3_data["has_prev"] is True


def test_get_incident_by_id_found_and_not_found(client, db, supervisor_headers, active_license, operario_user):
    """Consulta de detalle de incidente existente e inexistente (404)."""
    inc = Incident(title="Incidente Test", description="Desc", created_by_id=operario_user.id)
    db.add(inc)
    db.commit()

    # Encontrado
    r_found = client.get(f"/api/incidents/{inc.id}", headers=supervisor_headers)
    assert r_found.status_code == status.HTTP_200_OK
    assert r_found.json()["id"] == inc.id

    # No encontrado
    r_not_found = client.get("/api/incidents/99999", headers=supervisor_headers)
    assert r_not_found.status_code == status.HTTP_404_NOT_FOUND


def test_update_incident_status_and_closing(client, db, admin_headers, active_license, operario_user):
    """Trazabilidad: Al cerrar un incidente se registra fecha de cierre, usuario y evento en timeline."""
    inc = Incident(
        title="Cámara desenfocada",
        description="Lente sucio",
        status="Abierto",
        created_by_id=operario_user.id
    )
    db.add(inc)
    db.commit()

    # Pasar a En Proceso
    r_proc = client.patch(
        f"/api/incidents/{inc.id}",
        json={"status": "En Proceso"},
        headers=admin_headers
    )
    assert r_proc.status_code == status.HTTP_200_OK
    assert r_proc.json()["status"] == "En Proceso"

    # Cerrar incidente con solución
    r_close = client.patch(
        f"/api/incidents/{inc.id}",
        json={
            "status": "Cerrado",
            "solution": "Se realizó limpieza de domo y ajuste óptico de foco.",
            "root_cause": "Condiciones climáticas / polvo en suspensión"
        },
        headers=admin_headers
    )
    assert r_close.status_code == status.HTTP_200_OK
    data = r_close.json()
    assert data["status"] in ["Cerrado", "Pendiente de Validación"]
    assert data["solution"] is not None

    # Verificar que se creó evento de cambio de estado en la tabla Event
    events = db.query(Event).filter(Event.incident_id == inc.id, Event.event_type == "STATUS_CHANGE").all()
    assert len(events) >= 2


def test_update_incident_assignee_validation(client, db, admin_headers, active_license, operario_user):
    """Error esperado: Asignar a un usuario inexistente devuelve HTTP 400."""
    inc = Incident(title="Inc Test", description="Desc", created_by_id=operario_user.id)
    db.add(inc)
    db.commit()

    response = client.patch(
        f"/api/incidents/{inc.id}",
        json={"assigned_to_id": 99999}, # ID inexistente
        headers=admin_headers
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "no existe" in response.json()["detail"]


def test_supervisor_forbidden_incident_mutation(client, db, supervisor_headers, active_license, operario_user):
    """Restricción institucional: Supervisor tiene solo lectura y no puede crear ni modificar incidentes."""
    # 1. Intento de creación
    r_create = client.post(
        "/api/incidents",
        json={"title": "Falla prueba", "description": "Prueba supervisor"},
        headers=supervisor_headers
    )
    assert r_create.status_code == status.HTTP_403_FORBIDDEN

    # 2. Intento de modificación
    inc = Incident(title="Incidente Activo", description="Desc", status="Abierto", created_by_id=operario_user.id)
    db.add(inc)
    db.commit()

    r_patch = client.patch(
        f"/api/incidents/{inc.id}",
        json={"status": "En Proceso"},
        headers=supervisor_headers
    )
    assert r_patch.status_code == status.HTTP_403_FORBIDDEN

