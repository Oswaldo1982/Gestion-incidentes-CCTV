import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import Base

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

    incident = relationship("Incident")
    creator = relationship("User", foreign_keys=[created_by_id])
    device = relationship("Device", back_populates="maintenances")

    def __repr__(self):
        return f"<Maintenance id={self.id} type={self.type} status={self.status}>"
