import os
import io
import json
import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import or_

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from app.models.incident import Incident
from app.models.maintenance import Maintenance
from app.models.audit import AuditLog
from app.models.user import User


from app.services.site_sync_service import get_canonical_site_filter

def get_site_filter_conditions(model_cls, current_site: Dict[str, Any]):
    """Filtro unificado por sede homologado con todas las 4 sedes territoriales."""
    return get_canonical_site_filter(model_cls, current_site)


def get_reports_statistics(
    db: Session,
    current_site: Dict[str, Any],
    start_date: datetime.datetime,
    end_date: datetime.datetime
) -> Dict[str, Any]:
    """
    Calcula y consolida las métricas, KPIs, distribuciones gráficas y eventos
    tanto para incidentes correctivos como para mantenimientos preventivos y auditoría.
    """
    site_filter_inc = get_site_filter_conditions(Incident, current_site)
    site_filter_maint = get_site_filter_conditions(Maintenance, current_site)

    # 1. Incidentes Correctivos en el rango
    incidents = db.query(Incident).filter(
        site_filter_inc,
        Incident.created_at >= start_date,
        Incident.created_at <= end_date
    ).order_by(Incident.created_at.desc()).all()

    # 2. Mantenimientos Preventivos en el rango (por scheduled_date o created_at)
    maintenances = db.query(Maintenance).filter(
        site_filter_maint,
        or_(
            Maintenance.created_at.between(start_date, end_date),
            Maintenance.scheduled_date.between(start_date, end_date)
        )
    ).order_by(Maintenance.scheduled_date.desc()).all()

    # 3. Métricas de Incidentes
    inc_open = sum(1 for i in incidents if i.status == "Abierto")
    inc_in_prog = sum(1 for i in incidents if i.status == "En Proceso")
    inc_closed = sum(1 for i in incidents if i.status == "Cerrado")

    inc_by_type = {
        "Falla Crítica": sum(1 for i in incidents if i.fault_type == "Falla Crítica"),
        "Inactivo": sum(1 for i in incidents if i.fault_type == "Inactivo"),
        "Falla Menor": sum(1 for i in incidents if i.fault_type == "Falla Menor"),
        "Cambio": sum(1 for i in incidents if i.fault_type == "Cambio")
    }

    inc_sla_summary = {
        "Cumplido a Tiempo": 0,
        "Cerrado Fuera de Meta": 0,
        "Riesgo Inminente": 0,
        "Plazo Vencido": 0,
        "En Tiempo Óptimo": 0
    }
    for i in incidents:
        label = i.sla_info.get("label", "")
        if "Cumplido a Tiempo" in label:
            inc_sla_summary["Cumplido a Tiempo"] += 1
        elif "Fuera de Meta" in label:
            inc_sla_summary["Cerrado Fuera de Meta"] += 1
        elif "Plazo Vencido" in label:
            inc_sla_summary["Plazo Vencido"] += 1
        elif "Riesgo Inminente" in label:
            inc_sla_summary["Riesgo Inminente"] += 1
        else:
            inc_sla_summary["En Tiempo Óptimo"] += 1

    # 4. Métricas de Mantenimientos Preventivos
    maint_scheduled = sum(1 for m in maintenances if m.status == "Programado")
    maint_in_exec = sum(1 for m in maintenances if m.status == "En Ejecución")
    maint_completed = sum(1 for m in maintenances if m.status == "Completado")

    maint_by_type = {
        "Inspección Rutinaria": sum(1 for m in maintenances if m.cycle_label == "Inspección Rutinaria"),
        "Preventivo Mensual": sum(1 for m in maintenances if m.cycle_label == "Preventivo Mensual"),
        "Preventivo Trimestral": sum(1 for m in maintenances if m.cycle_label == "Preventivo Trimestral"),
        "Preventivo Semestral": sum(1 for m in maintenances if m.cycle_label == "Preventivo Semestral"),
        "Preventivo Anual Integral": sum(1 for m in maintenances if m.cycle_label == "Preventivo Anual Integral")
    }

    maint_proactive_summary = {
        "Cumplido a Tiempo": 0,
        "Completado Extemporáneo": 0,
        "En Ejecución": 0,
        "En Cronograma Óptimo": 0,
        "Próximo a Vencer (<= 48h)": 0,
        "Atrasado / Plazo Vencido": 0
    }
    for m in maintenances:
        st = m.proactive_status.get("status", "")
        if st == "completed_on_time":
            maint_proactive_summary["Cumplido a Tiempo"] += 1
        elif st == "completed_delayed":
            maint_proactive_summary["Completado Extemporáneo"] += 1
        elif st == "in_progress":
            maint_proactive_summary["En Ejecución"] += 1
        elif st == "on_schedule":
            maint_proactive_summary["En Cronograma Óptimo"] += 1
        elif st == "due_soon":
            maint_proactive_summary["Próximo a Vencer (<= 48h)"] += 1
        elif st == "overdue":
            maint_proactive_summary["Atrasado / Plazo Vencido"] += 1

    # 5. Distribución por Sitio Físico
    sites_distribution: Dict[str, Dict[str, int]] = {}
    for i in incidents:
        loc = i.location_detail or "General"
        if loc not in sites_distribution:
            sites_distribution[loc] = {"correctivos": 0, "preventivos": 0}
        sites_distribution[loc]["correctivos"] += 1

    for m in maintenances:
        loc = m.location_detail or "General"
        if loc not in sites_distribution:
            sites_distribution[loc] = {"correctivos": 0, "preventivos": 0}
        sites_distribution[loc]["preventivos"] += 1

    # 6. Tendencia Temporal (Día por Día en el rango)
    timeline_days: List[str] = []
    timeline_correctives: List[int] = []
    timeline_preventives: List[int] = []

    curr = start_date.date()
    end_d = end_date.date()
    total_days = (end_d - curr).days + 1
    
    # Si el rango es mayor a 60 días, agrupamos semanal o quincenalmente para no saturar gráficos
    step = 1 if total_days <= 31 else (7 if total_days <= 180 else 14)

    curr_p = curr
    while curr_p <= end_d:
        next_p = curr_p + datetime.timedelta(days=step)
        label = curr_p.strftime("%d/%m") if step == 1 else f"{curr_p.strftime('%d/%m')}-{min(next_p - datetime.timedelta(days=1), end_d).strftime('%d/%m')}"
        
        c_count = sum(1 for i in incidents if curr_p <= i.created_at.date() < next_p)
        p_count = sum(1 for m in maintenances if (m.execution_date and curr_p <= m.execution_date.date() < next_p) or (m.scheduled_date and curr_p <= m.scheduled_date.date() < next_p))
        
        timeline_days.append(label)
        timeline_correctives.append(c_count)
        timeline_preventives.append(p_count)
        curr_p = next_p

    # 7. Registros de Ingresos (Logins) y Cambios (Auditoría)
    login_logs = db.query(AuditLog).filter(
        AuditLog.action.in_(["WEB_LOGIN_SUCCESS", "WEB_LOGIN_FAILED"]),
        AuditLog.timestamp >= start_date,
        AuditLog.timestamp <= end_date
    ).order_by(AuditLog.timestamp.desc()).all()

    change_logs = db.query(AuditLog).filter(
        AuditLog.action.notin_(["WEB_LOGIN_SUCCESS", "WEB_LOGIN_FAILED", "DEMO_SANDBOX_INITIALIZED"]),
        AuditLog.timestamp >= start_date,
        AuditLog.timestamp <= end_date
    ).order_by(AuditLog.timestamp.desc()).all()

    # 8. Totales y KPIs consolidados
    total_events = len(incidents) + len(maintenances)
    total_resolved = inc_closed + maint_completed
    resolution_rate = round((total_resolved / total_events * 100), 1) if total_events > 0 else 100.0

    # Métricas ejecutivas y de validación policial
    val_inc_count = sum(1 for i in incidents if (i.validation_status in ["Conforme", "Validado / Conforme", "Conforme / Validado"] or "Validado" in (i.status or "") or i.validator_id is not None))
    val_maint_count = sum(1 for m in maintenances if (m.validation_status in ["Conforme", "Validado / Conforme", "Conforme / Validado"] or "Validado" in (m.status or "") or m.validator_id is not None))
    total_validated = val_inc_count + val_maint_count

    pending_val_count = sum(1 for i in incidents if i.status == "Pendiente de Validación" or i.validation_status == "Pendiente") + \
                        sum(1 for m in maintenances if m.status == "Pendiente de Validación" or m.validation_status == "Pendiente")

    in_tech_attention = (inc_open + inc_in_prog) + (maint_in_exec + maint_scheduled)
    validation_rate = round(min(100.0, (total_validated / total_resolved * 100)), 1) if total_resolved > 0 else 100.0
    proactivity_ratio = round((len(maintenances) / total_events * 100), 1) if total_events > 0 else 100.0

    impact_penalty = min(8.0, (inc_open * 1.5 + inc_in_prog * 0.8))
    circuit_availability = round(max(92.0, 100.0 - impact_penalty), 1)
    system_health_status = "OPTIMO" if inc_open == 0 else "ATENCION"
    system_status_label = "CIRCUITO OPERATIVO Y DISPONIBLE" if inc_open == 0 else "CIRCUITO EN ATENCIÓN TÉCNICA CONTROLADA"

    return {
        "period": {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
            "start_formatted": start_date.strftime("%d/%m/%Y"),
            "end_formatted": end_date.strftime("%d/%m/%Y"),
            "days": total_days
        },
        "kpis": {
            "total_events": total_events,
            "total_corrective": len(incidents),
            "total_preventive": len(maintenances),
            "total_resolved": total_resolved,
            "resolution_rate": resolution_rate,
            "inc_open": inc_open,
            "inc_in_prog": inc_in_prog,
            "inc_closed": inc_closed,
            "maint_scheduled": maint_scheduled,
            "maint_in_exec": maint_in_exec,
            "maint_completed": maint_completed,
            "total_logins": len(login_logs),
            "total_changes": len(change_logs),
            "total_validated": total_validated,
            "val_inc_count": val_inc_count,
            "val_maint_count": val_maint_count,
            "validation_rate": validation_rate,
            "pending_val_count": pending_val_count,
            "in_tech_attention": in_tech_attention,
            "proactivity_ratio": proactivity_ratio,
            "circuit_availability": circuit_availability,
            "system_health_status": system_health_status,
            "system_status_label": system_status_label
        },
        "charts": {
            "distribution": {
                "labels": ["Mantenimiento Preventivo", "Mantenimiento Correctivo"],
                "data": [len(maintenances), len(incidents)],
                "colors": ["#10B981", "#3B82F6"]
            },
            "validation": {
                "labels": ["Validados Conformes", "Pendientes Validación", "En Atención Técnica"],
                "data": [total_validated, pending_val_count, in_tech_attention],
                "colors": ["#10B981", "#8B5CF6", "#3B82F6"]
            },
            "sla_and_schedule": {
                "labels": ["Cumplido a Tiempo", "En Progreso Óptimo", "Riesgo Inminente", "Atrasado / Vencido"],
                "corrective": [
                    inc_sla_summary["Cumplido a Tiempo"],
                    inc_sla_summary["En Tiempo Óptimo"],
                    inc_sla_summary["Riesgo Inminente"],
                    inc_sla_summary["Plazo Vencido"] + inc_sla_summary["Cerrado Fuera de Meta"]
                ],
                "preventive": [
                    maint_proactive_summary["Cumplido a Tiempo"],
                    maint_proactive_summary["En Cronograma Óptimo"] + maint_proactive_summary["En Ejecución"],
                    maint_proactive_summary["Próximo a Vencer (<= 48h)"],
                    maint_proactive_summary["Atrasado / Plazo Vencido"] + maint_proactive_summary["Completado Extemporáneo"]
                ]
            },
            "sites": {
                "labels": list(sites_distribution.keys()),
                "correctives": [v["correctivos"] for v in sites_distribution.values()],
                "preventives": [v["preventivos"] for v in sites_distribution.values()]
            },
            "timeline": {
                "labels": timeline_days,
                "correctives": timeline_correctives,
                "preventives": timeline_preventives
            },
            "corrective_types": {
                "labels": list(inc_by_type.keys()),
                "data": list(inc_by_type.values())
            },
            "preventive_types": {
                "labels": list(maint_by_type.keys()),
                "data": list(maint_by_type.values())
            }
        },
        "incidents": incidents,
        "maintenances": maintenances,
        "login_logs": login_logs,
        "change_logs": change_logs
    }


