import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(150), nullable=True)
    document_id = Column(String(50), nullable=True)
    assigned_site = Column(String(100), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="Operario", nullable=False)  # Admin, Supervisor, Operario, Responsable
    is_active = Column(Boolean, default=True, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    temp_expires_at = Column(DateTime, nullable=True)
    badge_number = Column(String(30), unique=True, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relaciones
    created_incidents = relationship("Incident", back_populates="creator", foreign_keys="Incident.created_by_id")
    assigned_incidents = relationship("Incident", back_populates="assignee", foreign_keys="Incident.assigned_to_id")
    created_maintenances = relationship("Maintenance", back_populates="creator", foreign_keys="Maintenance.created_by_id")
    events = relationship("Event", back_populates="user")

    def __repr__(self):
        return f"<User username={self.username} role={self.role}>"


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)                        # Ej. Cámara PTZ Domo 01, NVR Principal 32CH
    device_type = Column(String(50), nullable=False)                  # Cámara PTZ, Cámara Domo, Cámara Bala, NVR, UPS, Switch
    brand = Column(String(50), nullable=True)                         # Hikvision, Dahua, Cisco, APC, etc.
    model = Column(String(50), nullable=True)
    serial_number = Column(String(100), nullable=True, index=True)
    ip_address = Column(String(50), nullable=True)
    mac_address = Column(String(50), nullable=True)
    sede = Column(String(100), nullable=False)                        # San Agustín, Huila (Sede Principal), Sede 2, etc.
    location_detail = Column(String(150), nullable=True)              # Entrada Principal, Cuarto de Servidores, etc.
    status = Column(String(20), default="Operativo", nullable=False)  # Operativo, Alerta Menor, En Falla, Mantenimiento, Inactivo
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relaciones
    incidents = relationship("Incident", back_populates="device")
    maintenances = relationship("Maintenance", back_populates="device")

    def __repr__(self):
        return f"<Device id={self.id} name={self.name} type={self.device_type} status={self.status}>"


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(20), default="Abierto", nullable=False)  # Abierto, En Proceso, Resuelto, Cerrado
    priority = Column(String(20), default="Media", nullable=False)   # Baja, Media, Alta, Crítica
    sede = Column(String(100), nullable=True)
    image_path = Column(String(255), nullable=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    ticket_number = Column(String(50), nullable=True, index=True)
    fault_type = Column(String(50), default="Falla Menor", nullable=True)  # Falla Crítica, Falla Menor, Inactivo, Cambio
    location_detail = Column(String(150), nullable=True)                    # Estación de Policía, Carabineros, etc.
    root_cause = Column(Text, nullable=True)
    solution = Column(Text, nullable=True)
    closing_image_path = Column(String(255), nullable=True)
    closed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    attended_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    # Relaciones
    creator = relationship("User", foreign_keys=[created_by_id], back_populates="created_incidents")
    assignee = relationship("User", foreign_keys=[assigned_to_id], back_populates="assigned_incidents")
    closed_by = relationship("User", foreign_keys=[closed_by_id])
    device = relationship("Device", back_populates="incidents")
    maintenances = relationship("Maintenance", back_populates="incident")
    events = relationship("Event", back_populates="incident")

    @property
    def ticket_code(self):
        if self.ticket_number:
            return self.ticket_number
        year = self.created_at.year if self.created_at else datetime.datetime.utcnow().year
        return f"TKT-{year}-{self.id:04d}"

    @property
    def sla_target_hours(self):
        mapping = {
            "Falla Crítica": 4,
            "Inactivo": 12,
            "Falla Menor": 24,
            "Cambio": 48
        }
        return mapping.get(self.fault_type, 24)

    @property
    def elapsed_text(self):
        now = datetime.datetime.utcnow()
        ref_time = self.closed_at if (self.status == "Cerrado" and self.closed_at) else now
        start_time = self.created_at or now
        delta = ref_time - start_time
        total_seconds = max(0, int(delta.total_seconds()))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60

        if self.status == "Cerrado":
            if hours > 24:
                days = hours // 24
                rem_hours = hours % 24
                return f"Cerrado en {days}d {rem_hours}h"
            elif hours > 0:
                return f"Cerrado en {hours}h {minutes}m"
            else:
                return f"Cerrado en {minutes}m"
        else:
            if hours > 24:
                days = hours // 24
                rem_hours = hours % 24
                return f"Hace {days}d {rem_hours}h ({hours}h transcurridas)"
            elif hours > 0:
                return f"Hace {hours}h {minutes}m"
            else:
                return f"Hace {minutes}m"

    @property
    def sla_info(self):
        target_h = self.sla_target_hours
        now = datetime.datetime.utcnow()
        start_time = self.created_at or now

        if self.status == "Cerrado":
            end_time = self.closed_at or self.updated_at or now
            elapsed_h = (end_time - start_time).total_seconds() / 3600.0
            if elapsed_h <= target_h:
                return {
                    "status": "closed_on_time",
                    "badge_bg": "bg-emerald-100",
                    "badge_text": "text-emerald-800",
                    "badge_border": "border-emerald-300",
                    "dot_color": "bg-emerald-500",
                    "label": "Cumplido a Tiempo",
                    "detail": f"Resuelto en {elapsed_h:.1f}h (Meta: {target_h}h)"
                }
            else:
                exceeded = elapsed_h - target_h
                return {
                    "status": "closed_late",
                    "badge_bg": "bg-slate-100",
                    "badge_text": "text-slate-700",
                    "badge_border": "border-slate-300",
                    "dot_color": "bg-slate-500",
                    "label": "Cerrado Fuera de Meta",
                    "detail": f"+{exceeded:.1f}h sobre SLA"
                }

        elapsed_h = (now - start_time).total_seconds() / 3600.0
        remaining_h = target_h - elapsed_h

        if elapsed_h >= target_h:
            overdue_h = elapsed_h - target_h
            return {
                "status": "expired",
                "badge_bg": "bg-rose-100",
                "badge_text": "text-rose-800",
                "badge_border": "border-rose-300 animate-pulse",
                "dot_color": "bg-rose-600 animate-ping",
                "label": "Plazo Vencido (Alerta SLA)",
                "detail": f"Vencido por {int(overdue_h)}h {int((overdue_h%1)*60)}m"
            }
        elif elapsed_h >= target_h * 0.70:
            return {
                "status": "warning",
                "badge_bg": "bg-amber-100",
                "badge_text": "text-amber-800",
                "badge_border": "border-amber-300",
                "dot_color": "bg-amber-500",
                "label": "Riesgo Inminente",
                "detail": f"Restan {int(remaining_h)}h {int((remaining_h%1)*60)}m"
            }
        else:
            return {
                "status": "optimal",
                "badge_bg": "bg-sky-50",
                "badge_text": "text-sky-700",
                "badge_border": "border-sky-200",
                "dot_color": "bg-sky-500",
                "label": "En Tiempo Óptimo",
                "detail": f"Restan {int(remaining_h)}h {int((remaining_h%1)*60)}m"
            }

    def __repr__(self):
        return f"<Incident id={self.id} ticket={self.ticket_number} title={self.title} status={self.status} priority={self.priority}>"


class Maintenance(Base):
    __tablename__ = "maintenances"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(20), nullable=False)                         # Preventivo, Correctivo
    title = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    scheduled_date = Column(DateTime, nullable=False)
    completed_date = Column(DateTime, nullable=True)
    status = Column(String(20), default="Programado", nullable=False) # Programado, En Ejecución, Completado, Cancelado
    sede = Column(String(100), nullable=True)
    image_path = Column(String(255), nullable=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    protocol_code = Column(String(50), nullable=True, index=True)
    maintenance_type = Column(String(50), default="Preventivo Mensual", nullable=True)  # Inspección Rutinaria, Preventivo Mensual, Preventivo Trimestral, Preventivo Semestral, Preventivo Anual Integral
    location_detail = Column(String(150), nullable=True)                               # Estación de Policía, Carabineros, Cam 1 "Terminal", etc.
    priority = Column(String(20), default="Media", nullable=False)
    checklist_results = Column(Text, nullable=True)                                   # Checklist de tareas preventivas en JSON o texto
    technical_findings = Column(Text, nullable=True)                                  # Diagnóstico / Hallazgos previos
    actions_taken = Column(Text, nullable=True)                                       # Actividades ejecutadas
    recommendations = Column(Text, nullable=True)                                      # Recomendaciones proactivas
    execution_date = Column(DateTime, nullable=True)
    completed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    completion_photo = Column(String(255), nullable=True)

    # Flujo de Validación Técnica
    validator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    validated_at = Column(DateTime, nullable=True)
    validation_status = Column(String(50), nullable=True)  # Pendiente, Conforme, Rechazado
    validation_notes = Column(Text, nullable=True)

    # Relaciones
    incident = relationship("Incident", back_populates="maintenances")
    creator = relationship("User", foreign_keys=[created_by_id], back_populates="created_maintenances")
    completed_by = relationship("User", foreign_keys=[completed_by_id])
    validator = relationship("User", foreign_keys=[validator_id])
    device = relationship("Device", back_populates="maintenances")
    events = relationship("Event", back_populates="maintenance")

    @property
    def code(self):
        if self.protocol_code:
            return self.protocol_code
        year = self.created_at.year if self.created_at else datetime.datetime.utcnow().year
        return f"MP-{year}-{self.id:04d}"

    @property
    def cycle_label(self):
        return self.maintenance_type or self.type or "Preventivo Mensual"

    @property
    def proactive_status(self):
        now = datetime.datetime.utcnow()

        if self.status == "Conforme / Validado":
            val_name = self.validator.full_name or self.validator.username if self.validator else "Validador"
            return {
                "status": "validated",
                "label": "Conforme / Validado",
                "badge_bg": "bg-emerald-100",
                "badge_text": "text-emerald-800",
                "badge_border": "border-emerald-300",
                "dot": "bg-emerald-600",
                "detail": f"Conformidad técnica certificada por {val_name}"
            }

        if self.status == "Pendiente de Validación":
            return {
                "status": "pending_validation",
                "label": "Pendiente de Validación",
                "badge_bg": "bg-purple-100",
                "badge_text": "text-purple-800",
                "badge_border": "border-purple-300 animate-pulse",
                "dot": "bg-purple-600 animate-ping",
                "detail": "Esperando revisión y dictamen técnico del Validador"
            }

        if self.status == "Rechazado":
            return {
                "status": "rejected",
                "label": "Rechazado con Observaciones",
                "badge_bg": "bg-rose-100",
                "badge_text": "text-rose-800",
                "badge_border": "border-rose-300",
                "dot": "bg-rose-600",
                "detail": "Requiere subsanación técnica según observaciones del Validador"
            }

        if self.status == "Completado":
            ref_completed = self.completed_date or now
            if self.scheduled_date and ref_completed <= self.scheduled_date + datetime.timedelta(hours=12):
                return {
                    "status": "completed_on_time",
                    "label": "Cumplido a Tiempo",
                    "badge_bg": "bg-emerald-100",
                    "badge_text": "text-emerald-800",
                    "badge_border": "border-emerald-300",
                    "dot": "bg-emerald-500",
                    "detail": "Ejecutado según cronograma técnico"
                }
            else:
                return {
                    "status": "completed_delayed",
                    "label": "Completado Extemporáneo",
                    "badge_bg": "bg-slate-100",
                    "badge_text": "text-slate-700",
                    "badge_border": "border-slate-300",
                    "dot": "bg-slate-400",
                    "detail": "Finalizado con posterioridad a la fecha meta"
                }

        if self.status == "En Ejecución":
            return {
                "status": "in_progress",
                "label": "En Ejecución Técnica",
                "badge_bg": "bg-blue-100",
                "badge_text": "text-blue-800",
                "badge_border": "border-blue-300 animate-pulse",
                "dot": "bg-blue-600 animate-ping",
                "detail": "Técnico trabajando en sitio"
            }

        # Estado Programado
        if not self.scheduled_date:
            return {
                "status": "on_schedule",
                "label": "Programado",
                "badge_bg": "bg-sky-50",
                "badge_text": "text-sky-700",
                "badge_border": "border-sky-200",
                "dot": "bg-sky-500",
                "detail": "Pendiente de ejecución"
            }

        diff = self.scheduled_date - now
        hours_left = diff.total_seconds() / 3600

        if hours_left < 0:
            return {
                "status": "overdue",
                "label": "Atrasado / Plazo Vencido",
                "badge_bg": "bg-rose-100",
                "badge_text": "text-rose-800",
                "badge_border": "border-rose-300 animate-pulse",
                "dot": "bg-rose-600",
                "detail": f"Vencido hace {abs(int(hours_left // 24))}d {abs(int(hours_left % 24))}h"
            }
        elif hours_left <= 48:
            return {
                "status": "due_soon",
                "label": "Próximo a Vencer (<= 48h)",
                "badge_bg": "bg-amber-100",
                "badge_text": "text-amber-800",
                "badge_border": "border-amber-300",
                "dot": "bg-amber-500",
                "detail": f"Vence en {int(hours_left)} horas"
            }
        else:
            days_left = int(hours_left // 24)
            return {
                "status": "on_schedule",
                "label": "En Cronograma Óptimo",
                "badge_bg": "bg-emerald-50",
                "badge_text": "text-emerald-700",
                "badge_border": "border-emerald-200",
                "dot": "bg-emerald-400",
                "detail": f"Faltan {days_left} días"
            }

    def __repr__(self):
        return f"<Maintenance id={self.id} code={self.code} type={self.type} status={self.status}>"


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)
    maintenance_id = Column(Integer, ForeignKey("maintenances.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(String(50), nullable=False)                 # CREATION, STATUS_CHANGE, COMMENT, ASSIGNMENT, etc.
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relaciones
    user = relationship("User", back_populates="events")
    incident = relationship("Incident", back_populates="events")
    maintenance = relationship("Maintenance", back_populates="events")

    def __repr__(self):
        return f"<Event id={self.id} event_type={self.event_type} user_id={self.user_id}>"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String(50), nullable=True, index=True)
    action = Column(String(50), nullable=False, index=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<AuditLog action={self.action} username={self.username} timestamp={self.timestamp}>"


class License(Base):
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True, index=True)
    license_key = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    activated_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<License id={self.id} is_active={self.is_active}>"


__all__ = ["Base", "User", "Device", "Incident", "Maintenance", "Event", "AuditLog", "License"]
