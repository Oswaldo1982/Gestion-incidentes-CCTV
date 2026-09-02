import os
import uuid
import datetime
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Depends, Request, Form, UploadFile, File, Query, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine, SessionLocal, get_db
from app.models.base import Base
from app.models.user import User
from app.models.device import Device
from app.models.incident import Incident
from app.models.maintenance import Maintenance
from app.models.event import Event
from app.auth import get_password_hash, authenticate_user, create_access_token, get_current_user_optional
from app.services.license_service import check_license_validity
from app.services.audit_service import create_audit_log
from app.routers import auth, users, license
from app.routers import incidents as incidents_api
from app.routers import maintenance as maintenance_api
from app.routers import events as events_api

# Directorio de subida local para evidencias fotográficas
UPLOAD_DIR = os.path.join("static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Inicializar motor de plantillas Jinja2 y exponer estado de Modo Demo
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["demo_mode"] = settings.DEMO_MODE

# Definición Oficial de las 4 Sedes Territoriales Multi-Tenant
AVAILABLE_SITES: List[Dict[str, Any]] = [
    {
        "id": "san-agustin",
        "name": "San Agustín",
        "full_name": "San Agustín (Huila)",
        "region": "Huila",
        "badge": "Circuito Arqueológico",
        "description": "Parque Arqueológico, Terminal y Red Hospitalaria",
        "icon": "🏛️",
        "cameras_count": 18,
        "status": "Operativo",
        "color": "blue",
        "default_supervisor": "supervisor_sanagustin"
    },
    {
        "id": "san-jose-guaviare",
        "name": "San José del Guaviare",
        "full_name": "San José del Guaviare (Guaviare)",
        "region": "Guaviare",
        "badge": "Central Departamental",
        "description": "Parque Santander, Muelle Fluvial y CAD Central",
        "icon": "🏢",
        "cameras_count": 24,
        "status": "Operativo",
        "color": "emerald",
        "default_supervisor": "supervisor_guaviare"
    },
    {
        "id": "el-retorno",
        "name": "El Retorno",
        "full_name": "El Retorno (Guaviare)",
        "region": "Guaviare",
        "badge": "Circuito Municipal",
        "description": "Control Vía Nacional, Alcaldía y Polideportivo",
        "icon": "🌳",
        "cameras_count": 12,
        "status": "Operativo",
        "color": "amber",
        "default_supervisor": "supervisor_guaviare"
    },
    {
        "id": "calamar",
        "name": "Calamar",
        "full_name": "Calamar (Guaviare)",
        "region": "Guaviare",
        "badge": "Circuito Fluvial",
        "description": "Muelle Río Unilla, Casco Urbano y Puesto de Salud",
        "icon": "🚤",
        "cameras_count": 8,
        "status": "Operativo",
        "color": "purple",
        "default_supervisor": "supervisor_guaviare"
    },
    {
        "id": "sitio-prueba",
        "name": "Sitio de Prueba",
        "full_name": "Sitio de Prueba (Entorno Demo)",
        "region": "Demostración",
        "badge": "Modo Sandbox",
        "description": "Entorno general de demostración y pruebas operativas",
        "icon": "🧪",
        "cameras_count": 8,
        "status": "Operativo",
        "color": "amber",
        "default_supervisor": "supervisor_sanagustin"
    }
]

# Catálogo Integral de Puntos Específicos por Sede
SEDES_CATALOG: List[Dict[str, Any]] = [
    # Sitio de Prueba (Entorno General Demo)
    {
        "id": 100,
        "site_id": "sitio-prueba",
        "name": "Sitio de Prueba - Acceso Principal",
        "municipality": "Sitio de Prueba",
        "address": "Zona Demostración Central",
        "cameras_total": 4,
        "cameras_active": 4,
        "status": "Operativo",
        "contact_person": "Coordinación Demo",
        "phone": "(+57) 300 000 0000",
        "type": "Demostración"
    },
    {
        "id": 101,
        "site_id": "sitio-prueba",
        "name": "Sitio de Prueba - Centro de Control",
        "municipality": "Sitio de Prueba",
        "address": "Sala de Monitoreo Demo",
        "cameras_total": 4,
        "cameras_active": 4,
        "status": "Operativo",
        "contact_person": "Operador Demo",
        "phone": "(+57) 300 000 0001",
        "type": "Demostración"
    },
    # San Agustín (Huila)
    {
        "id": 1,
        "site_id": "san-agustin",
        "name": "San Agustín - Parque Arqueológico",
        "municipality": "San Agustín (Huila)",
        "address": "Vía Parque Arqueológico Km 2.5",
        "cameras_total": 8,
        "cameras_active": 8,
        "status": "Operativo",
        "contact_person": "Punto de Control Turístico",
        "phone": "(+57) 315 789 1234",
        "type": "Turística / Patrimonial"
    },
    {
        "id": 2,
        "site_id": "san-agustin",
        "name": "San Agustín - Terminal de Transportes",
        "municipality": "San Agustín (Huila)",
        "address": "Carrera 11 # 1-45",
        "cameras_total": 6,
        "cameras_active": 6,
        "status": "Operativo",
        "contact_person": "Control Operativo Terminal",
        "phone": "(+57) 318 234 5678",
        "type": "Movilidad"
    },
    {
        "id": 3,
        "site_id": "san-agustin",
        "name": "San Agustín - Hospital Arsenio Repizo",
        "municipality": "San Agustín (Huila)",
        "address": "Carrera 7 # 6-20",
        "cameras_total": 4,
        "cameras_active": 4,
        "status": "Operativo",
        "contact_person": "Vigilancia Médica",
        "phone": "(+57) 310 987 6543",
        "type": "Salud"
    },

    # San José del Guaviare (Guaviare)
    {
        "id": 4,
        "site_id": "san-jose-guaviare",
        "name": "San José - Parque Principal Santander",
        "municipality": "San José del Guaviare (Guaviare)",
        "address": "Calle 8 con Carrera 20",
        "cameras_total": 10,
        "cameras_active": 10,
        "status": "Operativo",
        "contact_person": "Central de Monitoreo CAD",
        "phone": "(+57) 312 345 6789",
        "type": "Seguridad Ciudadana"
    },
    {
        "id": 5,
        "site_id": "san-jose-guaviare",
        "name": "San José - Puerto Fluvial Río Guaviare",
        "municipality": "San José del Guaviare (Guaviare)",
        "address": "Muelle Fluvial Principal",
        "cameras_total": 8,
        "cameras_active": 8,
        "status": "Operativo",
        "contact_person": "Capitanía de Puerto",
        "phone": "(+57) 314 567 8901",
        "type": "Transporte Fluvial"
    },
    {
        "id": 6,
        "site_id": "san-jose-guaviare",
        "name": "San José - Hospital San José y Malecón",
        "municipality": "San José del Guaviare (Guaviare)",
        "address": "Avenida El Retorno # 14-30",
        "cameras_total": 6,
        "cameras_active": 6,
        "status": "Operativo",
        "contact_person": "Control Perimetral",
        "phone": "(+57) 316 789 0123",
        "type": "Salud y Turismo"
    },

    # El Retorno (Guaviare)
    {
        "id": 7,
        "site_id": "el-retorno",
        "name": "El Retorno - Entrada Vía Nacional",
        "municipality": "El Retorno (Guaviare)",
        "address": "Km 1 Vía San José - El Retorno",
        "cameras_total": 6,
        "cameras_active": 6,
        "status": "Operativo",
        "contact_person": "Puesto de Control Entrada",
        "phone": "(+57) 317 890 1234",
        "type": "Control Vial"
    },
    {
        "id": 8,
        "site_id": "el-retorno",
        "name": "El Retorno - Casco Urbano y Alcaldía",
        "municipality": "El Retorno (Guaviare)",
        "address": "Plaza Principal El Retorno",
        "cameras_total": 6,
        "cameras_active": 6,
        "status": "Operativo",
        "contact_person": "Despacho de Seguridad",
        "phone": "(+57) 318 901 2345",
        "type": "Gubernamental"
    },

    # Calamar (Guaviare)
    {
        "id": 9,
        "site_id": "calamar",
        "name": "Calamar - Muelle Fluvial Río Unilla",
        "municipality": "Calamar (Guaviare)",
        "address": "Muelle Río Unilla",
        "cameras_total": 4,
        "cameras_active": 4,
        "status": "Operativo",
        "contact_person": "Control de Navegación",
        "phone": "(+57) 319 012 3456",
        "type": "Fluvial"
    },
    {
        "id": 10,
        "site_id": "calamar",
        "name": "Calamar - Parque Central y Casco Urbano",
        "municipality": "Calamar (Guaviare)",
        "address": "Calle 4 # 3-10, Centro",
        "cameras_total": 4,
        "cameras_active": 4,
        "status": "Operativo",
        "contact_person": "Vigilancia Municipal",
        "phone": "(+57) 320 123 4567",
        "type": "Urbana"
    }
]


def get_current_site(request: Request) -> Dict[str, Any]:
    """Obtiene la sede/tenant activa desde la cookie 'active_site' o query param."""
    site_id = request.query_params.get("site") or request.cookies.get("active_site", "san-agustin")
    site = next((s for s in AVAILABLE_SITES if s["id"] == site_id), AVAILABLE_SITES[0])
    return site


async def save_uploaded_photo(photo: Optional[UploadFile]) -> Optional[str]:
    """Guarda una fotografía de evidencia de forma 100% local en static/uploads/."""
    if not photo or not photo.filename:
        return None
    try:
        content = await photo.read()
        if not content:
            return None
        ext = os.path.splitext(photo.filename)[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
            ext = ".jpg"
        unique_name = f"{uuid.uuid4().hex}{ext}"
        target_path = os.path.join(UPLOAD_DIR, unique_name)
        with open(target_path, "wb") as f:
            f.write(content)
        return f"/static/uploads/{unique_name}"
    except Exception as e:
        print(f"[!] Error al guardar foto local: {e}")
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Crear tablas en la base de datos efectiva si no existen
    from app.models import User, Device, License, AuditLog, Incident, Maintenance, Event  # noqa: ensure all models loaded
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        if settings.DEMO_MODE:
            from app.seeder_demo import seed_demo_data
            print("=" * 65)
            print("[*] [MODO DEMO / SANDBOX (VOLÁTIL EN MEMORIA) ACTIVADO]")
            print(f"[*] Base de datos: {settings.effective_database_url}")
            print("=" * 65)
            seed_demo_data(db)
        else:
            # 2. Sembrar el usuario administrador inicial por defecto si no existe (Modo Normal)
            admin_exists = db.query(User).filter(
                (User.role == "Admin") | (User.username == settings.ADMIN_USERNAME)
            ).first()
            if not admin_exists:
                hashed_pw = get_password_hash(settings.ADMIN_PASSWORD)
                default_admin = User(
                    username=settings.ADMIN_USERNAME,
                    email=settings.ADMIN_EMAIL,
                    hashed_password=hashed_pw,
                    role="Admin",
                    is_active=True
                )
                db.add(default_admin)
                db.commit()
                print(f"[*] Usuario Administrador inicial creado con éxito: {settings.ADMIN_USERNAME}")
            else:
                print(f"[*] Usuario Administrador ya configurado: {admin_exists.username}")

            # 3. Sembrar licencia activa si no existe
            license_active = db.query(License).filter(License.is_active == True).first()
            if not license_active:
                from app.services.license_service import generate_dev_license
                dev_license_key = generate_dev_license(expires_days=3650, max_users=100)
                db.add(License(license_key=dev_license_key, is_active=True))
                db.commit()
                print("[*] Licencia de sistema sembrada y activada con éxito.")
    except Exception as e:
        print(f"[!] Error durante la inicialización en lifespan: {e}")
    finally:
        db.close()
        
    yield


app = FastAPI(
    title="Aplicación Web de Soporte y Mantenimiento de Incidentes CCTV",
    description="Sistema de gestión de incidentes, control de mantenimientos y roles con licenciamiento multi-sede.",
    version="2.8.0",
    lifespan=lifespan
)

# Montar archivos estáticos para servir fotos locales
app.mount("/static", StaticFiles(directory="static"), name="static")


# ----------------- 1. Landpage / Portal de Entrada (/) -----------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing_portal(
    request: Request,
    current_user: User = Depends(get_current_user_optional)
):
    """Portal de inicio ejecutivo con acceso guiado por sede o entorno de demostración."""
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={"current_user": current_user, "available_sites": AVAILABLE_SITES}
    )


