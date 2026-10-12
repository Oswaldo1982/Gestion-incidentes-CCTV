from fastapi import status
from app.models.user import User
from app.models.incident import Incident
from app.models.license import License
from app.utils.security import generate_license_key
from app.config import settings
import datetime


def test_get_users_admin_allowed(client, admin_headers, supervisor_user, operario_user):
    """Happy path: Administrador obtiene lista completa de usuarios."""
    response = client.get("/api/users", headers=admin_headers)
    assert response.status_code == status.HTTP_200_OK
    users = response.json()
    assert len(users) >= 3
    usernames = [u["username"] for u in users]
    assert "admin" in usernames
    assert "supervisor" in usernames


def test_get_users_forbidden_for_operario(client, operario_headers):
    """Control de acceso: Usuario sin rol Admin recibe HTTP 403."""
    response = client.get("/api/users", headers=operario_headers)
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_create_user_happy_path(client, admin_headers, active_license):
    """Happy path: Administrador crea un nuevo usuario exitosamente."""
    user_payload = {
        "username": "tecnico_sanagustin",
        "email": "tecnico@sanagustin.gov.co",
        "full_name": "Técnico Especialista CCTV",
        "document_id": "1085234567",
        "assigned_site": "San Agustín (Huila)",
        "password": "PasswordUnico2026!",
        "role": "Operario",
        "is_active": True
    }
    response = client.post("/api/users", json=user_payload, headers=admin_headers)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["username"] == "tecnico_sanagustin"
    assert data["email"] == "tecnico@sanagustin.gov.co"
    assert data["role"] == "Operario"


def test_create_user_duplicate_username_or_email(client, admin_headers, active_license, supervisor_user):
    """Error esperado: Intento de registrar usuario con nombre existente lanza HTTP 400."""
    user_payload = {
        "username": "supervisor", # Ya existe
        "email": "nuevo_email@test.com",
        "password": "PasswordUnico2026_2!",
        "role": "Operario"
    }
    response = client.post("/api/users", json=user_payload, headers=admin_headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "ya está registrado" in response.json()["detail"]


def test_create_user_duplicate_document_id(client, admin_headers, active_license, supervisor_user):
    """Error esperado: Intento de registrar cédula duplicada lanza HTTP 400."""
    user_payload = {
        "username": "otro_supervisor",
        "email": "otro_sup@test.com",
        "document_id": supervisor_user.document_id, # Cédula duplicada
        "password": "PasswordUnico2026_3!",
        "role": "Supervisor"
    }
    response = client.post("/api/users", json=user_payload, headers=admin_headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "documento de identidad" in response.json()["detail"]


def test_create_user_password_already_in_use(client, admin_headers, active_license):
    """Regla de seguridad: Contraseña ya usada por otro usuario en el sistema lanza HTTP 400."""
    user_payload = {
        "username": "nuevo_user_pw",
        "email": "nuevo_pw@test.com",
        "password": "AdminPass123!", # Misma contraseña que admin_user
        "role": "Operario"
    }
    response = client.post("/api/users", json=user_payload, headers=admin_headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "ya se encuentra registrada" in response.json()["detail"]


def test_create_user_license_limit_exceeded(client, db, admin_headers):
    """Límite de negocio: No permite crear más usuarios activos que el límite de la licencia."""
    db.query(License).delete()
    expiry = (datetime.datetime.utcnow() + datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    payload = {"client": "Test Limit", "expires": expiry, "max_users": 1}
    key = generate_license_key(payload, settings.LICENSE_SECRET_KEY)
    db.add(License(license_key=key, is_active=True))
    db.commit()

    # Ya existe 1 usuario activo no-Admin
    u1 = User(username="u1", email="u1@test.com", hashed_password="pw1", role="Operario", is_active=True)
    db.add(u1)
    db.commit()

    # Intentar crear un segundo usuario no-admin activo
    response = client.post(
        "/api/users",
        json={
            "username": "usuario_extra",
            "email": "usuario_extra@test.com",
            "password": "UniquePassword123!",
            "role": "Operario",
            "is_active": True
        },
        headers=admin_headers
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Límite de usuarios activos" in response.json()["detail"]


def test_update_user_prevent_self_deactivation(client, admin_headers, admin_user):
    """Regla de seguridad: Un administrador no puede desactivar su propia cuenta."""
    response = client.patch(
        f"/api/users/{admin_user.id}",
        json={"is_active": False},
        headers=admin_headers
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "No puedes desactivar tu propia cuenta" in response.json()["detail"]


def test_delete_user_happy_path(client, db, admin_headers, admin_user, operario_user):
    """Happy path: Administrador elimina un usuario y sus registros se reasignan al administrador."""
    # Crear un incidente creado por el operario
    inc = Incident(
        title="Incidente asignado",
        description="Falla",
        status="Abierto",
        created_by_id=operario_user.id
    )
    db.add(inc)
    db.commit()

    response = client.delete(f"/api/users/{operario_user.id}", headers=admin_headers)
    assert response.status_code == status.HTTP_200_OK

    # Validar que el usuario ya no existe
    assert db.query(User).filter(User.id == operario_user.id).first() is None

    # Validar que el incidente fue reasignado al admin para mantener integridad
    db.refresh(inc)
    assert inc.created_by_id == admin_user.id


def test_delete_user_prevent_deleting_main_admin(client, admin_headers, admin_user):
    """Regla de seguridad: La cuenta principal de administrador inicial no puede eliminarse."""
    response = client.delete(f"/api/users/{admin_user.id}", headers=admin_headers)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "no puede ser eliminada" in response.json()["detail"] or "propia cuenta" in response.json()["detail"]


def test_update_user_activate_exceeds_license_limit(client, db, admin_headers):
    """Regla de licencia: Activar un usuario inactivo respeta el límite max_users de la licencia."""
    db.query(License).delete()
    payload = {
        "client": "Sede Unitaria",
        "expires": (datetime.datetime.utcnow() + datetime.timedelta(days=90)).strftime("%Y-%m-%d"),
        "max_users": 1
    }
    key = generate_license_key(payload, settings.LICENSE_SECRET_KEY)
    db.add(License(license_key=key, is_active=True))

    u_active = User(username="activo_1", email="activo1@test.com", hashed_password="pw", role="Operario", is_active=True)
    u_inactive = User(username="inactivo_2", email="inactivo2@test.com", hashed_password="pw", role="Operario", is_active=False)
    db.add_all([u_active, u_inactive])
    db.commit()

    # Intentar activar u_inactive -> debe fallar porque ya hay 1 usuario activo y max_users=1
    response = client.patch(
        f"/api/users/{u_inactive.id}",
        json={"is_active": True},
        headers=admin_headers
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Límite de usuarios activos" in response.json()["detail"]
