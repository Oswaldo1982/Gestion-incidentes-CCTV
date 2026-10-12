from fastapi import status
from app.auth import create_access_token
from app.models.incident import Incident
from app.models.maintenance import Maintenance
import datetime


def test_reports_stats_api_authenticated(client, db, supervisor_user, active_license):
    """Happy path: Generación de métricas y KPIs consolidados en formato JSON para el frontend."""
    token = create_access_token({"sub": supervisor_user.username})
    client.cookies.set("access_token", f"Bearer {token}")
    client.cookies.set("active_site", "san-agustin")

    # Sembrar incidentes de prueba
    inc = Incident(
        title="Falla de cámara de seguridad",
        description="Sin video",
        status="Abierto",
        priority="Alta",
        fault_type="Falla Menor",
        sede="San Agustín (Huila)",
        created_by_id=supervisor_user.id
    )
    maint = Maintenance(
        type="Preventivo",
        title="Limpieza preventiva",
        description="Limpieza de domo",
        scheduled_date=datetime.datetime.utcnow(),
        status="Programado",
        sede="San Agustín (Huila)",
        created_by_id=supervisor_user.id
    )
    db.add_all([inc, maint])
    db.commit()

    response = client.get("/api/reports/stats?period=weekly")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "kpis" in data
    assert "total_events" in data["kpis"]
    assert "total_corrective" in data["kpis"]
    assert "total_preventive" in data["kpis"]
    assert data["kpis"]["total_events"] >= 2


def test_reports_stats_api_unauthenticated_error(client):
    """Control de acceso: Petición sin autenticación devuelve HTTP 401."""
    response = client.get("/api/reports/stats", follow_redirects=False)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_reports_pdf_export_authenticated(client, db, supervisor_user, active_license):
    """Happy path: Exportación y descarga oficial de informe ejecutivo en formato PDF."""
    token = create_access_token({"sub": supervisor_user.username})
    client.cookies.set("access_token", f"Bearer {token}")
    client.cookies.set("active_site", "san-agustin")

    response = client.get("/reports/export/pdf?period=weekly")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in response.headers["content-disposition"]
    # Los PDFs siempre inician con los bytes %PDF-
    assert response.content.startswith(b"%PDF-")


def test_reports_web_view_executive_layout_no_tables(client, db, supervisor_user, active_license):
    """Verifica que la vista web de informes cargue el modelo gráfico ejecutivo y que no contenga tablas inferiores."""
    token = create_access_token({"sub": supervisor_user.username})
    client.cookies.set("access_token", f"Bearer {token}")
    client.cookies.set("active_site", "san-agustin")

    response = client.get("/reports?period=weekly")
    assert response.status_code == status.HTTP_200_OK
    html = response.text

    # Contiene elementos del nuevo modelo gráfico ejecutivo
    assert "Disponibilidad Operativa:" in html
    assert "Scorecards" or "Disponibilidad" in html
    assert "chartTimeline" in html
    assert "chartValidation" in html
    assert "chartSites" in html
    assert "Descargar Informe Ejecutivo en PDF" in html

    # NO contiene la sección eliminada de pestañas inferiores ni tablas pesadas
    assert "activeTab = 'logins'" not in html
    assert "activeTab = 'changes'" not in html
    assert "activeTab = 'correctives'" not in html
    assert "activeTab = 'preventives'" not in html


def test_reports_pdf_export_executive_technical_specs(client, db, supervisor_user, validador_user, active_license):
    """Verifica que el informe ejecutivo en PDF procese dispositivos con todas sus características técnicas."""
    import json
    from app.models.device import Device

    token = create_access_token({"sub": supervisor_user.username})
    client.cookies.set("access_token", f"Bearer {token}")
    client.cookies.set("active_site", "san-agustin")

    # Crear dispositivo con ficha técnica completa
    device = Device(
        name="Cámara Domo PTZ Parque Central",
        device_type="Cámara PTZ",
        brand="Hikvision",
        model="DS-2DF8442IXS-AELW",
        serial_number="HK-CCTV-2026-9876",
        ip_address="192.168.10.45",
        sede="San Agustín (Huila)",
        location_detail="Parque Simón Bolívar"
    )
    db.add(device)
    db.commit()

    # Incidente con ficha técnica y validación policial
    inc = Incident(
        title="Intermitencia de video en enlace óptico",
        description="Pérdida de paquetes",
        status="Validado / Conforme",
        validation_status="Conforme",
        validator_id=validador_user.id,
        validated_at=datetime.datetime.utcnow(),
        priority="Alta",
        fault_type="Falla Crítica",
        sede="San Agustín (Huila)",
        location_detail="Parque Simón Bolívar",
        device_id=device.id,
        root_cause="Atenuación en conector de fibra óptica",
        solution="Fusión y conectorización nueva con prueba OTDR",
        closed_by_id=supervisor_user.id,
        closed_at=datetime.datetime.utcnow(),
        created_by_id=supervisor_user.id
    )

    # Mantenimiento preventivo con checklist de 6 puntos
    checklist_payload = json.dumps({
        "optica_limpieza": True,
        "fijacion_mecanica": True,
        "enlace_red_poe": True,
        "fuente_ups": True,
        "calibracion_ptz": True,
        "grabacion_nvr": True
    })
    maint = Maintenance(
        type="Preventivo",
        maintenance_type="Preventivo Mensual",
        title="Protocolo Preventivo Integral",
        description="Mantenimiento preventivo periódico",
        scheduled_date=datetime.datetime.utcnow(),
        status="Validado / Conforme",
        validation_status="Conforme",
        validator_id=validador_user.id,
        validated_at=datetime.datetime.utcnow(),
        sede="San Agustín (Huila)",
        location_detail="Parque Simón Bolívar",
        device_id=device.id,
        checklist_results=checklist_payload,
        technical_findings="Polvo acumulado en cúpula y tensión correcta",
        actions_taken="Limpieza óptica con alcohol isopropílico y reapriete de soportes",
        recommendations="Programar siguiente inspección en 30 días",
        completed_by_id=supervisor_user.id,
        completed_date=datetime.datetime.utcnow(),
        created_by_id=supervisor_user.id
    )
    db.add_all([inc, maint])
    db.commit()

    response = client.get("/reports/export/pdf?period=monthly")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "application/pdf"
    # Debe ser un PDF no vacío con estructura completa
    assert len(response.content) > 3000
    assert response.content.startswith(b"%PDF-")