# ----------------- 2. Rutas de Autenticación Unificada (Single-Screen Login) -----------------

@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(
    request: Request,
    site: Optional[str] = Query("san-agustin"),
    error: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_optional)
):
    """Renderiza el formulario único de inicio de sesión institucional con selector de sede y rol."""
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    clean_site = site if any(s["id"] == site for s in AVAILABLE_SITES) else "san-agustin"
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "current_user": None,
            "selected_site": clean_site,
            "error": error,
            "available_sites": AVAILABLE_SITES,
            "demo_mode": False
        }
    )


@app.get("/demo/login", response_class=HTMLResponse, include_in_schema=False)
def demo_login_page(
    request: Request,
    site: Optional[str] = Query("san-agustin"),
    error: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_optional)
):
    """Acceso al formulario único de inicio de sesión en Modo Demostración volátil."""
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

    clean_site = site if any(s["id"] == site for s in AVAILABLE_SITES) else "san-agustin"
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "current_user": None,
            "selected_site": clean_site,
            "error": error,
            "available_sites": AVAILABLE_SITES,
            "demo_mode": True
        }
    )


@app.post("/login", response_class=HTMLResponse, include_in_schema=False)
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    site_id: str = Form("san-agustin"),
    role_type: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Procesa el inicio de sesión institucional y redirige DIRECTAMENTE al Dashboard de la sede."""
    clean_site_id = site_id if any(s["id"] == site_id for s in AVAILABLE_SITES) else "san-agustin"
    user = authenticate_user(db, username=username.strip(), password=password)
    
    if not user:
        create_audit_log(
            db,
            user_id=None,
            username=username,
            action="WEB_LOGIN_FAILED",
            details={"reason": "Credenciales inválidas"}
        )
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "current_user": None,
                "selected_site": clean_site_id,
                "username": username,
                "error": "Usuario o contraseña incorrectos.",
                "available_sites": AVAILABLE_SITES,
                "demo_mode": settings.DEMO_MODE
            },
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    if not user.is_active:
        create_audit_log(
            db,
            user_id=user.id,
            username=user.username,
            action="WEB_LOGIN_FAILED",
            details={"reason": "Cuenta desactivada"}
        )
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "current_user": None,
                "selected_site": clean_site_id,
                "username": username,
                "error": "Esta cuenta se encuentra desactivada.",
                "available_sites": AVAILABLE_SITES,
                "demo_mode": settings.DEMO_MODE
            },
            status_code=status.HTTP_403_FORBIDDEN
        )

    # Validar licencia activa para usuarios sin rol Admin
    if user.role != "Admin":
        is_valid, reason = check_license_validity(db)
        if not is_valid:
            create_audit_log(
                db,
                user_id=user.id,
                username=user.username,
                action="WEB_LOGIN_FAILED",
                details={"reason": f"Falta de licencia: {reason}"}
            )
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "current_user": None,
                    "selected_site": clean_site_id,
                    "username": username,
                    "error": f"Acceso restringido por licencia: {reason}",
                    "available_sites": AVAILABLE_SITES,
                    "demo_mode": settings.DEMO_MODE
                },
                status_code=status.HTTP_402_PAYMENT_REQUIRED
            )

    # Generar token JWT
    access_token = create_access_token(data={"sub": user.username})

    create_audit_log(
        db,
        user_id=user.id,
        username=user.username,
        action="WEB_LOGIN_SUCCESS",
        details={"role": user.role, "site_id": clean_site_id}
    )

    # Redireccionar directamente al Dashboard del municipio seleccionado
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax"
    )
    response.set_cookie(
        key="active_site",
        value=clean_site_id,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=False,
        samesite="lax"
    )
    return response


@app.post("/demo/quick-login", response_class=HTMLResponse, include_in_schema=False)
def demo_quick_login(
    request: Request,
    demo_role: str = Form("admin"),
    db: Session = Depends(get_db)
):
    """
    Ingreso directo y cambio de rol instantáneo en el 'Sitio de Prueba'.
    Autentica el rol solicitado y otorga acceso completo con todas las funciones reales.
    """
    clean_site_id = "sitio-prueba"
    target_username = "admin"

    if demo_role == "supervisor":
        target_username = "supervisor"
    elif demo_role == "mantenimiento":
        target_username = "mantenimiento_cctv"

    user = db.query(User).filter(User.username == target_username).first()
    if not user:
        from app.seeder_demo import seed_demo_data
        try:
            seed_demo_data(db)
        except Exception as e:
            print(f"[!] Error al sembrar datos demo: {e}")
        user = db.query(User).filter(User.username == target_username).first()
        if not user:
            user = db.query(User).filter(User.role == "Supervisor" if demo_role == "supervisor" else "Admin").first()

    access_token = create_access_token(data={"sub": user.username})

    create_audit_log(
        db,
        user_id=user.id,
        username=user.username,
        action="DEMO_ROLE_SWITCH",
        details={"role": user.role, "site_id": clean_site_id}
    )

    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax"
    )
    response.set_cookie(
        key="active_site",
        value=clean_site_id,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=False,
        samesite="lax"
    )
    response.set_cookie(
        key="is_demo_session",
        value="true",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=False,
        samesite="lax"
    )
    return response


# Rutas de compatibilidad redirigidas limpiamente a /login
@app.get("/select-site", include_in_schema=False)
@app.get("/select-location", include_in_schema=False)
def redirect_to_login(site: Optional[str] = Query(None)):
    target = f"/login?site={site}" if site else "/login"
    return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)


@app.get("/site/{site_id}/login", include_in_schema=False)
def redirect_site_login(site_id: str):
    clean_site_id = site_id if any(s["id"] == site_id for s in AVAILABLE_SITES) else "san-agustin"
    return RedirectResponse(url=f"/login?site={clean_site_id}", status_code=status.HTTP_302_FOUND)


@app.get("/logout", include_in_schema=False)
@app.get("/demo/exit", include_in_schema=False)
def logout(
    request: Request,
    db: Session = Depends(get_db)
):
    """Cierra la sesión. Si la sesión era de Demo, borra y restablece todos los datos volátiles en memoria."""
    is_demo = request.cookies.get("is_demo_session") == "true" or settings.DEMO_MODE
    if is_demo:
        try:
            from app.seeder_demo import seed_demo_data
            seed_demo_data(db)
            print("[*] [Modo Demo] Sesión finalizada: todos los datos creados/modificados han sido borrados de memoria.")
        except Exception as e:
            print(f"[!] Error al limpiar datos de demo al salir: {e}")

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="is_demo_session")
    return response


@app.get("/switch-location/{site_id}", include_in_schema=False)
@app.get("/switch-site/{site_id}", include_in_schema=False)
def switch_location_quick(site_id: str, request: Request):
    """Para ingresar a otro sitio territorial se debe cerrar sesión y volver a ingresar credenciales."""
    return RedirectResponse(url="/logout", status_code=status.HTTP_303_SEE_OTHER)


# ----------------- 5. Panel Principal (Dashboard con Filtrado por Sede) -----------------

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Panel Principal de Control y Monitoreo filtrado por el municipio activo."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request)
    site_id = current_site["id"]

    # Catálogo de puntos del municipio activo
    display_sedes = [s for s in SEDES_CATALOG if s.get("site_id") == site_id]
    if not display_sedes:
        display_sedes = [s for s in SEDES_CATALOG if s.get("site_id") == "san-agustin"]

    # Filtro de base de datos estricto por el municipio activo
    site_filter_pattern = f"%{current_site['name']}%"
    incidents_query = db.query(Incident).filter(Incident.sede.ilike(site_filter_pattern))
    maintenances_query = db.query(Maintenance).filter(Maintenance.sede.ilike(site_filter_pattern))
    devices_query = db.query(Device).filter(Device.sede.ilike(site_filter_pattern))

    open_incidents = incidents_query.filter(Incident.status != "Cerrado").count()
    critical_incidents = incidents_query.filter(
        Incident.status != "Cerrado",
        Incident.priority == "Crítica"
    ).count()
    total_incidents = incidents_query.count()

    pending_maintenances = maintenances_query.filter(
        Maintenance.status.in_(["Programado", "En Ejecución"])
    ).count()
    completed_maintenances = maintenances_query.filter(
        Maintenance.status == "Completado"
    ).count()
    total_maintenances = maintenances_query.count()

    cameras_total = sum(s["cameras_total"] for s in display_sedes)
    cameras_active = sum(s["cameras_active"] for s in display_sedes)

    recent_incidents = incidents_query.order_by(Incident.created_at.desc()).limit(5).all()
    recent_maintenances = maintenances_query.order_by(Maintenance.scheduled_date.asc()).limit(5).all()

    metrics = {
        "open_incidents": open_incidents,
        "critical_incidents": critical_incidents,
        "total_incidents": total_incidents,
        "pending_maintenances": pending_maintenances,
        "completed_maintenances": completed_maintenances,
        "total_maintenances": total_maintenances,
        "cameras_total": cameras_total,
        "cameras_active": cameras_active
    }

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "current_user": current_user,
            "current_site": current_site,
            "available_sites": AVAILABLE_SITES,
            "active_page": "dashboard",
            "selected_sede": current_site["full_name"],
            "metrics": metrics,
            "sedes": display_sedes,
            "all_sedes": SEDES_CATALOG,
            "recent_incidents": recent_incidents,
            "recent_maintenances": recent_maintenances
        }
    )


# ----------------- 6. Gestión de Inventario de Equipos (Filtrado por Sede) -----------------

@app.get("/devices", response_class=HTMLResponse)
@app.get("/equipment", response_class=HTMLResponse)
def devices_view(
    request: Request,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Vista web de inventario de equipos filtrada por la sede activa."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request)
    site_filter_pattern = f"%{current_site['name']}%"

    devices_list = db.query(Device).filter(
        Device.sede.ilike(site_filter_pattern)
    ).order_by(Device.created_at.desc()).all()

    site_sedes = [s for s in SEDES_CATALOG if s.get("site_id") == current_site["id"]]

    return templates.TemplateResponse(
        request=request,
        name="devices.html",
        context={
            "current_user": current_user,
            "current_site": current_site,
            "available_sites": AVAILABLE_SITES,
            "active_page": "devices",
            "devices": devices_list,
            "sedes": site_sedes if site_sedes else SEDES_CATALOG
        }
    )


@app.post("/devices")
def create_device_web(
    request: Request,
    name: str = Form(...),
    device_type: str = Form(...),
    sede: Optional[str] = Form(None),
    location_detail: Optional[str] = Form(None),
    brand: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    serial_number: Optional[str] = Form(None),
    ip_address: Optional[str] = Form(None),
    device_status: str = Form("Operativo", alias="status"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Crea un nuevo equipo en el inventario del municipio activo."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request)
    assigned_sede = sede if sede and sede.strip() else current_site["full_name"]

    new_device = Device(
        name=name.strip(),
        device_type=device_type,
        sede=assigned_sede,
        location_detail=location_detail.strip() if location_detail else None,
        brand=brand.strip() if brand else None,
        model=model.strip() if model else None,
        serial_number=serial_number.strip() if serial_number else None,
        ip_address=ip_address.strip() if ip_address else None,
        status=device_status
    )
    db.add(new_device)
    db.commit()
    db.refresh(new_device)

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="DEVICE_CREATED",
        details={"device_id": new_device.id, "name": new_device.name, "type": device_type, "sede": assigned_sede}
    )
    db.commit()

    return RedirectResponse(url="/devices", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/devices/{device_id}/status")
def update_device_status_web(
    device_id: int,
    new_status: str = Form(..., alias="status"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Actualiza el estado operativo de un equipo."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        return RedirectResponse(url="/devices", status_code=status.HTTP_303_SEE_OTHER)

    old_status = device.status
    if old_status != new_status:
        device.status = new_status
        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="DEVICE_STATUS_CHANGE",
            details={"device_id": device.id, "old_status": old_status, "new_status": new_status}
        )
        db.commit()

    return RedirectResponse(url="/devices", status_code=status.HTTP_303_SEE_OTHER)


# ----------------- 7. Gestión de Usuarios -----------------

@app.get("/users", response_class=HTMLResponse)
def users_view(
    request: Request,
    msg: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Vista web de administración de usuarios institucionales."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)
    
    if current_user.role not in ["Admin", "Supervisor"]:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request)
    users_list = db.query(User).order_by(User.created_at.desc()).all()

    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={
            "current_user": current_user,
            "current_site": current_site,
            "available_sites": AVAILABLE_SITES,
            "active_page": "users",
            "users": users_list,
            "msg": msg,
            "error": error
        }
    )


@app.post("/users")
def create_user_web(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("Operario"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Crea una nueva cuenta de usuario institucional."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.role != "Admin":
        return RedirectResponse(url="/users?error=Solo+un+administrador+puede+crear+cuentas+de+usuario", status_code=status.HTTP_303_SEE_OTHER)

    clean_username = username.strip()
    clean_email = email.strip().lower()

    if db.query(User).filter(User.username == clean_username).first():
        return RedirectResponse(url="/users?error=El+nombre+de+usuario+ya+se+encuentra+registrado", status_code=status.HTTP_303_SEE_OTHER)

    if db.query(User).filter(User.email == clean_email).first():
        return RedirectResponse(url="/users?error=El+correo+electrónico+ya+está+asociado+a+otra+cuenta", status_code=status.HTTP_303_SEE_OTHER)

    hashed_pw = get_password_hash(password)
    new_user = User(
        username=clean_username,
        email=clean_email,
        hashed_password=hashed_pw,
        role=role,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="USER_CREATED_WEB",
        details={"created_user_id": new_user.id, "created_username": new_user.username, "role": role}
    )
    db.commit()

    return RedirectResponse(url=f"/users?msg=Cuenta+de+usuario+{clean_username}+creada+exitosamente", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/users/{user_id}/toggle-active")
def toggle_user_active_web(
    user_id: int,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Activa o desactiva una cuenta de usuario."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.role != "Admin":
        return RedirectResponse(url="/users?error=No+tienes+permisos+para+modificar+usuarios", status_code=status.HTTP_303_SEE_OTHER)

    if user_id == current_user.id:
        return RedirectResponse(url="/users?error=No+puedes+desactivar+tu+propia+cuenta+de+administrador", status_code=status.HTTP_303_SEE_OTHER)

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        return RedirectResponse(url="/users?error=Usuario+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)

    target_user.is_active = not target_user.is_active
    new_state_label = "activada" if target_user.is_active else "desactivada"

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="USER_STATUS_TOGGLED",
        details={"target_user_id": target_user.id, "target_username": target_user.username, "is_active": target_user.is_active}
    )
    db.commit()

    return RedirectResponse(url=f"/users?msg=La+cuenta+de+{target_user.username}+ha+sido+{new_state_label}", status_code=status.HTTP_303_SEE_OTHER)


# ----------------- 8. Rutas Operativas: Incidentes (Filtrado por Sede) -----------------

@app.get("/incidents", response_class=HTMLResponse)
def incidents_view(
    request: Request,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Vista web operativa de incidentes filtrada por el municipio activo."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request)
    site_filter_pattern = f"%{current_site['name']}%"

    incidents_list = db.query(Incident).filter(
        Incident.sede.ilike(site_filter_pattern)
    ).order_by(Incident.created_at.desc()).all()

    devices_list = db.query(Device).filter(
        Device.sede.ilike(site_filter_pattern)
    ).order_by(Device.name.asc()).all()

    site_sedes = [s for s in SEDES_CATALOG if s.get("site_id") == current_site["id"]]

    return templates.TemplateResponse(
        request=request,
        name="incidents.html",
        context={
            "current_user": current_user,
            "current_site": current_site,
            "available_sites": AVAILABLE_SITES,
            "active_page": "incidents",
            "incidents": incidents_list,
            "devices": devices_list,
            "sedes": site_sedes if site_sedes else SEDES_CATALOG
        }
    )


@app.post("/incidents")
async def create_incident_web(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    priority: str = Form("Media"),
    sede: Optional[str] = Form(None),
    device_id: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Procesa el reporte de un nuevo incidente en el municipio activo."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request)
    assigned_sede = sede if sede and sede.strip() else current_site["full_name"]
    image_path = await save_uploaded_photo(photo)
    parsed_device_id = int(device_id) if device_id and device_id.strip() else None

    new_incident = Incident(
        title=title.strip(),
        description=description.strip(),
        priority=priority,
        sede=assigned_sede,
        device_id=parsed_device_id,
        image_path=image_path,
        status="Abierto",
        created_by_id=current_user.id
    )
    db.add(new_incident)
    db.commit()
    db.refresh(new_incident)

    creation_event = Event(
        incident_id=new_incident.id,
        user_id=current_user.id,
        event_type="CREATION",
        description=f"Incidente reportado en {assigned_sede} por {current_user.username}."
    )
    db.add(creation_event)

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="INCIDENT_CREATED_WEB",
        details={"incident_id": new_incident.id, "title": new_incident.title, "sede": assigned_sede, "device_id": parsed_device_id}
    )
    db.commit()

    return RedirectResponse(url="/incidents", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/incidents/{incident_id}/status")
def update_incident_status_web(
    incident_id: int,
    new_status: str = Form(..., alias="status"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Actualiza el estado de un incidente."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        return RedirectResponse(url="/incidents", status_code=status.HTTP_303_SEE_OTHER)

    if new_status == "Cerrado" and current_user.role not in ["Admin", "Supervisor"]:
        return RedirectResponse(url="/incidents", status_code=status.HTTP_303_SEE_OTHER)

    old_status = incident.status
    if old_status != new_status:
        incident.status = new_status
        incident.updated_at = datetime.datetime.utcnow()
        
        db.add(Event(
            incident_id=incident.id,
            user_id=current_user.id,
            event_type="STATUS_CHANGE",
            description=f"Estado cambiado de '{old_status}' a '{new_status}' por {current_user.username}."
        ))

        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="INCIDENT_STATUS_CHANGE",
            details={"incident_id": incident.id, "old_status": old_status, "new_status": new_status}
        )
        db.commit()

    return RedirectResponse(url="/incidents", status_code=status.HTTP_303_SEE_OTHER)


# ----------------- 9. Rutas Operativas: Mantenimientos (Filtrado por Sede) -----------------

@app.get("/maintenance", response_class=HTMLResponse)
@app.get("/maintenances", response_class=HTMLResponse)
def maintenance_view(
    request: Request,
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Vista web operativa de mantenimientos filtrada por el municipio activo."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request)
    site_filter_pattern = f"%{current_site['name']}%"

    maintenances_list = db.query(Maintenance).filter(
        Maintenance.sede.ilike(site_filter_pattern)
    ).order_by(Maintenance.scheduled_date.desc()).all()

    active_incidents = db.query(Incident).filter(
        Incident.sede.ilike(site_filter_pattern),
        Incident.status != "Cerrado"
    ).all()

    devices_list = db.query(Device).filter(
        Device.sede.ilike(site_filter_pattern)
    ).order_by(Device.name.asc()).all()

    site_sedes = [s for s in SEDES_CATALOG if s.get("site_id") == current_site["id"]]

    return templates.TemplateResponse(
        request=request,
        name="maintenances.html",
        context={
            "current_user": current_user,
            "current_site": current_site,
            "available_sites": AVAILABLE_SITES,
            "active_page": "maintenance",
            "maintenances": maintenances_list,
            "active_incidents": active_incidents,
            "devices": devices_list,
            "sedes": site_sedes if site_sedes else SEDES_CATALOG
        }
    )


@app.post("/maintenance")
@app.post("/maintenances")
async def create_maintenance_web(
    request: Request,
    type: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    scheduled_date: str = Form(...),
    sede: Optional[str] = Form(None),
    device_id: Optional[str] = Form(None),
    incident_id: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Procesa la programación de un nuevo mantenimiento en el municipio activo."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request)
    assigned_sede = sede if sede and sede.strip() else current_site["full_name"]
    image_path = await save_uploaded_photo(photo)

    try:
        parsed_date = datetime.datetime.fromisoformat(scheduled_date)
    except Exception:
        parsed_date = datetime.datetime.utcnow()

    parsed_incident_id = int(incident_id) if incident_id and incident_id.strip() else None
    parsed_device_id = int(device_id) if device_id and device_id.strip() else None

    new_maint = Maintenance(
        type=type,
        title=title.strip(),
        description=description.strip(),
        scheduled_date=parsed_date,
        sede=assigned_sede,
        device_id=parsed_device_id,
        incident_id=parsed_incident_id,
        image_path=image_path,
        status="Programado",
        created_by_id=current_user.id
    )
    db.add(new_maint)
    db.commit()
    db.refresh(new_maint)

    db.add(Event(
        maintenance_id=new_maint.id,
        user_id=current_user.id,
        event_type="CREATION",
        description=f"Mantenimiento programado como {type} en {assigned_sede} por {current_user.username}."
    ))

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="MAINTENANCE_CREATED_WEB",
        details={"maintenance_id": new_maint.id, "title": new_maint.title, "sede": assigned_sede, "device_id": parsed_device_id}
    )
    db.commit()

    return RedirectResponse(url="/maintenance", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/maintenance/{maintenance_id}/status")
def update_maintenance_status_web(
    maintenance_id: int,
    new_status: str = Form(..., alias="status"),
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Actualiza el estado de un mantenimiento."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    maint = db.query(Maintenance).filter(Maintenance.id == maintenance_id).first()
    if not maint:
        return RedirectResponse(url="/maintenance", status_code=status.HTTP_303_SEE_OTHER)

    old_status = maint.status
    if old_status != new_status:
        maint.status = new_status
        if new_status == "Completado":
            maint.completed_date = datetime.datetime.utcnow()

        db.add(Event(
            maintenance_id=maint.id,
            user_id=current_user.id,
            event_type="STATUS_CHANGE",
            description=f"Estado de mantenimiento cambiado a '{new_status}' por {current_user.username}."
        ))

        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="MAINTENANCE_STATUS_CHANGE",
            details={"maintenance_id": maint.id, "old_status": old_status, "new_status": new_status}
        )
        db.commit()

    return RedirectResponse(url="/maintenance", status_code=status.HTTP_303_SEE_OTHER)


# ----------------- Routers de la API REST -----------------
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(license.router)
app.include_router(incidents_api.router)
app.include_router(maintenance_api.router)
app.include_router(events_api.router)
