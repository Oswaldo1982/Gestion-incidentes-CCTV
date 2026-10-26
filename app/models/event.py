import datetime
from typing import Optional
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.models.base import Base
from app.utils.timezone import get_local_now

class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    incident_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("incidents.id"), nullable=True)
    maintenance_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("maintenances.id"), nullable=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)                 # CREATION, STATUS_CHANGE, COMMENT, ASSIGNMENT, etc.
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=get_local_now, nullable=False)

    user = relationship("User")
    incident = relationship("Incident")
    maintenance = relationship("Maintenance")

    def __repr__(self):
        return f"<Event id={self.id} event_type={self.event_type} user_id={self.user_id}>"
