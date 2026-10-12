import datetime
from typing import Optional
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.models.base import Base

class Maintenance(Base):
    __tablename__ = "maintenances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)                         # Preventivo, Correctivo
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
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    protocol_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    maintenance_type: Mapped[Optional[str]] = mapped_column(String(50), default="Preventivo Mensual", nullable=True)  # Inspección Rutinaria, Preventivo Mensual, Preventivo Trimestral, Preventivo Semestral, Preventivo Anual Integral
    location_detail: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)                               # Estación de Policía, Carabineros, Cam 1 "Terminal", etc.
    priority: Mapped[str] = mapped_column(String(20), default="Media", nullable=False)
    checklist_results: Mapped[Optional[str]] = mapped_column(Text, nullable=True)                                   # Checklist de tareas preventivas
    technical_findings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)                                  # Diagnóstico / Hallazgos previos
    actions_taken: Mapped[Optional[str]] = mapped_column(Text, nullable=True)                                       # Actividades ejecutadas
    recommendations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)                                      # Recomendaciones proactivas
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

    incident = relationship("Incident")
    creator = relationship("User", foreign_keys=[created_by_id])
    completed_by = relationship("User", foreign_keys=[completed_by_id])
    validator = relationship("User", foreign_keys=[validator_id])
    device = relationship("Device", back_populates="maintenances")

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
        now = datetime.datetime.utcnow()

        if self.status in ["Conforme / Validado", "Validado / Conforme"]:
            val_name = self.validator.full_name or self.validator.username if self.validator else "Validador"
            val_badge = f" (Placa #{self.validator.badge_number})" if self.validator and self.validator.badge_number else ""
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

    def __repr__(self):
        return f"<Maintenance id={self.id} code={self.protocol_code} title={self.title} status={self.status}>"
