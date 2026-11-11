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

class Maintenance(Base):
    __tablename__ = "maintenances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)                         # Preventivo
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_date: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    completed_date: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Programado", nullable=False) # Programado, En Ejecución, Completado, Cancelado
    sede: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    device_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("devices.id"), nullable=True)
    
    incident_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("incidents.id"), nullable=True)
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=get_local_now, nullable=False)

    protocol_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    maintenance_type: Mapped[Optional[str]] = mapped_column(String(50), default="Preventivo Mensual", nullable=True)  # Inspección Rutinaria, Preventivo Mensual, Preventivo Trimestral, Preventivo Semestral, Preventivo Anual Integral
    location_detail: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)                               # Estación de Policía, Carabineros, Cam 1 "Terminal", etc.
    priority: Mapped[str] = mapped_column(String(20), default="Media", nullable=False)
    checklist_results: Mapped[Optional[str]] = mapped_column(Text, nullable=True)                                   # Checklist de tareas preventivas
    technical_findings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)                                  # Diagnóstico / Hallazgos previos
    actions_taken: Mapped[Optional[str]] = mapped_column(Text, nullable=True)                                       # Actividades ejecutadas
    recommendations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)                                      # Recomendaciones preventivas
    execution_date: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    completed_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    completion_photo: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Flujo de Validación Técnica
    validator_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    validated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    validation_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Pendiente, Conforme, Rechazado
    validation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_photo: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    timer_reset_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

    # Confiabilidad, Análisis de Causa Raíz (RCA) y Taxonomía de Activos (ISO 14224 / CMMS)
    rca_cause_factor: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    rca_failure_mechanism: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    operating_condition: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    asset_component: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    incident = relationship("Incident")
    creator = relationship("User", foreign_keys=[created_by_id])
    completed_by = relationship("User", foreign_keys=[completed_by_id])
    validator = relationship("User", foreign_keys=[validator_id])
    device = relationship("Device", back_populates="maintenances")

    @property
    def code(self):
        if self.protocol_code:
            return self.protocol_code
        prefix = "CCTV"
        if self.sede:
            s = self.sede.lower()
            if "agustin" in s or "agustín" in s:
                prefix = "SAN"
            elif "jose" in s or "josé" in s or "guaviare" in s:
                prefix = "SJG"
            elif "retorno" in s:
                prefix = "RET"
            elif "calamar" in s:
                prefix = "CAL"
        return f"MP-{prefix}-{self.id:04d}"

    @property
    def is_validated(self) -> bool:
        return (
            self.validation_status in ["Conforme", "Validado / Conforme", "Conforme / Validado"]
            or "Validado" in (self.status or "")
            or self.status in ["Validado / Conforme", "Conforme / Validado"]
        )

    @property
    def is_pending_validation(self) -> bool:
        return (
            self.status == "Pendiente de Validación"
            or (self.validation_status == "Pendiente" and not self.is_validated)
        )

    @property
    def is_rejected(self) -> bool:
        return self.status == "Rechazado" or self.validation_status == "Rechazado"

    @property
    def is_in_progress(self) -> bool:
        return self.status == "En Ejecución"

    @property
    def is_scheduled(self) -> bool:
        return self.status == "Programado"

    @property
    def cycle_label(self):
        return self.maintenance_type or self.type or "Preventivo Mensual"

    @property
    def checklist_dict(self):
        import json
        if not self.checklist_results:
            return {}
        try:
            return json.loads(self.checklist_results)
        except Exception:
            return {}

    @property
    def proactive_status(self):
        now = get_local_now()

        if self.status in ["Conforme / Validado", "Validado / Conforme"]:
            val_name = _clean_str(self.validator.full_name or self.validator.username) if self.validator else "Validador"
            raw_badge = _clean_str(self.validator.badge_number) if self.validator and self.validator.badge_number else ""
            val_badge = f" (Placa #{raw_badge})" if raw_badge else ""
            return {
                "status": "validated",
                "label": "Validado / Conforme",
                "badge_bg": "bg-emerald-100",
                "badge_text": "text-emerald-800",
                "badge_border": "border-emerald-300",
                "dot": "bg-emerald-600",
                "detail": f"Conformidad técnica certificada por {val_name}{val_badge}"
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

        delta = self.scheduled_date - now
        total_seconds = delta.total_seconds()

        if total_seconds < 0:
            overdue_h = abs(total_seconds) / 3600.0
            return {
                "status": "overdue",
                "label": "Atrasado (Alerta de Cronograma)",
                "badge_bg": "bg-rose-100",
                "badge_text": "text-rose-800",
                "badge_border": "border-rose-300 animate-pulse",
                "dot": "bg-rose-600 animate-ping",
                "detail": f"Vencido por {int(overdue_h)}h {int((overdue_h%1)*60)}m"
            }
        elif total_seconds <= 48 * 3600:
            remaining_h = total_seconds / 3600.0
            return {
                "status": "impending",
                "label": "Próximo a Vencer (<= 48h)",
                "badge_bg": "bg-amber-100",
                "badge_text": "text-amber-800",
                "badge_border": "border-amber-300",
                "dot": "bg-amber-500",
                "detail": f"Restan {int(remaining_h)}h {int((remaining_h%1)*60)}m"
            }
        else:
            days = int(total_seconds // 86400)
            return {
                "status": "on_schedule",
                "label": "En Cronograma Óptimo",
                "badge_bg": "bg-sky-50",
                "badge_text": "text-sky-700",
                "badge_border": "border-sky-200",
                "dot": "bg-sky-500",
                "detail": f"Programado en {days} días"
            }

    @property
    def elapsed_text(self) -> str:
        now = get_local_now()
        start_time = self.timer_reset_at or self.execution_date or self.created_at or now
        ref_time = self.validated_at or self.completed_date or now
        delta = ref_time - start_time
        total_seconds = max(0, int(delta.total_seconds()))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60

        if self.is_validated:
            if hours > 24:
                return f"Validado en {hours // 24}d {hours % 24}h"
            elif hours > 0:
                return f"Validado en {hours}h {minutes}m"
            else:
                return f"Validado en {minutes}m"
        elif self.status == "Pendiente de Validación":
            tech_time = self.completed_date or now
            tech_delta = tech_time - start_time
            tech_sec = max(0, int(tech_delta.total_seconds()))
            t_h = tech_sec // 3600
            t_m = (tech_sec % 3600) // 60
            if t_h > 24:
                return f"Finalizado en {t_h // 24}d {t_h % 24}h (Por Validar)"
            elif t_h > 0:
                return f"Finalizado en {t_h}h {t_m}m (Por Validar)"
            else:
                return f"Finalizado en {t_m}m (Por Validar)"
        elif self.completed_date:
            if hours > 24:
                return f"Ejecutado en {hours // 24}d {hours % 24}h"
            elif hours > 0:
                return f"Ejecutado en {hours}h {minutes}m"
            else:
                return f"Ejecutado en {minutes}m"
        else:
            if hours > 24:
                return f"En curso ({hours // 24}d {hours % 24}h)"
            elif hours > 0:
                return f"En curso ({hours}h {minutes}m)"
            else:
                return f"En curso ({minutes}m)"

    def to_trace_dict(self) -> dict:
        creator_name = _clean_str(self.creator.full_name or self.creator.username) if self.creator else 'Sistema'
        closed_by_name = _clean_str(self.completed_by.full_name or self.completed_by.username) if self.completed_by else ('Técnico de Mantenimiento' if self.completed_date else 'Pendiente de Cierre')
        val_user = self.validator
        if self.is_validated or self.is_rejected:
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
        val_notes = (self.validation_notes or '') if (self.is_validated or self.is_rejected) else ''
        p_stat = self.proactive_status

        creator_doc = (self.creator.document_id or '') if self.creator else ''
        creator_sig = (self.creator.signature_path or '') if self.creator else ''
        completed_by_doc = (self.completed_by.document_id or '') if self.completed_by else ''
        completed_by_sig = (self.completed_by.signature_path or '') if self.completed_by else ''

        if self.actions_taken:
            actions_desc = self.actions_taken
        elif self.status in ['Programado']:
            actions_desc = 'Pendiente de inicio de labores en campo.'
        elif self.status in ['En Ejecución', 'En Ejecucion']:
            actions_desc = 'Labores técnicas actualmente en ejecución en sitio.'
        else:
            actions_desc = 'Mantenimiento integral ejecutado.'

        if self.recommendations:
            recom_desc = self.recommendations
        elif self.status in ['Programado', 'En Ejecución']:
            recom_desc = 'Se emitirán recomendaciones preventivas una vez finalizada la intervención técnica.'
        else:
            recom_desc = 'Continuar con el ciclo regular de mantenimiento preventivo.'

        return {
            "id": self.id,
            "type": "maintenance",
            "code": self.code,
            "ticket": self.code,
            "title": self.title or '',
            "description": self.description or '',
            "maintenance_type": self.maintenance_type or 'Preventivo Mensual',
            "cycle": self.maintenance_type or self.type or 'Preventivo Mensual',
            "fault_type": self.type or 'Preventivo',
            "priority": self.priority or 'Media',
            "location": self.location_detail or (self.sede or 'Estación de Policía'),
            "device": self.device.name if self.device else 'General / Punto de Monitoreo',
            "device_ip": self.device.ip_address if self.device else '',
            "created_by": creator_name,
            "created_at": self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else '',
            "scheduled_date": self.scheduled_date.strftime('%d/%m/%Y %H:%M') if self.scheduled_date else '',
            "execution_date": self.execution_date.strftime('%d/%m/%Y %H:%M') if self.execution_date else 'N/A',
            "attended_at": self.execution_date.strftime('%d/%m/%Y %H:%M') if self.execution_date else 'N/A',
            "completed_by": closed_by_name,
            "closed_by": closed_by_name,
            "completed_date": self.completed_date.strftime('%d/%m/%Y %H:%M') if self.completed_date else 'Pendiente',
            "closed_at": self.completed_date.strftime('%d/%m/%Y %H:%M') if self.completed_date else 'Pendiente',
            "elapsed": self.elapsed_text,
            "status": self.status or 'Programado',
            "validation_status": self.validation_status or '',
            "is_technically_closed": bool(self.completed_date is not None or self.status in ['Pendiente de Validación', 'Completado', 'Rechazado']),
            "is_validated": bool(self.is_validated),
            "is_pending_validation": bool(self.is_pending_validation),
            "is_rejected": bool(self.is_rejected),
            "is_resolved": bool(self.is_validated or self.status == 'Completado'),
            "is_overtime": False,
            "created_by_doc": creator_doc,
            "created_by_sig": creator_sig,
            "completed_by_doc": completed_by_doc,
            "completed_by_sig": completed_by_sig,
            "validator": validator_name,
            "validator_badge": validator_badge,
            "validator_document": validator_doc,
            "validator_role": validator_role,
            "validator_sig": validator_sig,
            "validator_rank": 'Oficial Validador de Seguridad y Convivencia Policial (CCTV)' if (self.is_validated or self.is_rejected) else '',
            "validator_unit": 'Policía Nacional de Colombia - Estación de Policía - Centro de Monitoreo CCTV' if (self.is_validated or self.is_rejected) else '',
            "validated_at": self.validated_at.strftime('%d/%m/%Y %H:%M') if ((self.is_validated or self.is_rejected) and self.validated_at) else '',
            "validation_notes": val_notes,
            "proactive_label": p_stat.get("label", ""),
            "proactive_detail": p_stat.get("detail", ""),
            "resolution_label": p_stat.get("label", ""),
            "root_cause": self.technical_findings or ('Pendiente de inspección' if self.status in ['Programado', 'En Ejecución'] else 'Sin observaciones previas'),
            "solution": actions_desc,
            "findings": self.technical_findings or ('Pendiente de inspección' if self.status in ['Programado', 'En Ejecución'] else 'Sin observaciones previas'),
            "actions": actions_desc,
            "recommendations": recom_desc,
            "checklist_raw": self.checklist_results or '{}',
            "initial_img": self.image_path or '',
            "closing_img": self.completion_photo or '',
            "rejection_img": self.rejection_photo or ''
        }

    def __repr__(self):
        return f"<Maintenance id={self.id} code={self.protocol_code} title={self.title} status={self.status}>"
