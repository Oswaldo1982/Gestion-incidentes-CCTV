from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.config import settings

# Determinar URL efectiva de la base de datos (Producción o Sandbox Demo Volátil)
db_url = settings.effective_database_url

connect_args = {}
engine_kwargs = {}

if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    if ":memory:" in db_url or db_url == "sqlite://":
        # StaticPool mantiene la base de datos en memoria viva durante todo el ciclo de vida del proceso
        engine_kwargs["poolclass"] = StaticPool
else:
    # Optimización de Concurrencia y Conectividad para PostgreSQL en Producción
    engine_kwargs["pool_size"] = 20
    engine_kwargs["max_overflow"] = 10
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 1800

engine_kwargs["connect_args"] = connect_args

engine = create_engine(
    db_url,
    **engine_kwargs
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Configura la conexión SQLite para activar explícitamente el modo WAL (Write-Ahead Logging)
    y PRAGMA synchronous=NORMAL, evitando bloqueos por concurrencia ('database is locked')
    en entornos de producción o múltiples hilos.
    """
    if db_url.startswith("sqlite"):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()
        except Exception:
            # En bases de datos en memoria o SQLite con configuraciones restringidas
            pass

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from sqlalchemy import text

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

def ensure_database_schema(target_engine):
    """Verifica y agrega columnas faltantes en tablas existentes sin alterar datos (PostgreSQL y SQLite)."""
    if target_engine.dialect.name == "postgresql":
        try:
            with target_engine.connect() as conn:
                alter_queries = [
                    "ALTER TABLE incidents ALTER COLUMN status TYPE VARCHAR(100);",
                    "ALTER TABLE incidents ALTER COLUMN priority TYPE VARCHAR(50);",
                    "ALTER TABLE maintenances ALTER COLUMN status TYPE VARCHAR(100);",
                    "ALTER TABLE maintenances ALTER COLUMN priority TYPE VARCHAR(50);",
                    "ALTER TABLE maintenances ALTER COLUMN type TYPE VARCHAR(50);",
                    "ALTER TABLE devices ALTER COLUMN status TYPE VARCHAR(50);"
                ]
                for q in alter_queries:
                    try:
                        conn.execute(text(q))
                        conn.commit()
                    except Exception:
                        pass
        except Exception as e:
            print(f"[!] Aviso al sincronizar columnas postgres: {e}")
        return

    if target_engine.dialect.name != "sqlite":
        return
    try:
        with target_engine.connect() as conn:
            # Inspeccionar columnas de la tabla users
            result = conn.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result.fetchall()]
            if columns:
                if "full_name" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR"))
                if "document_id" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN document_id VARCHAR"))
                if "assigned_site" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN assigned_site VARCHAR"))
                if "must_change_password" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT 0"))
                if "temp_expires_at" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN temp_expires_at DATETIME"))
                if "badge_number" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN badge_number VARCHAR(30)"))
                if "signature_path" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN signature_path VARCHAR"))
                conn.commit()

            # Inspeccionar columnas de la tabla incidents
            result_inc = conn.execute(text("PRAGMA table_info(incidents)"))
            inc_cols = [row[1] for row in result_inc.fetchall()]
            if inc_cols:
                if "ticket_number" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN ticket_number VARCHAR(50)"))
                if "fault_type" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN fault_type VARCHAR(50)"))
                if "location_detail" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN location_detail VARCHAR(150)"))
                if "root_cause" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN root_cause TEXT"))
                if "solution" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN solution TEXT"))
                if "closed_by_id" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN closed_by_id INTEGER"))
                if "attended_at" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN attended_at DATETIME"))
                if "closed_at" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN closed_at DATETIME"))
                if "closing_image_path" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN closing_image_path VARCHAR(255)"))
                if "validator_id" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN validator_id INTEGER"))
                if "validated_at" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN validated_at DATETIME"))
                if "validation_status" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN validation_status VARCHAR(50)"))
                if "validation_notes" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN validation_notes TEXT"))
                if "rejection_photo" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN rejection_photo VARCHAR(255)"))
                if "timer_reset_at" not in inc_cols:
                    conn.execute(text("ALTER TABLE incidents ADD COLUMN timer_reset_at DATETIME"))
                conn.commit()

            # Inspeccionar columnas de la tabla maintenances
            result_maint = conn.execute(text("PRAGMA table_info(maintenances)"))
            maint_cols = [row[1] for row in result_maint.fetchall()]
            if maint_cols:
                if "protocol_code" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN protocol_code VARCHAR(50)"))
                if "maintenance_type" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN maintenance_type VARCHAR(50)"))
                if "location_detail" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN location_detail VARCHAR(150)"))
                if "priority" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN priority VARCHAR(20) DEFAULT 'Media'"))
                if "checklist_results" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN checklist_results TEXT"))
                if "technical_findings" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN technical_findings TEXT"))
                if "actions_taken" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN actions_taken TEXT"))
                if "recommendations" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN recommendations TEXT"))
                if "execution_date" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN execution_date DATETIME"))
                if "completed_by_id" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN completed_by_id INTEGER"))
                if "completion_photo" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN completion_photo VARCHAR(255)"))
                if "validator_id" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN validator_id INTEGER"))
                if "validated_at" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN validated_at DATETIME"))
                if "validation_status" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN validation_status VARCHAR(50)"))
                if "validation_notes" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN validation_notes TEXT"))
                if "rejection_photo" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN rejection_photo VARCHAR(255)"))
                if "timer_reset_at" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN timer_reset_at DATETIME"))
                if "rca_cause_factor" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN rca_cause_factor VARCHAR(150)"))
                if "rca_failure_mechanism" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN rca_failure_mechanism VARCHAR(150)"))
                if "operating_condition" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN operating_condition VARCHAR(100)"))
                if "asset_component" not in maint_cols:
                    conn.execute(text("ALTER TABLE maintenances ADD COLUMN asset_component VARCHAR(100)"))
                conn.commit()

            # Enforce single superadmin: migrate any secondary Admin accounts to operational roles
            result_users = conn.execute(text("PRAGMA table_info(users)"))
            user_cols = [row[1] for row in result_users.fetchall()]
            if user_cols:
                # Primary superadmin is ID 1 or username 'admin'. All secondary admins become operational roles.
                conn.execute(text("UPDATE users SET role = 'Supervisor' WHERE role = 'Admin' AND id != 1 AND username != 'admin'"))
                conn.commit()

            # Asegurar tablas del sistema de licenciamiento por sitio (4 sitios, 3 años)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS site_licenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id VARCHAR NOT NULL,
                    site_name VARCHAR NOT NULL,
                    year INTEGER NOT NULL,
                    password_hash VARCHAR NOT NULL,
                    password_mask VARCHAR NOT NULL,
                    certificate_code VARCHAR NOT NULL UNIQUE,
                    is_activated BOOLEAN DEFAULT 0 NOT NULL,
                    activated_at DATETIME,
                    expires_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS site_activation_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id VARCHAR NOT NULL UNIQUE,
                    first_access_at DATETIME,
                    current_year INTEGER DEFAULT 1 NOT NULL,
                    status VARCHAR DEFAULT 'GRACE_PERIOD' NOT NULL,
                    failed_attempts INTEGER DEFAULT 0 NOT NULL,
                    lockout_until DATETIME,
                    last_activated_at DATETIME,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))
            conn.commit()
    except Exception as e:
        print(f"[!] Aviso al sincronizar esquema de base de datos: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Asegurar esquema al importar el módulo
ensure_database_schema(engine)
