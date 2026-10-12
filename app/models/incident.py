import datetime
from typing import Optional
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.models.base import Base

class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="Abierto", nullable=False)  # Abierto, En Proceso, Resuelto, Cerrado
    priority: Mapped[str] = mapped_column(String(20), default="Media", nullable=False)   # Baja, Media, Alta, Crítica
    sede: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    device_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("devices.id"), nullable=True)
    
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_to_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    ticket_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    fault_type: Mapped[Optional[str]] = mapped_column(String(50), default="Falla Menor", nullable=True)  # Falla Crítica, Falla Menor, Inactivo, Cambio
    location_detail: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)                    # Estación de Policía, Carabineros, Punto de Cámara 01, etc.
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)                               # Diagnóstico causa raíz
    solution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)                                 # Solución técnica aplicada
    closing_image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)                # Evidencia fotográfica de solución
    closed_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    attended_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

    # Flujo de Validación Técnica Policial
    validator_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    validated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    validation_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Pendiente, Conforme, Rechazado
    validation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_photo: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    timer_reset_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

    creator = relationship("User", foreign_keys=[created_by_id])
    assignee = relationship("User", foreign_keys=[assigned_to_id])
    closed_by = relationship("User", foreign_keys=[closed_by_id])
    validator = relationship("User", foreign_keys=[validator_id])
    device = relationship("Device", back_populates="incidents")

    @property
    def ticket_code(self):
        if self.ticket_number:
            return self.ticket_number
        year = self.created_at.year if self.created_at else datetime.datetime.utcnow().year
        return f"TKT-{year}-{self.id:04d}"

    @ticket_code.setter
    def ticket_code(self, value):
        self.ticket_number = value

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
        is_finished = self.status in ["Cerrado", "Validado / Conforme", "Conforme / Validado"]
        ref_time = self.validated_at or self.closed_at if (is_finished and (self.validated_at or self.closed_at)) else now
        start_time = self.timer_reset_at or self.created_at or now
        delta = ref_time - start_time
        total_seconds = max(0, int(delta.total_seconds()))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60

        if is_finished:
            status_label = "Validado" if ("Validado" in self.status or "Conforme" in self.status) else "Cerrado"
            if hours > 24:
                days = hours // 24
                rem_hours = hours % 24
                return f"{status_label} en {days}d {rem_hours}h"
            elif hours > 0:
                return f"{status_label} en {hours}h {minutes}m"
            else:
                return f"{status_label} en {minutes}m"
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
        start_time = self.timer_reset_at or self.created_at or now

        if self.status in ["Validado / Conforme", "Conforme / Validado"]:
            val_name = self.validator.full_name or self.validator.username if self.validator else "Validador"
            val_badge = f" (Placa #{self.validator.badge_number})" if self.validator and self.validator.badge_number else ""
            end_time = self.validated_at or self.closed_at or now
            elapsed_h = (end_time - start_time).total_seconds() / 3600.0
            return {
                "status": "validated",
                "badge_bg": "bg-emerald-100",
                "badge_text": "text-emerald-800",
                "badge_border": "border-emerald-300",
                "dot_color": "bg-emerald-500",
                "label": "Validado / Conforme",
                "detail": f"Certificado por {val_name}{val_badge} ({elapsed_h:.1f}h)"
            }

        if self.status == "Pendiente de Validación":
            return {
                "status": "pending_validation",
                "badge_bg": "bg-purple-100",
                "badge_text": "text-purple-800",
                "badge_border": "border-purple-300 animate-pulse",
                "dot_color": "bg-purple-600 animate-ping",
                "label": "Pendiente de Validación",
                "detail": "Esperando dictamen técnico de la Estación de Policía"
            }

        if self.status == "Rechazado":
            return {
                "status": "rejected",
                "badge_bg": "bg-rose-100",
                "badge_text": "text-rose-800",
                "badge_border": "border-rose-300",
                "dot_color": "bg-rose-600",
                "label": "Rechazado con Observaciones",
                "detail": "Devuelto a técnico con tiempo cero para subsanación"
            }

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

        # Abierto o En Proceso
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
        return f"<Incident id={self.id} ticket={self.ticket_number} title={self.title} status={self.status}>"

