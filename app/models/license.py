import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.models.base import Base

class License(Base):
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True, index=True)
    license_key = Column(String, nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    activated_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<License id={self.id} is_active={self.is_active}>"
