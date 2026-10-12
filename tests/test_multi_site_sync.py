import pytest
from fastapi import status
from app.auth import create_access_token
from app.services.site_sync_service import ensure_all_sites_synchronized, TARGET_SITES
from app.main import AVAILABLE_SITES


@pytest.fixture(autouse=True)
def sync_sites_before_test(db):
    """Garantiza que la base de datos de pruebas tenga las 4 sedes sincronizadas."""
    ensure_all_sites_synchronized(db)


def test_all_four_sites_reports_web_view(client, db, supervisor_user, active_license):
    """Verifica que las 4 sedes carguen el nuevo modelo gráfico ejecutivo en la web de forma idéntica."""
    token = create_access_token({"sub": supervisor_user.username})
    client.cookies.set("access_token", f"Bearer {token}")

    for site in AVAILABLE_SITES[:4]:
        site_id = site["id"]
        client.cookies.set("active_site", site_id)

        response = client.get(f"/reports?site={site_id}&period=weekly")
        assert response.status_code == status.HTTP_200_OK, f"Error cargando /reports en sede {site_id}"
        html = response.text

        # Debe contener los elementos del nuevo modelo gráfico ejecutivo
        assert "Centro de Estadísticas, Mantenimiento & Auditoría" in html
        assert "Disponibilidad Operativa:" in html
        assert "chartTimeline" in html
        assert "chartValidation" in html
        assert "chartSites" in html
        assert "Descargar Informe Ejecutivo en PDF" in html

        # NO debe contener las tablas inferiores eliminadas
        assert "activeTab = 'logins'" not in html
        assert "activeTab = 'changes'" not in html
        assert "activeTab = 'correctives'" not in html
        assert "activeTab = 'preventives'" not in html


def test_all_four_sites_api_stats_homogeneity(client, db, supervisor_user, active_license):
    """Verifica que el API REST devuelva KPIs e indicadores para cada una de las 4 sedes."""
    token = create_access_token({"sub": supervisor_user.username})
    client.cookies.set("access_token", f"Bearer {token}")

    for site in AVAILABLE_SITES[:4]:
        site_id = site["id"]
        client.cookies.set("active_site", site_id)

        response = client.get(f"/api/reports/stats?site={site_id}&period=weekly")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "kpis" in data
        assert "charts" in data
        assert "circuit_availability" in data["kpis"]
        assert "total_events" in data["kpis"]
        assert "total_corrective" in data["kpis"]
        assert "total_preventive" in data["kpis"]


def test_all_four_sites_pdf_export_executive(client, db, supervisor_user, active_license):
    """Verifica que la descarga del informe ejecutivo oficial en PDF funcione en las 4 sedes."""
    token = create_access_token({"sub": supervisor_user.username})
    client.cookies.set("access_token", f"Bearer {token}")

    for site in AVAILABLE_SITES[:4]:
        site_id = site["id"]
        client.cookies.set("active_site", site_id)

        response = client.get(f"/reports/export/pdf?site={site_id}&period=weekly")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment; filename=" in response.headers["content-disposition"]
        assert response.content.startswith(b"%PDF-")
        assert len(response.content) > 3000


def test_all_four_sites_supervisor_restrictions_symmetry(client, db, supervisor_user, active_license):
    """Verifica que las restricciones del rol Supervisor se apliquen con total simetría en las 4 sedes."""
    token = create_access_token({"sub": supervisor_user.username})
    client.cookies.set("access_token", f"Bearer {token}")

    for site in AVAILABLE_SITES[:4]:
        site_id = site["id"]
        client.cookies.set("active_site", site_id)

        # 1. En incidentes: botón en gris
        r_inc = client.get(f"/incidents?site={site_id}")
        assert r_inc.status_code == status.HTTP_200_OK
        assert "cursor-not-allowed" in r_inc.text

        # 2. En mantenimiento: botón en gris
        r_maint = client.get(f"/maintenance?site={site_id}")
        assert r_maint.status_code == status.HTTP_200_OK
        assert "cursor-not-allowed" in r_maint.text

        # 3. En equipos: botón en gris
        r_dev = client.get(f"/devices?site={site_id}")
        assert r_dev.status_code == status.HTTP_200_OK
        assert "cursor-not-allowed" in r_dev.text

        # 4. Intento de crear incidente rechazado
        r_post_inc = client.post(
            f"/incidents?site={site_id}",
            data={
                "fault_type": "Falla Menor",
                "priority": "Media",
                "location_detail": "Parque",
                "description": "Prueba supervisor"
            },
            follow_redirects=False
        )
        assert r_post_inc.status_code == status.HTTP_303_SEE_OTHER
        assert "error=" in r_post_inc.headers["location"]
