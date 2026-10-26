"""
Módulo de compatibilidad para modelos SQLAlchemy 2.0.
Re-exporta las clases canónicas desde el paquete app.models.
"""
from app.models.base import Base
from app.models.user import User
from app.models.license import License
from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.maintenance import Maintenance
from app.models.event import Event
from app.models.device import Device
from app.models.site import Site

__all__ = [
    "Base",
    "User",
    "License",
    "AuditLog",
    "Incident",
    "Maintenance",
    "Event",
    "Device",
    "Site",
]
