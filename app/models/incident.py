from typing import Optional

def _clean_str(s: Optional[str]) -> str:
    if not s:
        return ""
    if s.startswith("deleted_") or s.startswith("del_"):
        parts = s.split("_", 2)
        return parts[-1] if len(parts) > 2 else s
    return s

import datetime
from typing import Optional
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.models.base import Base
from app.utils.timezone import get_local_now

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
    
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=get_local_now, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=get_local_now, onupdate=get_local_now, nullable=False)

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
        year = self.created_at.year if self.created_at else get_local_now().year
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
        return mapping.get(self.fault_type or "Falla Menor", 24)

    @property
    def is_technically_closed(self) -> bool:
        """Indica si el equipo técnico completó la intervención y remitió la orden."""
        if self.status in ["Abierto", "En Proceso", "Rechazado"]:
            return False
        return self.closed_at is not None or self.status in [
            "Pendiente de Validación",
            "Pendiente de Validación Policial",
            "Validado / Conforme",
            "Conforme / Validado",
            "Cerrado",
            "Resuelto"
        ]

    @property
    def is_validated(self) -> bool:
        """Determina si el incidente ya ha recibido visto bueno y certificación formal del Validador."""
        if self.status in ["Pendiente de Validación", "Pendiente de Validación Policial", "Rechazado", "Abierto", "En Proceso"]:
            return False
        return (
            self.status in ["Validado / Conforme", "Conforme / Validado"]
            or self.validation_status == "Conforme"
            or (self.validator_id is not None and self.validated_at is not None)
        )

    @property
    def is_resolved(self) -> bool:
        """Determina si un incidente ya ha sido resuelto y cerrado formalmente (incluyendo validación)."""
        if self.status in ["Pendiente de Validación", "Pendiente de Validación Policial", "Rechazado", "Abierto", "En Proceso"]:
            return False
        return (
            self.status in ["Cerrado", "Resuelto", "Validado / Conforme", "Conforme / Validado"]
            or self.validation_status == "Conforme"
            or (self.closed_at is not None and self.validator_id is not None)
        )

    @property
    def is_overtime(self) -> bool:
        """Determina si el ticket superó la meta SLA (resuelto en extra tiempo o vencido en curso)."""
        target_h = self.sla_target_hours
        now = get_local_now()
        start_time = self.timer_reset_at or self.created_at or now
        if self.is_resolved:
            end_time = self.validated_at or self.closed_at or self.updated_at or now
        else:
            end_time = now
        elapsed_h = max(0.0, (end_time - start_time).total_seconds() / 3600.0)
        return elapsed_h > target_h

    @property
    def resolution_label(self) -> str:
        """Etiqueta oficial de resolución: 'Resuelto SLA' si fue en extra tiempo, o 'Resuelto'."""
        if not self.is_resolved:
            return ""
        return "Resuelto SLA" if self.is_overtime else "Resuelto"

    @property
    def elapsed_text(self):
        now = get_local_now()
        ref_time = self.validated_at or self.closed_at or self.updated_at if (self.is_resolved and (self.validated_at or self.closed_at or self.updated_at)) else now
        start_time = self.timer_reset_at or self.created_at or now
        delta = ref_time - start_time
        total_seconds = max(0, int(delta.total_seconds()))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60

        if self.is_resolved:
            status_label = self.resolution_label
            if hours > 24:
                days = hours // 24
                rem_hours = hours % 24
                return f"{status_label} en {days}d {rem_hours}h"
            elif hours > 0:
                return f"{status_label} en {hours}h {minutes}m"
            else:
                return f"{status_label} en {minutes}m"
        elif self.status in ["Pendiente de Validación", "Pendiente de Validación Policial"]:
            tech_time = self.closed_at or self.updated_at or now
            tech_delta = tech_time - start_time
            tech_sec = max(0, int(tech_delta.total_seconds()))
            t_h = tech_sec // 3600
            t_m = (tech_sec % 3600) // 60
            if t_h > 24:
                return f"Finalizado en {t_h//24}d {t_h%24}h (Por Validar)"
            elif t_h > 0:
                return f"Finalizado en {t_h}h {t_m}m (Por Validar)"
            else:
                return f"Finalizado en {t_m}m (Por Validar)"
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
        now = get_local_now()
        start_time = self.timer_reset_at or self.created_at or now

        # 1. Caso RESUELTO / CERRADO / VALIDADO
        if self.is_resolved:
            end_time = self.validated_at or self.closed_at or self.updated_at or now
            delta = end_time - start_time
            elapsed_h = max(0.0, delta.total_seconds() / 3600.0)
            is_late = elapsed_h > target_h

            val_name = self.validator.full_name or self.validator.username if self.validator else "Oficial Validador"
            val_badge = f" (Placa #{self.validator.badge_number})" if self.validator and self.validator.badge_number else ""

            if not is_late:
                return {
                    "status": "closed_on_time",
                    "badge_bg": "bg-emerald-100",
                    "badge_text": "text-emerald-800",
                    "badge_border": "border-emerald-300",
                    "dot_color": "bg-emerald-500",
                    "label": "Resuelto",
                    "sub_label": "Resuelto",
                    "is_resolved": True,
                    "is_overtime": False,
                    "detail": f"Cumplido en {elapsed_h:.1f}h (Meta SLA: {target_h}h)"
                }
            else:
                exceeded = elapsed_h - target_h
                return {
                    "status": "closed_late",
                    "badge_bg": "bg-emerald-50",
                    "badge_text": "text-emerald-900",
                    "badge_border": "border-emerald-400",
                    "dot_color": "bg-emerald-500",
                    "label": "Resuelto SLA",
                    "sub_label": "Resuelto SLA",
                    "is_resolved": True,
                    "is_overtime": True,
                    "detail": f"Resuelto con +{exceeded:.1f}h en tiempo extra (Meta SLA: {target_h}h)"
                }

        # 2. Pendiente de Validación Policial
        if self.status in ["Pendiente de Validación", "Pendiente de Validación Policial"]:
            return {
                "status": "pending_validation",
                "badge_bg": "bg-purple-100",
                "badge_text": "text-purple-800",
                "badge_border": "border-purple-300 animate-pulse",
                "dot_color": "bg-purple-600 animate-ping",
                "label": "Pendiente de Validación",
                "sub_label": "Por Validar",
                "is_resolved": False,
                "is_overtime": False,
                "detail": "Esperando dictamen técnico de la Estación de Policía"
            }

        # 3. Rechazado
        if self.status == "Rechazado":
            return {
                "status": "rejected",
                "badge_bg": "bg-rose-100",
                "badge_text": "text-rose-800",
                "badge_border": "border-rose-300",
                "dot_color": "bg-rose-600",
                "label": "Rechazado con Observaciones",
                "sub_label": "Rechazado",
                "is_resolved": False,
                "is_overtime": False,
                "detail": "Devuelto a técnico con tiempo cero para subsanación"
            }

        # 4. Abierto o En Proceso
        elapsed_h = max(0.0, (now - start_time).total_seconds() / 3600.0)
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
                "sub_label": "Alerta SLA",
                "is_resolved": False,
                "is_overtime": True,
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
                "sub_label": "Alerta",
                "is_resolved": False,
                "is_overtime": False,
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
                "sub_label": "Óptimo",
                "is_resolved": False,
                "is_overtime": False,
                "detail": f"Restan {int(remaining_h)}h {int((remaining_h%1)*60)}m"
            }

    def to_trace_dict(self) -> dict:
        creator_name = _clean_str(self.creator.full_name or self.creator.username) if self.creator else 'Sistema'
        creator_role = (self.creator.role or 'Usuario') if self.creator else 'Sistema'
        creator_doc = (self.creator.document_id or '') if self.creator else ''
        creator_sig = (self.creator.signature_path or '') if self.creator else ''
        closed_by_name = _clean_str(self.closed_by.full_name or self.closed_by.username) if (self.is_technically_closed and self.closed_by) else ('Técnico de Mantenimiento' if self.is_technically_closed else 'Pendiente de Cierre')
        closed_by_role = (self.closed_by.role or 'Empresa de Mantenimiento') if (self.is_technically_closed and self.closed_by) else ('Empresa de Mantenimiento' if self.is_technically_closed else '')
        closed_by_doc = (self.closed_by.document_id or '') if (self.is_technically_closed and self.closed_by) else ''
        closed_by_sig = (self.closed_by.signature_path or '') if (self.is_technically_closed and self.closed_by) else ''
        val_user = self.validator
        if self.is_validated:
            validator_name = _clean_str(val_user.full_name or val_user.username) if val_user else 'Oficial Validador Policial'
            validator_badge = _clean_str(val_user.badge_number or '1234') if val_user else '1234'
            validator_doc = (val_user.document_id or '') if val_user else ''
            validator_role = (val_user.role or 'Validador') if val_user else 'Validador'
            validator_sig = (val_user.signature_path or '') if val_user else ''
        else:
            validator_name = ''
            validator_badge = ''
            validator_doc = ''
            validator_role = ''
            validator_sig = ''
        val_notes = (self.validation_notes or '') if (self.is_validated or self.status == 'Rechazado' or self.validation_status == 'Rechazado') else ''

        dev_type = self.device.device_type if self.device else 'CCTV'
        dev_brand = f"{self.device.brand or ''} {self.device.model or ''}".strip() if self.device else ''
        dev_serial = (self.device.serial_number or '') if self.device else ''

        return {
            "id": self.id,
            "type": "incident",
            "ticket": self.ticket_code,
            "code": self.ticket_code,
            "title": self.title or '',
            "description": self.description or '',
            "fault_type": self.fault_type or 'Falla Menor',
            "priority": self.priority or 'Media',
            "location": self.location_detail or (self.sede or 'Estación de Policía'),
            "device": self.device.name if self.device else 'General',
            "device_type": dev_type,
            "device_brand": dev_brand,
            "device_serial": dev_serial,
            "device_ip": self.device.ip_address if self.device else '',
            "created_by": creator_name,
            "created_by_role": creator_role,
            "created_by_doc": creator_doc,
            "created_by_sig": creator_sig,
            "created_at": self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else '',
            "attended_at": self.attended_at.strftime('%d/%m/%Y %H:%M') if self.attended_at else 'Inmediato',
            "closed_by": closed_by_name,
            "closed_by_role": closed_by_role,
            "closed_by_doc": closed_by_doc,
            "closed_by_sig": closed_by_sig,
            "completed_by": closed_by_name,
            "closed_at": self.closed_at.strftime('%d/%m/%Y %H:%M') if (self.is_technically_closed and self.closed_at) else 'Pendiente',
            "completed_date": self.closed_at.strftime('%d/%m/%Y %H:%M') if (self.is_technically_closed and self.closed_at) else 'Pendiente',
            "elapsed": self.elapsed_text or '0h 0m',
            "root_cause": self.root_cause or 'Sin registrar',
            "findings": self.root_cause or 'Sin registrar',
            "solution": self.solution or 'Sin registrar',
            "actions": self.solution or 'Sin registrar',
            "recommendations": '',
            "status": self.status or 'Abierto',
            "validation_status": self.validation_status or '',
            "is_technically_closed": bool(self.is_technically_closed),
            "is_validated": bool(self.is_validated),
            "is_pending_validation": bool(self.status in ["Pendiente de Validación", "Pendiente de Validación Policial"]),
            "is_resolved": bool(self.is_resolved),
            "is_rejected": bool(self.status == 'Rechazado' or self.validation_status == 'Rechazado'),
            "is_overtime": bool(self.is_overtime),
            "resolution_label": self.resolution_label or '',
            "proactive_label": self.resolution_label or '',
            "validator": validator_name,
            "validator_badge": validator_badge,
            "validator_document": validator_doc,
            "validator_role": validator_role,
            "validator_sig": validator_sig,
            "validator_rank": 'Validador Policial - SIGMC' if self.is_validated else '',
            "validator_unit": 'Sistema Integral de Gestión de Mantenimiento CCTV - SIGMC' if self.is_validated else '',
            "validated_at": self.validated_at.strftime('%d/%m/%Y %H:%M') if (self.is_validated and self.validated_at) else '',
            "validation_notes": val_notes,
            "initial_img": self.image_path or '',
            "closing_img": self.closing_image_path or '',
            "rejection_img": self.rejection_photo or ''
        }

    def __repr__(self):
        return f"<Incident id={self.id} ticket={self.ticket_number} title={self.title} status={self.status}>"

