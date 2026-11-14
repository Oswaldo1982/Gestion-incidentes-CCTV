from typing import Optional
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Carga de variables de entorno desde el archivo .env si existe
load_dotenv()

class Settings(BaseSettings):
    # Modo Demo / Sandbox (Volátil en Memoria)
    DEMO_MODE: bool = False
    DEMO_DATABASE_URL: str = "sqlite:///:memory:"

    # Modo Desarrollador (Bypass Total de Restricciones y Licencias para Desarrollo/Pruebas)
    DEV_MODE: bool = False

    # Suspensión de Licenciamiento Multi-Sede (Por solicitud administrativa)
    SUSPEND_SITE_LICENSING: bool = True

    # Base de Datos de Producción / Desarrollo Estándar
    DATABASE_URL: str = "sqlite:///./sqlite.db"
    UPLOAD_DIR: str = "static/uploads"
    SECRET_KEY: str = "cctv-secret-key-production-2026"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 20
    
    # Licenciamiento
    LICENSE_SECRET_KEY: str = "license-hmac-secret-key-987654321"
    
    # Credenciales Administrador Inicial
    ADMIN_USERNAME: str = "admin"
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "admin123"

    # Configuración de Correo Electrónico (SMTP)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "notificaciones@cctv-seguridad.gov.co"
    SMTP_FROM_NAME: str = "Sistema CCTV Institucional"
    SMTP_USE_TLS: bool = True

    @property
    def effective_database_url(self) -> str:
        """
        Retorna la URL de base de datos persistente (PostgreSQL en Railway o sqlite.db en local).
        Garantiza que tanto San Agustín como el Sitio de Prueba (Demo) persistan
        en el mismo motor de almacenamiento duradero sin pérdida de datos tras reinicios.
        """
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

