import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from app.models.base import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    device_type = Column(String(50), nullable=False)  # Cámara PTZ, Cámara Domo, Cámara Bala, NVR, UPS, Switch
    brand = Column(String(50), nullable=True)
    model = Column(String(50), nullable=True)
    serial_number = Column(String(100), nullable=True, index=True)
    ip_address = Column(String(50), nullable=True)
    mac_address = Column(String(50), nullable=True)
    sede = Column(String(100), nullable=False)        # San Agustín, Huila (Sede Principal), Sede 2, etc.
    location_detail = Column(String(150), nullable=True)
    status = Column(String(20), default="Operativo", nullable=False) # Operativo, Alerta Menor, En Falla, Mantenimiento, Inactivo
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relaciones
    incidents = relationship("Incident", back_populates="device")
    maintenances = relationship("Maintenance", back_populates="device")

    def __repr__(self):
        return f"<Device id={self.id} name={self.name} type={self.device_type} status={self.status}>"
