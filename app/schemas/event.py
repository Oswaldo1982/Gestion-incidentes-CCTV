from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class EventCreate(BaseModel):
    description: str = Field(..., min_length=1)

class EventResponse(BaseModel):
    id: int
    incident_id: Optional[int] = None
    maintenance_id: Optional[int] = None
    user_id: int
    event_type: str
    description: str
    created_at: datetime

    class Config:
        from_attributes = True
