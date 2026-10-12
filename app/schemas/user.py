from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field, model_validator

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None
    document_id: Optional[str] = None
    assigned_site: Optional[str] = None
    role: Literal["Admin", "Validador", "Supervisor", "Empresa de Mantenimiento", "Operario", "Responsable"] = "Empresa de Mantenimiento"
    badge_number: Optional[str] = None
    is_active: bool = True
    must_change_password: bool = False
    temp_expires_at: Optional[datetime] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

    @model_validator(mode="after")
    def validate_validador_badge(self):
        if self.role == "Validador":
            if not self.badge_number or not self.badge_number.strip():
                raise ValueError("El número de placa policial es obligatorio para el rol Validador.")
            clean_badge = self.badge_number.strip()
            if not clean_badge.isdigit():
                raise ValueError("El número de placa policial debe contener únicamente dígitos numéricos.")
        return self

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    document_id: Optional[str] = None
    assigned_site: Optional[str] = None
    role: Optional[Literal["Admin", "Validador", "Supervisor", "Empresa de Mantenimiento", "Operario", "Responsable"]] = None
    badge_number: Optional[str] = None
    is_active: Optional[bool] = None
    must_change_password: Optional[bool] = None
    temp_expires_at: Optional[datetime] = None
    password: Optional[str] = Field(None, min_length=6)

class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    document_id: Optional[str] = None
    assigned_site: Optional[str] = None
    role: str
    badge_number: Optional[str] = None
    is_active: bool
    must_change_password: bool = False
    temp_expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
