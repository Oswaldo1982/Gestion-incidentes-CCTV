import datetime
from typing import Optional, Dict, Any
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, DateTime
from app.models.base import Base


class SiteBase(SQLModel):
    id: str = Field(primary_key=True, max_length=50, description="Identificador único (slug) de la sede, ej: san-agustin")
    name: str = Field(max_length=100, description="Nombre de la sede, ej: San Agustín")
    full_name: str = Field(max_length=150, description="Nombre completo territorial, ej: San Agustín (Huila)")
    region: Optional[str] = Field(default="", max_length=100, description="Departamento o región")
    badge: Optional[str] = Field(default="", max_length=100, description="Etiqueta distintiva del circuito")
    description: Optional[str] = Field(default="", max_length=255, description="Descripción de cobertura territorial")
    icon: Optional[str] = Field(default="🏛️", max_length=50, description="Icono o emoji representativo")
    cameras_count: int = Field(default=0, description="Cantidad estimada o base de cámaras")
    status: str = Field(default="Operativo", max_length=50, description="Estado operativo de la sede")
    color: Optional[str] = Field(default="blue", max_length=50, description="Color identificador para la interfaz")
    default_supervisor: Optional[str] = Field(default="", max_length=100, description="Usuario supervisor asignado por defecto")
    is_active: bool = Field(default=True, description="Indica si la sede está activa en el sistema")


class Site(SiteBase, table=True):
    __tablename__ = "sites"
    metadata = Base.metadata

    created_at: Optional[datetime.datetime] = Field(default=None, sa_column=Column(DateTime, default=datetime.datetime.utcnow, nullable=False))
    updated_at: Optional[datetime.datetime] = Field(default=None, sa_column=Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False))

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
            "is_active": self.is_active
        }
