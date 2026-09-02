import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="Responsable", nullable=False)  # Admin, Supervisor, Responsable
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relaciones
    created_incidents = relationship("Incident", back_populates="creator", foreign_keys="Incident.created_by_id")
    assigned_incidents = relationship("Incident", back_populates="assignee", foreign_keys="Incident.assigned_to_id")
    created_maintenances = relationship("Maintenance", back_populates="creator", foreign_keys="Maintenance.created_by_id")
    events = relationship("Event", back_populates="user")

    def __repr__(self):
        return f"<User username={self.username} role={self.role}>"


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)                        # Ej. Cámara PTZ Domo 01, NVR Principal 32CH
    device_type = Column(String(50), nullable=False)                  # Cámara PTZ, Cámara Domo, Cámara Bala, NVR, UPS, Switch
    brand = Column(String(50), nullable=True)                         # Hikvision, Dahua, Cisco, APC, etc.
    model = Column(String(50), nullable=True)
    serial_number = Column(String(100), nullable=True, index=True)
    ip_address = Column(String(50), nullable=True)
    mac_address = Column(String(50), nullable=True)
    sede = Column(String(100), nullable=False)                        # San Agustín, Huila (Sede Principal), Sede 2, etc.
    location_detail = Column(String(150), nullable=True)              # Entrada Principal, Cuarto de Servidores, etc.
    status = Column(String(20), default="Operativo", nullable=False)  # Operativo, Alerta Menor, En Falla, Mantenimiento, Inactivo
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relaciones
    incidents = relationship("Incident", back_populates="device")
    maintenances = relationship("Maintenance", back_populates="device")

    def __repr__(self):
        return f"<Device id={self.id} name={self.name} type={self.device_type} status={self.status}>"


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(20), default="Abierto", nullable=False)  # Abierto, En Proceso, Resuelto, Cerrado
    priority = Column(String(20), default="Media", nullable=False)   # Baja, Media, Alta, Crítica
    sede = Column(String(100), nullable=True)
    image_path = Column(String(255), nullable=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    # Relaciones
    creator = relationship("User", foreign_keys=[created_by_id], back_populates="created_incidents")
    assignee = relationship("User", foreign_keys=[assigned_to_id], back_populates="assigned_incidents")
    device = relationship("Device", back_populates="incidents")
    maintenances = relationship("Maintenance", back_populates="incident")
    events = relationship("Event", back_populates="incident")

    def __repr__(self):
        return f"<Incident id={self.id} title={self.title} status={self.status} priority={self.priority}>"


class Maintenance(Base):
    __tablename__ = "maintenances"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(20), nullable=False)                         # Preventivo, Correctivo
    title = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    scheduled_date = Column(DateTime, nullable=False)
    completed_date = Column(DateTime, nullable=True)
    status = Column(String(20), default="Programado", nullable=False) # Programado, En Ejecución, Completado, Cancelado
    sede = Column(String(100), nullable=True)
    image_path = Column(String(255), nullable=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relaciones
    incident = relationship("Incident", back_populates="maintenances")
    creator = relationship("User", foreign_keys=[created_by_id], back_populates="created_maintenances")
    device = relationship("Device", back_populates="maintenances")
    events = relationship("Event", back_populates="maintenance")

    def __repr__(self):
        return f"<Maintenance id={self.id} type={self.type} status={self.status}>"


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)
    maintenance_id = Column(Integer, ForeignKey("maintenances.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(String(50), nullable=False)                 # CREATION, STATUS_CHANGE, COMMENT, ASSIGNMENT, etc.
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relaciones
    user = relationship("User", back_populates="events")
    incident = relationship("Incident", back_populates="events")
    maintenance = relationship("Maintenance", back_populates="events")

    def __repr__(self):
        return f"<Event id={self.id} event_type={self.event_type} user_id={self.user_id}>"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String(50), nullable=True, index=True)
    action = Column(String(50), nullable=False, index=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<AuditLog action={self.action} username={self.username} timestamp={self.timestamp}>"


class License(Base):
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True, index=True)
    license_key = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    activated_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<License id={self.id} is_active={self.is_active}>"


__all__ = ["Base", "User", "Device", "Incident", "Maintenance", "Event", "AuditLog", "License"]
