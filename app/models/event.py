import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import Base

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)
    maintenance_id = Column(Integer, ForeignKey("maintenances.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(String(50), nullable=False)                 # CREATION, STATUS_CHANGE, COMMENT, ASSIGNMENT, etc.
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    user = relationship("User")
    incident = relationship("Incident")
    maintenance = relationship("Maintenance")

    def __repr__(self):
        return f"<Event id={self.id} event_type={self.event_type} user_id={self.user_id}>"
