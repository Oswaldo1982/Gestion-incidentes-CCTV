from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

class MaintenanceBase(BaseModel):
    type: Literal["Preventivo", "Correctivo"]
    title: str = Field(..., min_length=3, max_length=100)
    description: str = Field(..., min_length=5)
    scheduled_date: datetime
    incident_id: Optional[int] = None

class MaintenanceCreate(MaintenanceBase):
    pass

class MaintenanceUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = Field(None, min_length=5)
    scheduled_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    status: Optional[Literal["Programado", "En Ejecución", "Completado", "Cancelado"]] = None
    incident_id: Optional[int] = None

class MaintenanceResponse(BaseModel):
    id: int
    type: str
    title: str
    description: str
    scheduled_date: datetime
    completed_date: Optional[datetime] = None
    status: str
    incident_id: Optional[int] = None
    created_by_id: int
    created_at: datetime

    class Config:
        from_attributes = True
