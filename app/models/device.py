import datetime
from typing import Optional
from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.models.base import Base
from app.utils.timezone import get_local_now


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_type: Mapped[str] = mapped_column(String(50), nullable=False)  # Cámara PTZ, Cámara Domo, Cámara Bala, NVR, UPS, Switch
    brand: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    mac_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sede: Mapped[str] = mapped_column(String(100), nullable=False)        # San Agustín, Huila (Sede Principal), Sede 2, etc.
    location_detail: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Operativo", nullable=False) # Operativo, Alerta Menor, En Falla, Mantenimiento, Inactivo
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=get_local_now, nullable=False)

    # Relaciones
    incidents = relationship("Incident", back_populates="device")
    maintenances = relationship("Maintenance", back_populates="device")

    @property
    def calculated_status(self) -> str:
        """
        Calcula el estado operativo en tiempo real derivado de incidentes y mantenimientos:
        - 'Inactivo': Si fue desactivado administrativamente.
        - 'En Falla': Si tiene al menos un incidente en estado 'Abierto' o 'En Proceso'.
        - 'En Mantenimiento': Si tiene un mantenimiento en estado 'En Ejecución' o 'Programado'.
        - 'Operativo': En cualquier otro caso.
        """
        if self.status == "Inactivo":
            return "Inactivo"
        if hasattr(self, "incidents") and self.incidents:
            for inc in self.incidents:
                if inc.status in ["Abierto", "En Proceso"]:
                    return "En Falla"
        if hasattr(self, "maintenances") and self.maintenances:
            for maint in self.maintenances:
                if maint.status in ["En Ejecución", "Programado"]:
                    return "En Mantenimiento"
        return "Operativo"

    @property
    def active_incident(self):
        """Retorna el incidente activo más reciente si existe."""
        if hasattr(self, "incidents") and self.incidents:
            for inc in self.incidents:
                if inc.status in ["Abierto", "En Proceso"]:
                    return inc
        return None

    def __repr__(self):
        return f"<Device id={self.id} name={self.name} type={self.device_type} status={self.calculated_status}>"

