import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, Optional

from app.config import settings

logger = logging.getLogger("cctv_email_service")


def send_temporary_password_email(
    to_email: str,
    full_name: str,
    temp_password: str,
    site_name: Optional[str] = None,
    badge_number: Optional[str] = None
) -> Dict[str, Any]:
    """
    Envía una notificación por correo electrónico al usuario con su contraseña temporal de 24 horas.
    Si SMTP_HOST está configurado en las variables de entorno, realiza el despacho SMTP real.
    Si no está configurado, simula el envío y registra la credencial en logs de manera segura.
    """
    subject = "Contraseña temporal sistema gestión CCTV"
    site_info = f"Sede Territorial: {site_name}\n" if site_name else ""
    badge_info = f"Placa Policial: #{badge_number}\n" if badge_number else ""

    text_body = (
        f"Estimado(a) {full_name},\n\n"
        f"{site_info}"
        f"{badge_info}\n"
        f"Esperamos que se encuentre muy bien.\n\n"
        f"Atendiendo a su solicitud de restablecimiento de acceso en la plataforma del Sistema de Gestión de Circuitos Cerrados de Televisión (CCTV), le hacemos entrega de su contraseña temporal:\n\n"
        f"   {temp_password}\n\n"
        f"Recomendaciones importantes para su ingreso:\n"
        f"1. Esta contraseña temporal cuenta con una validez de 24 horas continuas a partir de este momento.\n"
        f"2. Al ingresar a la plataforma con su correo electrónico ({to_email}) y esta contraseña temporal, el sistema le solicitará amablemente que configure su nueva contraseña definitiva y confidencial.\n"
        f"3. Si usted no realizó esta solicitud o requiere asistencia adicional, por favor comuníquese de inmediato con el Administrador del Sistema.\n\n"
        f"Le deseamos un excelente día.\n\n"
        f"Cordialmente,\n"
        f"Equipo de Soporte y Seguridad - Sistema de Gestión CCTV"
    )

    badge_html_snippet = f'<div style="font-size: 11px; color: #4338ca; font-weight: bold; margin-top: 4px;">Placa Policial: #{badge_number}</div>' if badge_number else ""

    html_body = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f172a; margin: 0; padding: 20px; color: #334155; }}
            .container {{ max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.15); }}
            .header {{ background: linear-gradient(135deg, #1e293b, #0f172a); padding: 28px 24px; text-align: center; color: #ffffff; }}
            .badge {{ display: inline-block; padding: 4px 12px; background: rgba(59, 130, 246, 0.2); border: 1px solid rgba(59, 130, 246, 0.4); color: #93c5fd; font-size: 11px; font-weight: bold; border-radius: 20px; text-transform: uppercase; margin-bottom: 8px; }}
            .title {{ font-size: 20px; font-weight: 800; margin: 0; letter-spacing: -0.5px; }}
            .content {{ padding: 28px 24px; }}
            .greeting {{ font-size: 15px; font-weight: 600; color: #0f172a; margin-bottom: 12px; }}
            .desc {{ font-size: 13px; line-height: 1.6; color: #475569; margin-bottom: 20px; }}
            .card-creds {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; text-align: center; margin: 20px 0; }}
            .creds-label {{ font-size: 11px; font-weight: bold; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }}
            .temp-pass {{ font-family: 'Courier New', Courier, monospace; font-size: 22px; font-weight: 900; color: #1d4ed8; letter-spacing: 2px; padding: 10px 20px; background: #eff6ff; border: 1px dashed #93c5fd; border-radius: 8px; display: inline-block; user-select: all; }}
            .alert-box {{ background: #fef2f2; border-left: 4px solid #ef4444; padding: 12px 16px; border-radius: 6px; margin: 20px 0; font-size: 12px; color: #991b1b; line-height: 1.5; }}
            .steps {{ font-size: 12px; color: #475569; line-height: 1.6; margin: 16px 0; }}
            .footer {{ background: #f1f5f9; padding: 16px 24px; text-align: center; font-size: 11px; color: #64748b; border-top: 1px solid #e2e8f0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="badge">Seguridad CCTV</div>
                <h1 class="title">Contraseña Temporal Sistema Gestión CCTV</h1>
            </div>
            <div class="content">
                <div class="greeting">Estimado(a) {full_name},</div>
                <p class="desc">
                    Esperamos que se encuentre muy bien.<br><br>
                    Atendiendo a su solicitud de acceso en la plataforma del <strong>Sistema de Gestión de Circuitos Cerrados de Televisión (CCTV)</strong>, le hacemos entrega de su contraseña temporal:
                </p>

                <div class="card-creds">
                    <div class="creds-label">Su Contraseña Temporal de Acceso</div>
                    <div class="temp-pass">{temp_password}</div>
                    <div style="font-size: 11px; color: #64748b; margin-top: 8px;">Usuario de Ingreso: <strong>{to_email}</strong></div>
                    {badge_html_snippet}
                </div>

                <div class="alert-box">
                    <strong>⏳ Vigencia:</strong> Esta contraseña temporal cuenta con una validez máxima de <strong>24 horas continuas</strong>.
                </div>

                <div class="steps">
                    <strong>Pasos para restaurar su acceso:</strong>
                    <ol style="margin-top: 6px; padding-left: 18px;">
                        <li>Ingrese al portal con su correo electrónico institucional y la contraseña temporal suministrada arriba.</li>
                        <li>El sistema le solicitará amablemente que establezca su <strong>nueva contraseña definitiva</strong>.</li>
                        <li>Una vez configurada su clave definitiva, podrá acceder con total normalidad y seguridad a la plataforma.</li>
                    </ol>
                </div>

                <p style="font-size: 11px; color: #94a3b8; margin-top: 20px; line-height: 1.5;">
                    Si usted no solicitó este cambio de clave, por favor comuníquese de inmediato con el Administrador del Sistema.
                </p>
            </div>
            <div class="footer">
                Sistema Central de Seguridad y Circuito Cerrado de Televisión (CCTV)<br>
                <em>Mensaje institucional automático de seguridad.</em>
            </div>
        </div>
    </body>
    </html>
    """

    sender_addr = settings.SMTP_FROM or settings.SMTP_USER or "notificaciones@cctv-seguridad.gov.co"
    sender_display = f"{settings.SMTP_FROM_NAME} <{sender_addr}>"

    # Si hay servidor SMTP configurado, intentar envío real a través de la red
    if settings.SMTP_HOST:
        clean_password = settings.SMTP_PASSWORD.replace(" ", "").strip() if settings.SMTP_PASSWORD else None
        
        if settings.SMTP_USER and not clean_password:
            err_msg = "El servidor SMTP requiere contraseña pero SMTP_PASSWORD está vacío en el archivo .env."
            logger.error(err_msg)
            return {
                "success": False,
                "sent_via_smtp": False,
                "error": err_msg,
                "temp_password": temp_password
            }

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = sender_display
            msg["To"] = to_email

            part_text = MIMEText(text_body, "plain", "utf-8")
            part_html = MIMEText(html_body, "html", "utf-8")
            msg.attach(part_text)
            msg.attach(part_html)

            port = settings.SMTP_PORT
            if port == 465:
                server = smtplib.SMTP_SSL(settings.SMTP_HOST, port, timeout=15)
            else:
                server = smtplib.SMTP(settings.SMTP_HOST, port, timeout=15)

            server.ehlo()
            if settings.SMTP_USE_TLS and port != 465:
                server.starttls()
                server.ehlo()

            if settings.SMTP_USER and clean_password:
                server.login(settings.SMTP_USER, clean_password)

            server.sendmail(sender_addr, [to_email], msg.as_string())
            server.quit()

            logger.info(f"Correo de recuperación enviado exitosamente vía SMTP a {to_email}")
            return {
                "success": True,
                "sent_via_smtp": True,
                "message": f"Contraseña temporal enviada exitosamente a '{to_email}'.",
                "temp_password": temp_password
            }
        except smtplib.SMTPAuthenticationError as e:
            err_msg = (
                "Error de autenticación con Gmail SMTP (535). Verifique que la Contraseña de Aplicación "
                "de 16 caracteres en el archivo .env sea la correcta y que la cuenta de Google tenga activa "
                "la verificación en dos pasos."
            )
            logger.error(f"Fallo de autenticación SMTP al enviar a {to_email}: {e}")
            return {
                "success": False,
                "sent_via_smtp": False,
                "error": err_msg,
                "temp_password": temp_password
            }
        except Exception as e:
            err_msg = f"Error al despachar correo por SMTP ({type(e).__name__}): {str(e)}"
            logger.error(f"Error despachando correo SMTP a {to_email}: {e}")
            return {
                "success": False,
                "sent_via_smtp": False,
                "error": err_msg,
                "temp_password": temp_password
            }

    # Si estamos en Modo Demo explícito (sandbox volátil en memoria), simular en consola
    if settings.DEMO_MODE:
        logger.info(f"[MODO DEMO] Correo simulado para {to_email}: {temp_password}")
        print("\n=======================================================")
        print("[MODO DEMO - SERVICIO DE CORREO CCTV]")
        print(f"Para: {full_name} <{to_email}>")
        print(f"Asunto: {subject}")
        print(f"Contraseña Temporal Generada (24h): {temp_password}")
        print("=======================================================\n")
        return {
            "success": True,
            "sent_via_smtp": False,
            "message": f"[Modo Demo] Contraseña temporal generada para '{to_email}'.",
            "temp_password": temp_password
        }

    # Si NO hay servidor SMTP configurado y no es Demo:
    logger.warning("No se ha configurado SMTP_HOST en las variables de entorno (.env).")
    return {
        "success": False,
        "sent_via_smtp": False,
        "error": "El servidor de correo saliente (SMTP) no está configurado en el archivo .env.",
        "temp_password": temp_password
    }

