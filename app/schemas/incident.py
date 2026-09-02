from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

class IncidentBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    description: str = Field(..., min_length=5)
    priority: Literal["Baja", "Media", "Alta", "Crítica"] = "Media"

class IncidentCreate(IncidentBase):
    pass

class IncidentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = Field(None, min_length=5)
    status: Optional[Literal["Abierto", "En Proceso", "Resuelto", "Cerrado"]] = None
    priority: Optional[Literal["Baja", "Media", "Alta", "Crítica"]] = None
    assigned_to_id: Optional[int] = None

class IncidentResponse(BaseModel):
    id: int
    title: str
    description: str
    status: str
    priority: str
    created_by_id: int
    assigned_to_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
