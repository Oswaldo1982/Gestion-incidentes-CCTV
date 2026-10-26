import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from app.utils.timezone import get_local_now


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String(100), default="", nullable=True)
    badge: Mapped[Optional[str]] = mapped_column(String(100), default="", nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), default="", nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(50), default="🏛️", nullable=True)
    cameras_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="Operativo", nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(50), default="blue", nullable=True)
    default_supervisor: Mapped[Optional[str]] = mapped_column(String(100), default="", nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=get_local_now, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=get_local_now, onupdate=get_local_now, nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "full_name": self.full_name,
            "region": self.region,
            "badge": self.badge,
            "description": self.description,
            "icon": self.icon,
            "cameras_count": self.cameras_count,
            "status": self.status,
            "color": self.color,
            "default_supervisor": self.default_supervisor,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
