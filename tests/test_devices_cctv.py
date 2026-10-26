from fastapi import status
from app.models.device import Device
from app.models.incident import Incident
from app.models.maintenance import Maintenance
from app.auth import create_access_token
import datetime


def test_devices_view_unauthenticated_redirect(client):
    """Acceso no autenticado: Redirige a /select-site con HTTP 302."""
    response = client.get("/devices", follow_redirects=False)
    assert response.status_code == status.HTTP_302_FOUND
    assert response.headers["location"] == "/select-site"


def test_devices_view_authenticated(client, admin_user, active_license, sample_device):
    """Happy path: Administrador accede a la vista web de inventario CCTV de la sede."""
    token = create_access_token({"sub": admin_user.username})
    client.cookies.set("access_token", f"Bearer {token}")
    client.cookies.set("active_site", "san-agustin")

    response = client.get("/devices")
    assert response.status_code == status.HTTP_200_OK
    assert "text/html" in response.headers["content-type"]
    assert sample_device.serial_number in response.text
    assert sample_device.brand in response.text


def test_create_device_web(client, db, admin_user, active_license):
    """Happy path: Creación de un nuevo punto de cámara CCTV mediante formulario web."""
    token = create_access_token({"sub": admin_user.username})
    client.cookies.set("access_token", f"Bearer {token}")
    client.cookies.set("active_site", "san-agustin")

    form_data = {
        "name": 'Cámara Domo 02 "Parque Arqueológico"',
        "device_type": "Cámara Domo",
        "location_detail": 'Cam3 "Parque Arqueológico"',
        "brand": "Dahua",
        "model": "DH-IPC-HDBW",
        "serial_number": "DH-DOMO-778899",
        "ip_address": "192.168.10.45",
        "sede": "San Agustín (Huila)"
    }
    response = client.post("/devices", data=form_data, follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert "/devices?msg=" in response.headers["location"]

    # Verificar existencia en base de datos
    dev = db.query(Device).filter(Device.serial_number == "DH-DOMO-778899").first()
    assert dev is not None
    assert dev.name == 'Cámara Domo 02 "Parque Arqueológico"'
    assert dev.status == "Operativo"


def test_update_device_status_web(client, db, admin_user, sample_device):
    """Happy path: Modificación manual del estado operativo de un equipo."""
    token = create_access_token({"sub": admin_user.username})
    client.cookies.set("access_token", f"Bearer {token}")

    response = client.post(
        f"/devices/{sample_device.id}/status",
        data={"status": "Alerta Menor"},
        follow_redirects=False
    )
    assert response.status_code == status.HTTP_303_SEE_OTHER

    db.refresh(sample_device)
    assert sample_device.status == "Alerta Menor"


def test_relocate_device_web_authorized(client, db, admin_user, sample_device):
    """Happy path: El Administrador Principal autoriza con su clave el traslado de una cámara."""
    token = create_access_token({"sub": admin_user.username})
    client.cookies.set("access_token", f"Bearer {token}")
    client.cookies.set("active_site", "san-agustin")

    form_data = {
        "new_sitio": 'Cam 2 "Cuatro vientos"',
        "admin_password": "AdminPass123!" # Contraseña correcta del administrador
    }
    response = client.post(f"/devices/{sample_device.id}/relocate", data=form_data, follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert "/devices?msg=" in response.headers["location"]

    db.refresh(sample_device)
    assert sample_device.location_detail == 'Cam 2 "Cuatro vientos"'


def test_relocate_device_web_wrong_password(client, db, admin_user, sample_device):
    """Error esperado: Contraseña incorrecta deniega el traslado del equipo."""
    token = create_access_token({"sub": admin_user.username})
    client.cookies.set("access_token", f"Bearer {token}")
    client.cookies.set("active_site", "san-agustin")

    form_data = {
        "new_sitio": "Estación de Policía",
        "admin_password": "WrongPassword123!"
    }
    response = client.post(f"/devices/{sample_device.id}/relocate", data=form_data, follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert "error=" in response.headers["location"]
    assert "incorrecta" in response.headers["location"]


def test_delete_device_web_unlinking(client, db, admin_user, sample_device):
    """Integridad referencial: Eliminar equipo desvincula incidentes y mantenimientos sin destruirlos."""
    # Crear un incidente y un mantenimiento asociados a la cámara
    inc = Incident(
        title="Falla lente",
        description="Doble imagen",
        device_id=sample_device.id,
        created_by_id=admin_user.id
    )
    maint = Maintenance(
        type="Preventivo",
        title="Mantenimiento preventivo",
        description="Limpieza",
        scheduled_date=datetime.datetime.utcnow(),
        device_id=sample_device.id,
        created_by_id=admin_user.id
    )
    db.add_all([inc, maint])
    db.commit()

    token = create_access_token({"sub": admin_user.username})
    client.cookies.set("access_token", f"Bearer {token}")
    client.cookies.set("active_site", "san-agustin")

    response = client.post(
        f"/devices/{sample_device.id}/delete",
        data={"admin_password": "AdminPass123!"},
        follow_redirects=False
    )
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert "/devices?msg=" in response.headers["location"]

    # El equipo fue eliminado
    assert db.query(Device).filter(Device.id == sample_device.id).first() is None

    # El historial del incidente y mantenimiento sobrevive con device_id = None
    db.refresh(inc)
    db.refresh(maint)
    assert inc.device_id is None
    assert maint.device_id is None


def test_validador_cannot_create_device_web(client, db, validador_user, active_license):
    """Regla de Seguridad: El rol Validador no puede registrar nuevos equipos en CCTV."""
    token = create_access_token({"sub": validador_user.username})
    client.cookies.set("access_token", f"Bearer {token}")
    client.cookies.set("active_site", "san-agustin")

    form_data = {
        "name": 'Cámara Domo Validador Test',
        "device_type": "Cámara Domo",
        "location_detail": 'Cam 1 "Terminal"',
        "brand": "Dahua",
        "model": "DH-TEST",
        "serial_number": "VAL-DOMO-001122",
        "ip_address": "192.168.10.99",
        "sede": "San Agustín (Huila)"
    }
    response = client.post("/devices", data=form_data, follow_redirects=False)
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert "error=" in response.headers["location"]
    assert "Validador" in response.headers["location"]

    # Verificar que NO se creó el equipo en la base de datos
    dev = db.query(Device).filter(Device.serial_number == "VAL-DOMO-001122").first()
    assert dev is None


def test_validador_devices_view_button_disabled(client, validador_user, active_license):
    """UI: En la vista de inventario, el botón Registrar Equipo aparece deshabilitado para el Validador."""
    token = create_access_token({"sub": validador_user.username})
    client.cookies.set("access_token", f"Bearer {token}")
    client.cookies.set("active_site", "san-agustin")

    response = client.get("/devices")
    assert response.status_code == status.HTTP_200_OK
    assert "Acceso restringido: El rol Validador" in response.text

