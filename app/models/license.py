import datetime
from sqlalchemy import Integer, String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class License(Base):
    """Modelo legacy para compatibilidad retroactiva con tests unitarios existentes."""
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    license_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    activated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<License id={self.id} is_active={self.is_active}>"


class SiteLicenseKey(Base):
    """
    Registro individual de contraseña de activación para un sitio y un año específico.
    Total: 4 sitios * 3 años = 12 credenciales maestras.
    Almacena únicamente el hash criptográfico para máxima seguridad ante inspecciones de BD.
    """
    __tablename__ = "site_licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    site_id: Mapped[str] = mapped_column(String, index=True, nullable=False)  # san-agustin, san-jose-guaviare, el-retorno, calamar
    site_name: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3
    password_hash: Mapped[str] = mapped_column(String, nullable=False)  # Hash seguro (bcrypt)
    password_mask: Mapped[str] = mapped_column(String, nullable=False)  # Ej. "****-****-****-W4Y8"
    certificate_code: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)  # Ej: "LIC-SANAGUSTIN-Y1-XXXX"
    is_activated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    activated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<SiteLicenseKey site={self.site_id} year={self.year} activated={self.is_activated}>"


class SiteActivationState(Base):
    """
    Estado del ciclo de vida y control de activación por sitio:
    - 24 horas de periodo de gracia tras el primer despliegue / primer acceso
    - Bloqueo y solicitud de contraseña de Año 1 al expirar las 24 horas
    - Renovación anual para Año 2 y Año 3
    - Control de intentos fallidos para prevenir ataques de fuerza bruta
    """
    __tablename__ = "site_activation_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    site_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    first_access_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    current_year: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String, default="GRACE_PERIOD", nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lockout_until: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    last_activated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False
    )

    def __repr__(self):
        return f"<SiteActivationState site={self.site_id} status={self.status} year={self.current_year}>"
