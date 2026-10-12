from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class SiteBaseSchema(BaseModel):
    id: str = Field(..., min_length=2, max_length=50, description="Identificador único (slug) de la sede, ej: san-agustin")
    name: str = Field(..., min_length=2, max_length=100, description="Nombre de la sede")
    full_name: str = Field(..., min_length=2, max_length=150, description="Nombre completo territorial")
    region: Optional[str] = Field(default="", max_length=100)
    badge: Optional[str] = Field(default="", max_length=100)
    description: Optional[str] = Field(default="", max_length=255)
    icon: Optional[str] = Field(default="🏛️", max_length=50)
    cameras_count: Optional[int] = Field(default=0, ge=0)
    status: Optional[str] = Field(default="Operativo", max_length=50)
    color: Optional[str] = Field(default="blue", max_length=50)
    default_supervisor: Optional[str] = Field(default="", max_length=100)
    is_active: Optional[bool] = True


class SiteCreate(SiteBaseSchema):
    pass


class SiteUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    full_name: Optional[str] = Field(None, min_length=2, max_length=150)
    region: Optional[str] = Field(None, max_length=100)
    badge: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    icon: Optional[str] = Field(None, max_length=50)
    cameras_count: Optional[int] = Field(None, ge=0)
    status: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=50)
    default_supervisor: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None


class SiteResponse(SiteBaseSchema):
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SiteListResponse(BaseModel):
    items: List[SiteResponse]
    total: int
