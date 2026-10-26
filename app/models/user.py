import datetime
from typing import Optional
from sqlalchemy import Integer, String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    document_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    assigned_site: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, default="Empresa de Mantenimiento", nullable=False)  # Admin, Validador, Supervisor, Empresa de Mantenimiento (alias Operario)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    temp_expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    badge_number: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True, nullable=True)
    signature_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<User username={self.username} role={self.role}>"
