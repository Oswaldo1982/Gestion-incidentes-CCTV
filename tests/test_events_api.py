from fastapi import status
from app.models.incident import Incident
from app.models.maintenance import Maintenance
import datetime


def test_incident_timeline_and_comments(client, db, operario_headers, active_license, operario_user):
    """Happy path y restricciones: Comentarios en timeline de incidentes."""
    inc = Incident(
        title="Falla de domo PTZ",
        description="Sin movimiento horizontal",
        status="Abierto",
        created_by_id=operario_user.id
    )
    db.add(inc)
    db.commit()

    # Agregar comentario a incidente abierto
    r_comment = client.post(
        f"/api/events/incident/{inc.id}/comment",
        json={"description": "Se verificó cableado UTP en mástil, voltaje normal."},
        headers=operario_headers
    )
    assert r_comment.status_code == status.HTTP_201_CREATED
    data = r_comment.json()
    assert "voltaje normal" in data["description"]
    assert data["event_type"] == "COMMENT"

    # Consultar timeline
    r_timeline = client.get(f"/api/events/incident/{inc.id}", headers=operario_headers)
    assert r_timeline.status_code == status.HTTP_200_OK
    assert len(r_timeline.json()) >= 1

    # Cerrar incidente y comprobar que se bloquean nuevos comentarios
    inc.status = "Cerrado"
    db.commit()

    r_blocked = client.post(
        f"/api/events/incident/{inc.id}/comment",
        json={"description": "Intento de comentar en ticket cerrado."},
        headers=operario_headers
    )
    assert r_blocked.status_code == status.HTTP_400_BAD_REQUEST
    assert "incidentes cerrados" in r_blocked.json()["detail"]


def test_maintenance_timeline_and_comments(client, db, supervisor_headers, active_license, supervisor_user):
    """Happy path y restricciones: Comentarios en timeline de mantenimientos."""
    maint = Maintenance(
        type="Preventivo",
        title="Ajuste de Cámaras",
        description="Enfoque",
        scheduled_date=datetime.datetime.utcnow(),
        status="Programado",
        created_by_id=supervisor_user.id
    )
    db.add(maint)
    db.commit()

    # Comentario válido en estado Programado
    r_comment = client.post(
        f"/api/events/maintenance/{maint.id}/comment",
        json={"description": "Coordinado vehículo con Secretaría de Gobierno."},
        headers=supervisor_headers
    )
    assert r_comment.status_code == status.HTTP_201_CREATED

    # Completar mantenimiento y verificar restricción
    maint.status = "Completado"
    db.commit()

    r_blocked = client.post(
        f"/api/events/maintenance/{maint.id}/comment",
        json={"description": "Comentario extemporáneo."},
        headers=supervisor_headers
    )
    assert r_blocked.status_code == status.HTTP_400_BAD_REQUEST
    assert "Completado" in r_blocked.json()["detail"]
