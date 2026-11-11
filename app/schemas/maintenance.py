from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

class MaintenanceBase(BaseModel):
    type: Literal["Preventivo"] = "Preventivo"
    title: Optional[str] = Field(None, max_length=150)
    description: str = Field(..., min_length=5)
    scheduled_date: datetime
    sede: Optional[str] = None
    location_detail: Optional[str] = None
    device_id: Optional[int] = None
    incident_id: Optional[int] = None
    protocol_code: Optional[str] = None
    maintenance_type: Optional[str] = "Preventivo Mensual"
    priority: Optional[str] = "Media"

class MaintenanceCreate(MaintenanceBase):
    pass

class MaintenanceValidate(BaseModel):
    action: Literal["approve", "reject"]
    validation_notes: Optional[str] = None

class MaintenanceUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=150)
    description: Optional[str] = None
    scheduled_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    status: Optional[Literal["Programado", "En Ejecución", "Pendiente de Validación", "Validado / Conforme", "Conforme / Validado", "Rechazado", "Completado", "Cancelado"]] = None
    sede: Optional[str] = None
    location_detail: Optional[str] = None
    device_id: Optional[int] = None
    incident_id: Optional[int] = None
    priority: Optional[str] = None
    maintenance_type: Optional[str] = None
    checklist_results: Optional[str] = None
    technical_findings: Optional[str] = None
    actions_taken: Optional[str] = None
    recommendations: Optional[str] = None
    execution_date: Optional[datetime] = None
    completed_by_id: Optional[int] = None
    completion_photo: Optional[str] = None
    validator_id: Optional[int] = None
    validated_at: Optional[datetime] = None
    validation_status: Optional[str] = None
    validation_notes: Optional[str] = None

class MaintenanceResponse(BaseModel):
    id: int
    type: str
    title: str
    description: str
    scheduled_date: datetime
    completed_date: Optional[datetime] = None
    status: str
    sede: Optional[str] = None
    location_detail: Optional[str] = None
    device_id: Optional[int] = None
    incident_id: Optional[int] = None
    protocol_code: Optional[str] = None
    maintenance_type: Optional[str] = None
    priority: Optional[str] = "Media"
    checklist_results: Optional[str] = None
    technical_findings: Optional[str] = None
    actions_taken: Optional[str] = None
    recommendations: Optional[str] = None
    execution_date: Optional[datetime] = None
    completed_by_id: Optional[int] = None
    completion_photo: Optional[str] = None
    image_path: Optional[str] = None
    validator_id: Optional[int] = None
    validated_at: Optional[datetime] = None
    validation_status: Optional[str] = None
    validation_notes: Optional[str] = None
    created_by_id: int
    created_at: datetime

    class Config:
        from_attributes = True
