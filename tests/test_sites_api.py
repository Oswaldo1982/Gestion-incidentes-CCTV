from fastapi import status
from app.models.site import Site


def test_list_sites_empty_and_populated(client, db, sample_site):
    """Consulta de sedes: Retorna lista de sedes territoriales."""
    response = client.get("/api/sites")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) >= 1
    assert any(s["id"] == "san-agustin" for s in data)


def test_list_sites_active_only(client, db):
    """Filtro active_only: Excluye sedes desactivadas administrativamente."""
    s_active = Site(id="sede-activa", name="Sede Activa", full_name="Sede Activa Test", is_active=True)
    s_inactive = Site(id="sede-inactiva", name="Sede Inactiva", full_name="Sede Inactiva Test", is_active=False)
    db.add_all([s_active, s_inactive])
    db.commit()

    # Todos
    r_all = client.get("/api/sites")
    assert r_all.status_code == status.HTTP_200_OK
    ids_all = [s["id"] for s in r_all.json()]
    assert "sede-activa" in ids_all
    assert "sede-inactiva" in ids_all

    # Solo activos
    r_active = client.get("/api/sites?active_only=true")
    assert r_active.status_code == status.HTTP_200_OK
    ids_active = [s["id"] for s in r_active.json()]
    assert "sede-activa" in ids_active
    assert "sede-inactiva" not in ids_active


def test_get_site_by_id(client, sample_site):
    """Consulta individual de sede por ID existente y 404 inexistente."""
    r_ok = client.get("/api/sites/san-agustin")
    assert r_ok.status_code == status.HTTP_200_OK
    assert r_ok.json()["name"] == "San Agustín"

    r_404 = client.get("/api/sites/inexistente-xyz")
    assert r_404.status_code == status.HTTP_404_NOT_FOUND


def test_create_site_admin_happy_path(client, admin_headers):
    """Creación de sede: Administrador puede registrar una nueva sede territorial dinámica."""
    payload = {
        "id": "nueva-sede-sur",
        "name": "Sede Regional Sur",
        "full_name": "Sede Regional Sur (Circuito Especial)",
        "region": "Amazonas",
        "badge": "Circuito Frontera",
        "description": "Monitoreo perimetral y fluvial",
        "cameras_count": 16,
        "color": "indigo"
    }
    response = client.post("/api/sites", json=payload, headers=admin_headers)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["id"] == "nueva-sede-sur"
    assert data["name"] == "Sede Regional Sur"
    assert data["is_active"] is True


def test_create_site_duplicate_id_forbidden(client, admin_headers, sample_site):
    """Validación: Rechaza duplicados con código 400 si el ID ya existe."""
    payload = {
        "id": "san-agustin",
        "name": "Duplicado",
        "full_name": "Duplicado Test"
    }
    response = client.post("/api/sites", json=payload, headers=admin_headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Ya existe una sede territorial" in response.json()["detail"]


def test_create_site_non_admin_forbidden(client, supervisor_headers):
    """Seguridad: Usuarios no administradores no pueden crear sedes (403)."""
    payload = {
        "id": "sede-hacker",
        "name": "Sede Denegada",
        "full_name": "Sede Denegada"
    }
    response = client.post("/api/sites", json=payload, headers=supervisor_headers)
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_update_site_admin(client, admin_headers, sample_site):
    """Actualización: Administrador modifica atributos de una sede existente."""
    payload = {
        "name": "San Agustín Renovado",
        "cameras_count": 35,
        "color": "emerald"
    }
    response = client.patch(f"/api/sites/{sample_site.id}", json=payload, headers=admin_headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["name"] == "San Agustín Renovado"
    assert data["cameras_count"] == 35
    assert data["color"] == "emerald"


def test_deactivate_and_reactivate_site(client, admin_headers, sample_site):
    """Desactivación y reactivación operativa de una sede territorial."""
    # Desactivar
    r_deact = client.delete(f"/api/sites/{sample_site.id}", headers=admin_headers)
    assert r_deact.status_code == status.HTTP_200_OK
    assert r_deact.json()["is_active"] is False

    # Verificar estado
    r_check = client.get(f"/api/sites/{sample_site.id}")
    assert r_check.json()["is_active"] is False
    assert r_check.json()["status"] == "Inactivo"

    # Reactivar
    r_act = client.post(f"/api/sites/{sample_site.id}/activate", headers=admin_headers)
    assert r_act.status_code == status.HTTP_200_OK
    assert r_act.json()["is_active"] is True
    assert r_act.json()["status"] == "Operativo"
