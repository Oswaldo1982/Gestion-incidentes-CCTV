from typing import Optional
from pydantic import BaseModel

class LicenseActivate(BaseModel):
    license_key: str

class LicenseStatusResponse(BaseModel):
    is_active: bool
    client: Optional[str] = None
    expires: Optional[str] = None
    max_users: Optional[int] = None
    active_users: int
    message: str
