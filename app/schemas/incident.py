from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

class IncidentBase(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=150)
    description: str = Field(..., min_length=5)
    priority: Literal["Baja", "Media", "Alta", "Crítica"] = "Media"
    fault_type: Optional[str] = "Falla Menor"
    location_detail: Optional[str] = None
    device_id: Optional[int] = None
    sede: Optional[str] = None

class IncidentCreate(IncidentBase):
    pass

class IncidentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=150)
    description: Optional[str] = Field(None, min_length=5)
    status: Optional[str] = None
    priority: Optional[Literal["Baja", "Media", "Alta", "Crítica"]] = None
    assigned_to_id: Optional[int] = None
    root_cause: Optional[str] = None
    solution: Optional[str] = None
    closed_by_id: Optional[int] = None
    validation_notes: Optional[str] = None


class IncidentValidate(BaseModel):
    action: Literal["approve", "reject"] = Field(..., description="Dictamen: 'approve' o 'reject'")
    validation_notes: Optional[str] = Field(None, description="Observaciones y justificación técnica del dictamen")
    rejection_photo: Optional[str] = Field(None, description="Ruta o URI de evidencia fotográfica del rechazo")


class IncidentResponse(BaseModel):
    id: int
    ticket_number: Optional[str] = None
    title: str
    description: str
    status: str
    priority: str
    fault_type: Optional[str] = None
    location_detail: Optional[str] = None
    sede: Optional[str] = None
    device_id: Optional[int] = None
    root_cause: Optional[str] = None
    solution: Optional[str] = None
    image_path: Optional[str] = None
    closing_image_path: Optional[str] = None
    rejection_photo: Optional[str] = None
    created_by_id: int
    assigned_to_id: Optional[int] = None
    closed_by_id: Optional[int] = None
    validator_id: Optional[int] = None
    validated_at: Optional[datetime] = None
    validation_status: Optional[str] = None
    validation_notes: Optional[str] = None
    timer_reset_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    attended_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PaginatedIncidentResponse(BaseModel):
    items: list[IncidentResponse]
    total: int = Field(..., description="Total de registros existentes según los filtros")
    page: int = Field(..., description="Página actual consultada")
    page_size: int = Field(..., description="Cantidad de registros por página")
    total_pages: int = Field(..., description="Total de páginas calculadas")
    has_next: bool = Field(..., description="Indica si existe una página posterior")
    has_prev: bool = Field(..., description="Indica si existe una página anterior")
