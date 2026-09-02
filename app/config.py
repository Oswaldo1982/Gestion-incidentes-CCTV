import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Modo Demo / Sandbox (Volátil en Memoria)
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "t", "yes", "demo")
    DEMO_DATABASE_URL: str = os.getenv("DEMO_DATABASE_URL", "sqlite:///:memory:")

    # Base de Datos de Producción / Desarrollo Estándar
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./sqlite.db")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-super-secret-key-change-it-in-production-12345")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    
    # Licenciamiento
    LICENSE_SECRET_KEY: str = os.getenv("LICENSE_SECRET_KEY", "license-hmac-secret-key-987654321")
    
    # Credenciales Administrador Inicial
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@example.com")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")

    @property
    def effective_database_url(self) -> str:
        """
        Retorna la URL de base de datos correspondiente:
        - Si DEMO_MODE es True, utiliza SQLite volátil en memoria (sqlite:///:memory:).
        - Si DEMO_MODE es False, utiliza la base de datos persistente (sqlite.db o PostgreSQL).
        """
        if self.DEMO_MODE:
            return self.DEMO_DATABASE_URL
        return self.DATABASE_URL

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
