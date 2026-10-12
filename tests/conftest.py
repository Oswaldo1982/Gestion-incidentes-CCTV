import os
from datetime import datetime, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
import app.database as app_db
from app.models.user import User
from app.models.license import License
from app.models.device import Device
from app.models.site import Site
from app.models.incident import Incident  # noqa: F401
from app.models.maintenance import Maintenance  # noqa: F401
from app.models.event import Event  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.utils.security import get_password_hash, generate_license_key
from app.config import settings
from app.auth import create_access_token
from app.main import app as fastapi_app

# Asegurar ambiente de pruebas
settings.DEMO_MODE = False
os.environ["DEMO_MODE"] = "False"

# Configuración de base de datos SQLite en memoria aislada para pruebas
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine
)

# Interceptar SessionLocal del módulo app.database
app_db.engine = test_engine
app_db.SessionLocal = TestingSessionLocal


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Crea el esquema inicial antes de los tests."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def clean_database():
    """Limpia los datos entre ejecuciones manteniendo el esquema."""
    yield
    with test_engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()


@pytest.fixture
def db():
    """Proporciona una sesión de base de datos para pruebas."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    """Cliente de pruebas FastAPI con get_db sobreescrito a base en memoria."""
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def active_license(db):
    """Crea una licencia válida y activa en la base de datos."""
    db.query(License).delete()
    expiry = (datetime.utcnow() + timedelta(days=365)).strftime("%Y-%m-%d")
    payload = {
        "client": "Municipio San Agustin Test",
        "expires": expiry,
        "max_users": 10
    }
    key = generate_license_key(payload, settings.LICENSE_SECRET_KEY)
    lic = License(license_key=key, is_active=True)
    db.add(lic)
    db.commit()
    db.refresh(lic)
    return lic


@pytest.fixture
def admin_user(db):
    """Crea un usuario administrador por defecto."""
    existing = db.query(User).filter(User.username == "admin").first()
    if existing:
        return existing
    user = User(
        username="admin",
        email="admin@test.gov.co",
        full_name="Administrador Principal",
        document_id="1000000001",
        assigned_site="Todas las Sedes",
        hashed_password=get_password_hash("AdminPass123!"),
        role="Admin",
        is_active=True,
        must_change_password=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def supervisor_user(db):
    """Crea un usuario con rol Supervisor."""
    existing = db.query(User).filter(User.username == "supervisor").first()
    if existing:
        return existing
    user = User(
        username="supervisor",
        email="supervisor@test.gov.co",
        full_name="Supervisor Técnico",
        document_id="1000000002",
        assigned_site="San Agustín (Huila)",
        hashed_password=get_password_hash("SuperPass123!"),
        role="Supervisor",
        is_active=True,
        must_change_password=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def operario_user(db):
    """Crea un usuario con rol Operario/Técnico de Mantenimiento."""
    existing = db.query(User).filter(User.username == "operario").first()
    if existing:
        return existing
    user = User(
        username="operario",
        email="operario@test.gov.co",
        full_name="Operario Técnico de Campo",
        document_id="1000000003",
        assigned_site="San Agustín (Huila)",
        hashed_password=get_password_hash("OperPass123!"),
        role="Operario",
        is_active=True,
        must_change_password=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def validador_user(db):
    """Crea un usuario con rol Validador."""
    existing = db.query(User).filter(User.username == "validador").first()
    if existing:
        return existing
    user = User(
        username="validador",
        email="validador@test.gov.co",
        full_name="Ingeniero Validador de Calidad",
        document_id="1000000004",
        assigned_site="Todas las Sedes",
        hashed_password=get_password_hash("ValPass123!"),
        role="Validador",
        is_active=True,
        must_change_password=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def mantenimiento_user(db):
    """Crea un usuario con rol Empresa de Mantenimiento."""
    existing = db.query(User).filter(User.username == "mantenimiento_contratista").first()
    if existing:
        return existing
    user = User(
        username="mantenimiento_contratista",
        email="contratista@test.gov.co",
        full_name="Consorcio CCTV Mantenimiento",
        document_id="1000000005",
        assigned_site="Todas las Sedes",
        hashed_password=get_password_hash("MantPass123!"),
        role="Empresa de Mantenimiento",
        is_active=True,
        must_change_password=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user):
    token = create_access_token({"sub": admin_user.username})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def supervisor_headers(supervisor_user):
    token = create_access_token({"sub": supervisor_user.username})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def operario_headers(operario_user):
    token = create_access_token({"sub": operario_user.username})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def validador_headers(validador_user):
    token = create_access_token({"sub": validador_user.username})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mantenimiento_headers(mantenimiento_user):
    token = create_access_token({"sub": mantenimiento_user.username})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_device(db):
    """Crea un equipo CCTV de prueba."""
    device = Device(
        name='Cámara PTZ 01 "Parque Principal"',
        device_type="Cámara PTZ",
        brand="Hikvision",
        model="DS-2DE4425IW-DE",
        serial_number="HK-PTZ-987654",
        ip_address="192.168.10.25",
        mac_address="AA:BB:CC:DD:EE:01",
        sede="San Agustín (Huila)",
        location_detail='Cam 1 "Terminal"',
        status="Operativo"
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@pytest.fixture
def sample_site(db):
    """Crea una sede territorial de prueba."""
    site = Site(
        id="san-agustin",
        name="San Agustín",
        full_name="San Agustín (Huila)",
        region="Huila",
        badge="Circuito Arqueológico",
        description="Parque Arqueológico, Terminal y Red Hospitalaria",
        icon="🏛️",
        cameras_count=18,
        status="Operativo",
        color="blue",
        default_supervisor="supervisor_sanagustin",
        is_active=True
    )
    db.add(site)
    db.commit()
    db.refresh(site)
    return site