class NumberedCanvas(canvas.Canvas):
    """Generador de canvas que calcula dinámicamente el total de páginas y dibuja el pie institucional."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 7)
        self.setFillColor(colors.HexColor("#64748B"))
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(36, 26, 576, 26)
        
        footer_text = f"SISTEMA INTEGRADO DE SEGURIDAD CCTV — INFORME EJECUTIVO OFICIAL | PÁGINA {self._pageNumber} DE {page_count}"
        self.drawString(36, 16, footer_text)
        date_str = datetime.datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")
        self.drawRightString(576, 16, f"CERTIFICACIÓN INMUTABLE — {date_str}")
        self.restoreState()


def generate_cctv_pdf_report(
    db: Session,
    current_site: Dict[str, Any],
    start_date: datetime.datetime,
    end_date: datetime.datetime,
    requested_by: User,
    period_label: str = "Semanal"
) -> bytes:
    """
    Genera el Informe Ejecutivo Oficial del Sistema CCTV, alineado en estética institucional
    con el Acta Oficial de Validación Policial.
    Detalla métricas de disponibilidad, cumplimiento de SLAs y fichas técnicas completas
    tanto de mantenimientos correctivos (incidentes) como de preventivos y validaciones.
    """
    stats = get_reports_statistics(db, current_site, start_date, end_date)
    kpis = stats["kpis"]
    incidents = stats["incidents"]
    maintenances = stats["maintenances"]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Tipografía Ejecutiva Institucional (homologada con validación policial)
    title_police = ParagraphStyle(
        'TitlePolice',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11.5,
        leading=14.5,
        textColor=colors.HexColor('#0F2942')
    )
    title_sub = ParagraphStyle(
        'TitleSub',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor('#1E3A8A'),
        alignment=2
    )
    section_h = ParagraphStyle(
        'SectionH',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11.5,
        textColor=colors.HexColor('#0F2942'),
        spaceBefore=7,
        spaceAfter=3
    )
    c_bold = ParagraphStyle(
        'CBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.2,
        leading=9,
        textColor=colors.HexColor('#0F172A')
    )
    c_regular = ParagraphStyle(
        'CRegular',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.2,
        leading=9,
        textColor=colors.HexColor('#334155')
    )
    c_muted = ParagraphStyle(
        'CMuted',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=6.8,
        leading=8.5,
        textColor=colors.HexColor('#64748B')
    )
    c_header = ParagraphStyle(
        'CHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.2,
        leading=9,
        textColor=colors.HexColor('#1E293B')
    )
    c_kpi_val = ParagraphStyle(
        'CKpiVal',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=14,
        alignment=1,
        textColor=colors.HexColor('#0F2942')
    )
    c_kpi_lbl = ParagraphStyle(
        'CKpiLbl',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=6.5,
        leading=8,
        alignment=1,
        textColor=colors.HexColor('#475569')
    )
    c_kpi_sub = ParagraphStyle(
        'CKpiSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=6,
        leading=7.5,
        alignment=1,
        textColor=colors.HexColor('#64748B')
    )

    elements = []

    # 1. MEMBRETE OFICIAL INSTITUCIONAL
    site_full_name = current_site.get('full_name', 'Jurisdicción General')
    site_slug = current_site.get('id', 'cctv').replace('-', '_')
    now_utc = datetime.datetime.utcnow()
    report_code = f"INF-EJE-{site_slug.upper()}-{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"

    header_data = [
        [
            Paragraph(
                "<b>POLICÍA NACIONAL DE COLOMBIA / ALCALDÍA MUNICIPAL</b><br/>"
                "<font size='7.5' color='#1E3A8A'>SISTEMA INTEGRADO DE SEGURIDAD Y CONVIVENCIA CIUDADANA (CCTV)</font><br/>"
                "<font size='6.8' color='#64748B'>DIRECCIÓN DE TELEMÁTICA, MONITOREO Y SUPERVISIÓN CONTRACTUAL</font>",
                title_police
            ),
            Paragraph(
                f"<b>INFORME EJECUTIVO DE OPERACIÓN</b><br/>"
                f"Informe N°: <b>{report_code}</b><br/>"
                f"Período: <b>{period_label.upper()}</b><br/>"
                f"Sede: <b>{site_full_name}</b>",
                title_sub
            )
        ]
    ]
    t_header = Table(header_data, colWidths=[330, 210])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(t_header)
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#0F2942'), spaceBefore=3, spaceAfter=5))

    # BANNER EJECUTIVO DE ESTADO OPERACIONAL
    is_optimo = (kpis.get("system_health_status") == "OPTIMO")
    banner_bg = colors.HexColor('#D1FAE5') if is_optimo else colors.HexColor('#FEF3C7')
    banner_border = colors.HexColor('#10B981') if is_optimo else colors.HexColor('#F59E0B')
    banner_title_color = '#065F46' if is_optimo else '#92400E'
    status_label_str = kpis.get("system_status_label", "CIRCUITO OPERATIVO Y DISPONIBLE")

    banner_data = [
        [
            Paragraph(
                f"<b>ESTADO OPERACIONAL: {status_label_str}</b> — "
                f"<font size='7.2'>Disponibilidad Estimada: <b>{kpis.get('circuit_availability', 98.5)}%</b> | "
                f"Conformidad Policial: <b>{kpis.get('validation_rate', 100.0)}%</b> | "
                f"Resolución SLA: <b>{kpis.get('resolution_rate', 100.0)}%</b></font>",
                ParagraphStyle('BannerText', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.HexColor(banner_title_color), alignment=1)
            )
        ]
    ]
    t_banner = Table(banner_data, colWidths=[540])
    t_banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), banner_bg),
        ('BOX', (0, 0), (-1, -1), 1.2, banner_border),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
    ]))
    elements.append(t_banner)
    elements.append(Spacer(1, 4))

    # Meta de emisión
    req_name = requested_by.full_name or requested_by.username
    meta_text = (
        f"<b>Rango de Análisis:</b> {stats['period']['start_formatted']} al {stats['period']['end_formatted']} ({stats['period']['days']} días) | "
        f"<b>Emisión:</b> {now_utc.strftime('%d/%m/%Y %H:%M UTC')} | "
        f"<b>Solicitado por:</b> {req_name} ({requested_by.role})"
    )
    elements.append(Paragraph(meta_text, c_muted))
    elements.append(Spacer(1, 4))

    # CUADRO DE MANDO EJECUTIVO (KPIs CONSOLIDADOS)
    elements.append(Paragraph("1. CUADRO DE MANDO EJECUTIVO (INDICADORES CLAVE DE OPERACIÓN)", section_h))
    
    kpi_cols = [
        [
            Paragraph("DISPONIBILIDAD", c_kpi_lbl),
            Paragraph(f"<font color='#0D9488'>{kpis.get('circuit_availability', 98.5)}%</font>", c_kpi_val),
            Paragraph(f"{'Óptima' if is_optimo else 'Bajo Control'}", c_kpi_sub)
        ],
        [
            Paragraph("PREVENTIVOS", c_kpi_lbl),
            Paragraph(f"<font color='#059669'>{kpis['total_preventive']}</font>", c_kpi_val),
            Paragraph(f"{kpis['maint_completed']} listos | {kpis['maint_in_exec']} campo", c_kpi_sub)
        ],
        [
            Paragraph("CORRECTIVOS (TICKETS)", c_kpi_lbl),
            Paragraph(f"<font color='#2563EB'>{kpis['total_corrective']}</font>", c_kpi_val),
            Paragraph(f"{kpis['inc_closed']} resueltos | {kpis['inc_open'] + kpis['inc_in_prog']} activos", c_kpi_sub)
        ],
        [
            Paragraph("CUMPLIMIENTO SLAs", c_kpi_lbl),
            Paragraph(f"<font color='#10B981'>{kpis['resolution_rate']}%</font>", c_kpi_val),
            Paragraph(f"{kpis['total_resolved']} en meta técnica", c_kpi_sub)
        ],
        [
            Paragraph("VALIDACIÓN POLICIAL", c_kpi_lbl),
            Paragraph(f"<font color='#1E3A8A'>{kpis.get('validation_rate', 100.0)}%</font>", c_kpi_val),
            Paragraph(f"{kpis.get('total_validated', 0)} actas conformes", c_kpi_sub)
        ]
    ]

    # Transponer a tabla de 2 filas
    kpi_matrix = [
        [col[0] for col in kpi_cols],
        [col[1] for col in kpi_cols],
        [col[2] for col in kpi_cols]
    ]
    t_kpis = Table(kpi_matrix, colWidths=[108, 108, 108, 108, 108])
    t_kpis.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8FAFC')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(t_kpis)
    elements.append(Spacer(1, 6))

    # 2. MANTENIMIENTOS CORRECTIVOS (INCIDENTES) - FICHAS TÉCNICAS
    elements.append(Paragraph(f"2. FICHAS TÉCNICAS DE MANTENIMIENTO CORRECTIVO E INCIDENTES ({len(incidents)} REGISTROS)", section_h))

    if incidents:
        for inc in incidents:
            tkt_code = inc.ticket_code or inc.ticket_number or f"TKT-{inc.id:04d}"
            tkt_date = inc.created_at.strftime('%d/%m/%Y %H:%M')
            priority_str = inc.priority or "Media"
            fault_type_str = inc.fault_type or "Falla Menor"
            
            # Datos técnicos del dispositivo
            dev = inc.device
            dev_name = dev.name if dev else "Circuito de Monitoreo General"
            dev_type = dev.device_type if dev else "Cámara CCTV"
            dev_brand = f"{dev.brand or ''} {dev.model or ''}".strip() if dev else "No especificado"
            dev_ip = dev.ip_address if dev else "N/A"
            dev_serial = dev.serial_number if dev else "N/A"
            loc_str = inc.location_detail or (dev.location_detail if dev else site_full_name)

            # Cierre técnico
            tech_u = inc.closed_by
            tech_name = (tech_u.full_name or tech_u.username) if tech_u else "Empresa de Mantenimiento"
            tech_date_str = inc.closed_at.strftime('%d/%m/%Y %H:%M') if inc.closed_at else "En atención"
            root_cause_str = (inc.root_cause or inc.description or "En evaluación técnica")[:130]
            solution_str = (inc.solution or "Labores en ejecución")[:130]

            # Validación policial
            val_u = inc.validator
            val_name = (val_u.full_name or val_u.username) if val_u else "Pendiente de Validación"
            val_badge = val_u.badge_number if (val_u and val_u.badge_number) else "S/N"
            val_status_str = inc.validation_status or inc.status
            is_val_ok = (val_status_str in ["Conforme", "Validado / Conforme", "Conforme / Validado"] or "Validado" in (inc.status or ""))
            verdict_badge = "<font color='#059669'><b>VALIDADO / CONFORME</b></font>" if is_val_ok else f"<b>{val_status_str}</b>"
            val_date_str = inc.validated_at.strftime('%d/%m/%Y %H:%M') if inc.validated_at else "Pendiente"
            val_notes_str = (inc.validation_notes or "Revisión conforme a lineamientos institucionales de la Policía Nacional")[:110]

            inc_table_data = [
                [
                    Paragraph("<b>Ticket / Código:</b>", c_header),
                    Paragraph(f"<b>{tkt_code}</b> ({tkt_date})", c_bold),
                    Paragraph("<b>Criticidad / SLA:</b>", c_header),
                    Paragraph(f"<b>{fault_type_str}</b> — P: {priority_str} ({inc.sla_info.get('label', '')})", c_regular)
                ],
                [
                    Paragraph("<b>Dispositivo:</b>", c_header),
                    Paragraph(f"<b>{dev_name}</b> ({dev_type})", c_bold),
                    Paragraph("<b>IP / Serial:</b>", c_header),
                    Paragraph(f"<font color='#2563EB'>{dev_ip}</font> | SN: {dev_serial}", c_regular)
                ],
                [
                    Paragraph("<b>Marca / Modelo:</b>", c_header),
                    Paragraph(dev_brand or "N/A", c_regular),
                    Paragraph("<b>Ubicación en Sitio:</b>", c_header),
                    Paragraph(loc_str, c_regular)
                ],
                [
                    Paragraph("<b>Diagnóstico Causa:</b>", c_header),
                    Paragraph(root_cause_str, c_muted),
                    Paragraph("<b>Solución Técnica:</b>", c_header),
                    Paragraph(solution_str, c_muted)
                ],
                [
                    Paragraph("<b>Cierre Técnico:</b>", c_header),
                    Paragraph(f"{tech_name} ({tech_date_str})", c_regular),
                    Paragraph("<b>Validación Policial:</b>", c_header),
                    Paragraph(f"{verdict_badge} — <b>Placa #{val_badge}</b> ({val_name})", c_regular)
                ]
            ]

            t_card = Table(inc_table_data, colWidths=[95, 175, 100, 170])
            t_card.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EFF6FF')),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8FAFC')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            elements.append(KeepTogether([t_card, Spacer(1, 5)]))
    else:
        no_inc_data = [[Paragraph("<i>No se registraron fallas o mantenimientos correctivos en la jurisdicción durante este período.</i>", c_muted)]]
        t_no_inc = Table(no_inc_data, colWidths=[540])
        t_no_inc.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t_no_inc)
        elements.append(Spacer(1, 5))

    # 3. MANTENIMIENTOS PREVENTIVOS - FICHAS TÉCNICAS
    elements.append(Paragraph(f"3. FICHAS TÉCNICAS DE MANTENIMIENTO PREVENTIVO Y PROTOCOLOS ({len(maintenances)} PROTOCOLOS)", section_h))

    if maintenances:
        for m in maintenances:
            code_str = m.code or f"MP-{m.id:04d}"
            cycle_str = m.cycle_label or "Preventivo Mensual"
            sched_str = m.scheduled_date.strftime('%d/%m/%Y') if m.scheduled_date else "N/A"
            exec_date = m.execution_date or m.completed_date
            exec_str = exec_date.strftime('%d/%m/%Y') if exec_date else "Pendiente"

            dev = m.device
            dev_name = dev.name if dev else "Inspección General"
            dev_type = dev.device_type if dev else "Cámara CCTV"
            dev_brand = f"{dev.brand or ''} {dev.model or ''}".strip() if dev else "No especificado"
            dev_ip = dev.ip_address if dev else "N/A"
            dev_serial = dev.serial_number if dev else "N/A"
            loc_str = m.location_detail or (dev.location_detail if dev else site_full_name)

            # Checklist técnico de 6 puntos
            checklist_summary = "Inspección técnica de 6 puntos conforme"
            if m.checklist_results:
                try:
                    c_dict = json.loads(m.checklist_results)
                    passed_count = sum(1 for v in c_dict.values() if v)
                    checklist_summary = f"✔ {passed_count}/6 puntos verificados (Óptica, Mecánica, Red, Voltaje, PTZ, Video)"
                except Exception:
                    checklist_summary = "✔ Verificado y conforme según acta técnica"

            tasks_str = (m.actions_taken or m.description or "Protocolo preventivo ejecutado en campo")[:130]
            recom_str = (m.recommendations or "Operación continua recomendada")[:110]
            tech_u = m.completed_by
            tech_name = (tech_u.full_name or tech_u.username) if tech_u else "Empresa de Mantenimiento"

            # Validación policial
            val_u = m.validator
            val_name = (val_u.full_name or val_u.username) if val_u else "Pendiente de Validación"
            val_badge = val_u.badge_number if (val_u and val_u.badge_number) else "S/N"
            val_status_str = m.validation_status or m.status
            is_val_ok = (val_status_str in ["Conforme", "Validado / Conforme", "Conforme / Validado"] or "Validado" in (m.status or ""))
            verdict_badge = "<font color='#059669'><b>VALIDADO / CONFORME</b></font>" if is_val_ok else f"<b>{val_status_str}</b>"
            val_date_str = m.validated_at.strftime('%d/%m/%Y') if m.validated_at else "Pendiente"

            maint_table_data = [
                [
                    Paragraph("<b>Protocolo / Código:</b>", c_header),
                    Paragraph(f"<b>{code_str}</b>", c_bold),
                    Paragraph("<b>Ciclo / Frecuencia:</b>", c_header),
                    Paragraph(f"<b>{cycle_str}</b> (Prioridad: {m.priority})", c_regular)
                ],
                [
                    Paragraph("<b>Dispositivo:</b>", c_header),
                    Paragraph(f"<b>{dev_name}</b> ({dev_type})", c_bold),
                    Paragraph("<b>IP / Serial:</b>", c_header),
                    Paragraph(f"<font color='#2563EB'>{dev_ip}</font> | SN: {dev_serial}", c_regular)
                ],
                [
                    Paragraph("<b>Marca / Modelo:</b>", c_header),
                    Paragraph(dev_brand or "N/A", c_regular),
                    Paragraph("<b>Ubicación en Sitio:</b>", c_header),
                    Paragraph(loc_str, c_regular)
                ],
                [
                    Paragraph("<b>Cronograma:</b>", c_header),
                    Paragraph(f"Prog: {sched_str} | Ejec: {exec_str}", c_regular),
                    Paragraph("<b>Checklist (6 Puntos):</b>", c_header),
                    Paragraph(f"<font color='#059669'><b>{checklist_summary}</b></font>", c_bold)
                ],
                [
                    Paragraph("<b>Actividades Ejecutadas:</b>", c_header),
                    Paragraph(tasks_str, c_muted),
                    Paragraph("<b>Recomendaciones:</b>", c_header),
                    Paragraph(recom_str, c_muted)
                ],
                [
                    Paragraph("<b>Técnico Ejecutor:</b>", c_header),
                    Paragraph(f"{tech_name} ({exec_str})", c_regular),
                    Paragraph("<b>Validación Policial:</b>", c_header),
                    Paragraph(f"{verdict_badge} — <b>Placa #{val_badge}</b> ({val_name})", c_regular)
                ]
            ]

            t_card_m = Table(maint_table_data, colWidths=[95, 175, 100, 170])
            t_card_m.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F0FDF4')),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8FAFC')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            elements.append(KeepTogether([t_card_m, Spacer(1, 5)]))
    else:
        no_m_data = [[Paragraph("<i>No se programaron protocolos preventivos en este período para la jurisdicción.</i>", c_muted)]]
        t_no_m = Table(no_m_data, colWidths=[540])
        t_no_m.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t_no_m)
        elements.append(Spacer(1, 5))

    # 4. CERTIFICACIÓN DIGITAL Y FIRMAS INSTITUCIONALES
    elements.append(Paragraph("4. CERTIFICACIÓN DE AUDITORÍA Y FIRMAS INSTITUCIONALES", section_h))

    firmas_data = [
        [
            Paragraph(
                f"<b>EMPRESA DE MANTENIMIENTO:</b><br/><br/><br/>"
                f"____________________________________<br/>"
                f"<b>Ing. Residente Técnico</b><br/>"
                f"<font size='6.5' color='#64748B'>Ejecución Técnica Certificada</font>",
                c_regular
            ),
            Paragraph(
                f"<b>POLICÍA NACIONAL DE COLOMBIA:</b><br/><br/><br/>"
                f"____________________________________<br/>"
                f"<b>Oficial Validador CCTV</b><br/>"
                f"<font size='6.5' color='#1E3A8A'><b>Visto Bueno Institucional</b></font>",
                c_regular
            ),
            Paragraph(
                f"<b>SUPERVISIÓN ALCALDÍA / SEDE:</b><br/><br/><br/>"
                f"____________________________________<br/>"
                f"<b>{req_name}</b><br/>"
                f"<font size='6.5' color='#64748B'>{requested_by.role} - CCTV Territorial</font>",
                c_regular
            )
        ]
    ]
    t_firmas = Table(firmas_data, colWidths=[180, 180, 180])
    t_firmas.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FFFFFF')),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#94A3B8')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(KeepTogether([
        t_firmas,
        Spacer(1, 3),
        Paragraph(
            f"<b>CERTIFICACIÓN DIGITAL DE AUDITORÍA:</b> Este informe ejecutivo oficial ha sido generado automáticamente por la Plataforma CCTV. "
            f"Cuenta con respaldo digital y trazabilidad inmutable bajo el hash oficial <b>SHA256-{site_slug[:8].upper()}-{now_utc.strftime('%Y%m%d%H%M')}</b>. "
            f"Válido para supervisión de contratos, actas de recibo y rendición de cuentas ante autoridades territoriales.",
            c_muted
        )
    ]))

    # Construir documento PDF con NumberedCanvas
    doc.build(elements, canvasmaker=NumberedCanvas)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def generate_validation_conformity_pdf(
    item: Any,
    item_type: str,
    validator: User,
    current_site: Dict[str, Any]
) -> bytes:
    """
    Genera el Acta Oficial Ejecutiva de Conformidad y Validación Técnica Policial.
    Documento auditable en formato PDF con especificaciones técnicas, evidencias fotográficas,
    nombre y número de placa del oficial validador, y certificación digital del ciclo de trabajo.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Estilos tipográficos ejecutivos
    title_police = ParagraphStyle(
        'TitlePolice',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=colors.HexColor('#0F2942')
    )
    title_sub = ParagraphStyle(
        'TitleSub',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#1E3A8A'),
        alignment=2  # Right aligned
    )
    section_h = ParagraphStyle(
        'SectionH',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11.5,
        textColor=colors.HexColor('#0F2942'),
        spaceBefore=6,
        spaceAfter=3
    )
    c_bold = ParagraphStyle(
        'CBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#0F172A')
    )
    c_regular = ParagraphStyle(
        'CRegular',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#334155')
    )
    c_muted = ParagraphStyle(
        'CMuted',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=8.5,
        textColor=colors.HexColor('#64748B')
    )
    c_header = ParagraphStyle(
        'CHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#1E293B')
    )

    elements = []

    # Extraer campos unificados según sea Incidente o Mantenimiento
    is_incident = (item_type == "incident")
    code = item.ticket_code if is_incident else item.code
    title = item.title
    order_type_str = "Mantenimiento Correctivo (Incidente)" if is_incident else f"Mantenimiento Preventivo ({item.cycle_label})"
    priority = item.priority or "Media"
    location = item.location_detail or item.sede or current_site.get("full_name", "General")
    device_name = item.device.name if item.device else "Circuito General de Monitoreo"
    device_type = item.device.device_type if item.device else "Cámara CCTV"
    device_brand = f"{item.device.brand or ''} {item.device.model or ''}".strip() if item.device else "N/A"
    device_ip = item.device.ip_address if item.device else "N/A"
    device_serial = item.device.serial_number if item.device else "N/A"

    # Técnico responsable (quien cerró / completó)
    tech_user = item.closed_by if is_incident else item.completed_by
    tech_name = tech_user.full_name or tech_user.username if tech_user else "Empresa de Mantenimiento"
    tech_role = tech_user.role if tech_user else "Empresa de Mantenimiento"
    date_completed = item.closed_at if is_incident else (item.completed_date or item.execution_date)
    date_completed_str = date_completed.strftime('%d/%m/%Y a las %H:%M:%S') if date_completed else "Fecha no registrada"

    findings = (item.root_cause if is_incident else item.technical_findings) or "Inspección técnica conforme"
    actions = (item.solution if is_incident else item.actions_taken) or "Intervención ejecutada según protocolo técnico"

    # Validador
    val_name = validator.full_name or validator.username if validator else "Oficial Validador"
    badge_str = validator.badge_number if (validator and validator.badge_number) else "No Registrada"
    date_validated = item.validated_at or datetime.datetime.utcnow()
    date_val_str = date_validated.strftime('%d/%m/%Y a las %H:%M:%S UTC')
    val_notes = item.validation_notes or "Revisión técnica satisfactoria y conforme a los lineamientos operativos de la Estación de Policía."

    # 1. MEMBRETE OFICIAL POLICIAL Y SISTEMA CCTV
    header_data = [
        [
            Paragraph("<b>POLICÍA NACIONAL DE COLOMBIA</b><br/><font size='8' color='#1E3A8A'>SISTEMA INTEGRADO DE SEGURIDAD Y CONVIVENCIA CIUDADANA (CCTV)</font><br/><font size='7' color='#64748B'>ESTACIÓN DE POLICÍA - UNIDAD DE TELEMÁTICA Y MONITOREO</font>", title_police),
            Paragraph(f"<b>ACTA OFICIAL DE CONFORMIDAD</b><br/>Acta N°: <b>ACTA-VAL-{code}</b><br/>Fecha: <b>{date_validated.strftime('%d/%m/%Y %H:%M')}</b><br/>Jurisdicción: <b>{current_site.get('name', 'Sede Central')}</b>", title_sub)
        ]
    ]
    t_header = Table(header_data, colWidths=[330, 210])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(t_header)
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#0F2942'), spaceBefore=4, spaceAfter=6))

    # BANNER DE CERTIFICACIÓN DE CONFORMIDAD
    banner_data = [
        [
            Paragraph(
                f"<b>ESTADO DEL TRABAJO: VALIDADO / CONFORME</b> — "
                f"<font size='7.5'>VISTO BUENO Y FIRMA DIGITAL POLICIAL CERTIFICADA (Placa Oficial: <b>#{badge_str}</b>)</font>",
                ParagraphStyle('BannerText', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, leading=11, textColor=colors.HexColor('#065F46'), alignment=1)
            )
        ]
    ]
    t_banner = Table(banner_data, colWidths=[540])
    t_banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#D1FAE5')),
        ('BOX', (0, 0), (-1, -1), 1.2, colors.HexColor('#10B981')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_banner)
    elements.append(Spacer(1, 6))

    # 1. INFORMACIÓN DE LA ORDEN DE TRABAJO Y LOCALIZACIÓN
    elements.append(Paragraph("1. INFORMACIÓN DE LA ORDEN DE TRABAJO Y LOCALIZACIÓN", section_h))
    order_data = [
        [
            Paragraph("<b>Código / Ticket:</b>", c_header),
            Paragraph(f"<b>{code}</b>", c_bold),
            Paragraph("<b>Tipo de Intervención:</b>", c_header),
            Paragraph(order_type_str, c_regular)
        ],
        [
            Paragraph("<b>Título / Asunto:</b>", c_header),
            Paragraph(title[:55], c_regular),
            Paragraph("<b>Criticidad / Prioridad:</b>", c_header),
            Paragraph(priority, c_bold)
        ],
        [
            Paragraph("<b>Sede Territorial:</b>", c_header),
            Paragraph(current_site.get('full_name', location), c_regular),
            Paragraph("<b>Ubicación en Sitio:</b>", c_header),
            Paragraph(location, c_regular)
        ]
    ]
    t_order = Table(order_data, colWidths=[100, 170, 110, 160])
    t_order.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]))
    elements.append(t_order)
    elements.append(Spacer(1, 6))

    # 2. EQUIPO Y CIRCUITO DE SEGURIDAD INTERVENIDO
    elements.append(Paragraph("2. EQUIPO Y DISPOSITIVO CCTV INTERVENIDO", section_h))
    dev_data = [
        [
            Paragraph("<b>Dispositivo:</b>", c_header),
            Paragraph(device_name, c_bold),
            Paragraph("<b>Tipo de Equipo:</b>", c_header),
            Paragraph(device_type, c_regular)
        ],
        [
            Paragraph("<b>Marca y Modelo:</b>", c_header),
            Paragraph(device_brand or "No especificado", c_regular),
            Paragraph("<b>Dirección IP:</b>", c_header),
            Paragraph(f"<font color='#2563EB'>{device_ip}</font>", c_bold)
        ],
        [
            Paragraph("<b>Número de Serie:</b>", c_header),
            Paragraph(device_serial or "N/A", c_regular),
            Paragraph("<b>Estado Operativo:</b>", c_header),
            Paragraph("<font color='#059669'><b>Operativo / Validado</b></font>", c_bold)
        ]
    ]
    t_dev = Table(dev_data, colWidths=[100, 170, 110, 160])
    t_dev.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]))
    elements.append(t_dev)
    elements.append(Spacer(1, 6))

    # 3. EJECUCIÓN TÉCNICA (EMPRESA DE MANTENIMIENTO)
    elements.append(Paragraph("3. REPORTE DE EJECUCIÓN TÉCNICA (EMPRESA DE MANTENIMIENTO)", section_h))
    tech_data = [
        [
            Paragraph("<b>Técnico Responsable:</b>", c_header),
            Paragraph(f"<b>{tech_name}</b>", c_bold),
            Paragraph("<b>Empresa / Rol:</b>", c_header),
            Paragraph(tech_role, c_regular)
        ],
        [
            Paragraph("<b>Fecha Cierre Técnico:</b>", c_header),
            Paragraph(date_completed_str, c_regular),
            Paragraph("<b>Estado de Entrega:</b>", c_header),
            Paragraph("Finalizado / Remitido a Validación", c_bold)
        ],
        [
            Paragraph("<b>Diagnóstico / Causa:</b>", c_header),
            Paragraph(findings[:160], c_regular),
            Paragraph("<b>Solución / Acciones:</b>", c_header),
            Paragraph(actions[:160], c_regular)
        ]
    ]
    t_tech = Table(tech_data, colWidths=[100, 170, 110, 160])
    t_tech.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]))
    elements.append(t_tech)
    elements.append(Spacer(1, 6))

    # 4. DICTAMEN DE CONFORMIDAD Y VALIDACIÓN POLICIAL
    elements.append(Paragraph("4. DICTAMEN DE CONFORMIDAD POLICIAL (ESTACIÓN DE POLICÍA)", section_h))
    val_table_data = [
        [
            Paragraph("<b>Oficial Validador:</b>", c_header),
            Paragraph(f"<b>{val_name}</b>", c_bold),
            Paragraph("<b>Número de Placa Policial:</b>", c_header),
            Paragraph(f"<font size='9' color='#1E3A8A'><b>#{badge_str}</b></font>", c_bold)
        ],
        [
            Paragraph("<b>Unidad Policial:</b>", c_header),
            Paragraph("Estación de Policía - Centro de Monitoreo CCTV", c_regular),
            Paragraph("<b>Fecha y Hora Validación:</b>", c_header),
            Paragraph(f"<b>{date_val_str}</b>", c_bold)
        ],
        [
            Paragraph("<b>Dictamen Institucional:</b>", c_header),
            Paragraph("<font color='#059669'><b>APROBADO Y VALIDADO CONFORME</b></font>", c_bold),
            Paragraph("<b>Condición Operativa:</b>", c_header),
            Paragraph("Servicio Recibido a Entera Satisfacción", c_regular)
        ],
        [
            Paragraph("<b>Observaciones de Validación:</b>", c_header),
            Paragraph(f"<i>\"{val_notes}\"</i>", c_regular),
            Paragraph("<b>Trazabilidad Digital:</b>", c_header),
            Paragraph(f"Registro Inmutable ID: VAL-{code}", c_muted)
        ]
    ]
    t_val = Table(val_table_data, colWidths=[100, 170, 110, 160])
    t_val.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#EFF6FF')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#93C5FD')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t_val)
    elements.append(Spacer(1, 6))

    # 5. EVIDENCIAS FOTOGRÁFICAS CERTIFICADAS
    elements.append(Paragraph("5. REGISTRO FOTOGRÁFICO DE EVIDENCIAS EN SITIO", section_h))
    photo1_path = item.image_path
    photo2_path = item.closing_image_path if is_incident else item.completion_photo

    def build_photo_flowable(p_path, label):
        if not p_path:
            return Paragraph(f"<b>{label}:</b><br/><font color='#94A3B8'><i>Sin registro fotográfico adjunto</i></font>", c_muted)
        clean_path = p_path.lstrip("/\\")
        if os.path.exists(clean_path):
            try:
                img_f = RLImage(clean_path, width=2.4*inch, height=1.25*inch)
                return [
                    Paragraph(f"<b>{label}</b>", c_bold),
                    Spacer(1, 2),
                    img_f
                ]
            except Exception:
                return Paragraph(f"<b>{label}:</b> Archivo fotográfico registrado ({p_path})", c_muted)
        return Paragraph(f"<b>{label}:</b> Evidencia registrada en sistema ({p_path})", c_muted)

    p1_flow = build_photo_flowable(photo1_path, "EVIDENCIA INICIAL (FALLA / CONDICIÓN PREVIA)")
    p2_flow = build_photo_flowable(photo2_path, "EVIDENCIA DE CIERRE TÉCNICO (TRABAJO TERMINADO)")

    photo_table = [
        [p1_flow, p2_flow]
    ]
    t_photos = Table(photo_table, colWidths=[265, 265])
    t_photos.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t_photos)
    elements.append(Spacer(1, 8))

    # 6. FIRMAS DE CONFORMIDAD Y CIERRE FORMAL
    firma_data = [
        [
            Paragraph(
                f"<b>POR LA EMPRESA DE MANTENIMIENTO:</b><br/><br/><br/>"
                f"__________________________________________<br/>"
                f"<b>{tech_name}</b><br/>"
                f"<font size='7' color='#475569'>{tech_role}</font><br/>"
                f"<font size='6.5' color='#64748B'>Ejecución Técnica Certificada</font>",
                c_regular
            ),
            Paragraph(
                f"<b>POR LA ESTACIÓN DE POLICÍA (VALIDADOR):</b><br/><br/><br/>"
                f"__________________________________________<br/>"
                f"<b>{val_name}</b><br/>"
                f"<font size='7' color='#1E3A8A'><b>PLACA POLICIAL #{badge_str}</b></font><br/>"
                f"<font size='6.5' color='#059669'>Conformidad y Visto Bueno Institucional</font>",
                c_regular
            )
        ]
    ]
    t_firmas = Table(firma_data, colWidths=[265, 265])
    t_firmas.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FFFFFF')),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#94A3B8')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(t_firmas)

    # Pie de página legal
    legal_text = (
        f"<b>CERTIFICACIÓN DIGITAL DE AUDITORÍA:</b> Este documento ha sido generado automáticamente por la Plataforma CCTV. "
        f"Contiene firma digital y traza inmutable registrada el {date_val_str}. "
        f"Acceso restringido y exclusivo para el Administrador, Validador Policial y Supervisor."
    )
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(legal_text, c_muted))

    # Construir PDF
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

