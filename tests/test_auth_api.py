from fastapi import status
from app.models.license import License
from app.models.user import User
from app.utils.security import get_password_hash


def test_auth_login_happy_path(client, admin_user, active_license):
    """Happy path: Inicio de sesión exitoso con retorno de JWT Bearer."""
    response = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "AdminPass123!"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_auth_login_invalid_password(client, admin_user, active_license):
    """Error esperado: Contraseña incorrecta devuelve HTTP 401."""
    response = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "WrongPassword"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Usuario o contraseña incorrectos" in response.json()["detail"]


def test_auth_login_unknown_user(client, active_license):
    """Error esperado: Usuario inexistente devuelve HTTP 401."""
    response = client.post(
        "/api/auth/login",
        data={"username": "non_existent_user", "password": "SomePassword123"}
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_auth_login_inactive_user(client, db, active_license):
    """Error esperado: Cuenta inactiva no puede autenticarse (HTTP 403)."""
    user = User(
        username="disabled_user",
        email="disabled@test.gov.co",
        hashed_password=get_password_hash("Pass123!"),
        role="Operario",
        is_active=False
    )
    db.add(user)
    db.commit()

    response = client.post(
        "/api/auth/login",
        data={"username": "disabled_user", "password": "Pass123!"}
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "desactivada" in response.json()["detail"]


def test_auth_login_license_required_for_non_admin(client, db, operario_user):
    """Regla de negocio: Si no hay licencia activa, los usuarios no-Admin no pueden ingresar (HTTP 402)."""
    # Eliminar cualquier licencia activa
    db.query(License).delete()
    db.commit()

    response = client.post(
        "/api/auth/login",
        data={"username": "operario", "password": "OperPass123!"}
    )
    assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
    assert "Acceso denegado" in response.json()["detail"]


def test_auth_login_admin_allowed_without_license(client, db, admin_user):
    """Regla de negocio: El Administrador SÍ puede ingresar sin licencia para cargar una nueva."""
    db.query(License).delete()
    db.commit()

    response = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "AdminPass123!"}
    )
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.json()


def test_web_login_role_mismatch_rejected(client, db, active_license):
    """Regla de negocio: Si se selecciona rol Administrador pero se ingresan credenciales de Validador, se rechaza."""
    val_user = User(
        username="validador_test_match",
        email="validador_match@test.gov.co",
        hashed_password=get_password_hash("ValPass123!"),
        role="Validador",
        assigned_site="Todas las Sedes",
        is_active=True
    )
    db.add(val_user)
    db.commit()

    resp = client.post(
        "/login",
        data={
            "site_id": "san-agustin",
            "role_type": "admin",
            "username": "validador_match@test.gov.co",
            "password": "ValPass123!"
        },
        follow_redirects=False
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Las credenciales ingresadas son incorrectas." in resp.text


def test_web_login_site_mismatch_rejected(client, db, active_license):
    """Regla de negocio: Si el usuario está asignado a Calamar e intenta ingresar a San Agustín, se rechaza."""
    calamar_user = User(
        username="sup_calamar_only",
        email="sup_calamar@test.gov.co",
        hashed_password=get_password_hash("SupPass123!"),
        role="Supervisor",
        assigned_site="Calamar (Guaviare)",
        is_active=True
    )
    db.add(calamar_user)
    db.commit()

    resp = client.post(
        "/login",
        data={
            "site_id": "san-agustin",
            "role_type": "supervisor",
            "username": "sup_calamar@test.gov.co",
            "password": "SupPass123!"
        },
        follow_redirects=False
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Las credenciales ingresadas son incorrectas." in resp.text


def test_web_login_happy_path_with_matching_role_and_site(client, db, active_license):
    """Regla de negocio: Credenciales, rol y sede coincidentes permiten el ingreso exitoso."""
    val_user = User(
        username="val_sanagustin_ok",
        email="val_sa@test.gov.co",
        hashed_password=get_password_hash("ValPass123!"),
        role="Validador",
        assigned_site="San Agustín (Huila)",
        is_active=True
    )
    db.add(val_user)
    db.commit()

    resp = client.post(
        "/login",
        data={
            "site_id": "san-agustin",
            "role_type": "validador",
            "username": "val_sa@test.gov.co",
            "password": "ValPass123!"
        },
        follow_redirects=False
    )
    assert resp.status_code == status.HTTP_303_SEE_OTHER
    assert resp.headers["location"] == "/dashboard"

