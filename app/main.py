import os
import calendar
import json
import uuid
import datetime
import logging
import urllib.parse
import random
import string
import re
import dns.resolver
from contextlib import asynccontextmanager

from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Depends, Request, Form, UploadFile, File, Query, status, HTTPException, WebSocket
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import or_, and_, func, case, select
from sqlalchemy.orm import Session

logger = logging.getLogger("cctv_main")


from app.config import settings
from app.database import engine, SessionLocal, get_db
from app.models.base import Base
from app.models.user import User
from app.models.device import Device
from app.models.incident import Incident
from app.models.maintenance import Maintenance
from app.models.event import Event
from app.models.license import License
from app.models.site import Site
from app.auth import get_password_hash, authenticate_user, create_access_token, get_current_user_optional, verify_password, is_password_already_in_use
from app.utils.timezone import get_local_now
from app.services.license_service import check_license_validity, get_active_license_payload, activate_license, verify_user_limit
from app.services.audit_service import create_audit_log
from app.services.realtime_service import realtime_manager
from app.services.email_service import send_temporary_password_email
from app.services.report_service import get_reports_statistics, generate_cctv_pdf_report, generate_validation_conformity_pdf, generate_cctv_executive_pdf_report
from app.routers import auth, users, license
from app.routers import sites as sites_api
from app.routers import incidents as incidents_api
from app.routers import maintenance as maintenance_api
from app.routers import events as events_api

# Directorio de subida local para evidencias fotográficas
UPLOAD_DIR = settings.UPLOAD_DIR
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.join("static", "uploads"), exist_ok=True)

# Inicializar motor de plantillas Jinja2 y exponer estado de Modo Demo
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["demo_mode"] = settings.DEMO_MODE

# Definición Oficial de Sedes Territoriales Multi-Tenant
# Por directriz operativa inicial, San Agustín es la única sede real activa para producción.
# El Sitio de Prueba se reserva para el Entorno Demo / Sandbox.
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

# Sedes reservadas para fases futuras de expansión territorial:
EXPANSION_SITES_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "san-jose-guaviare",
        "name": "San José del Guaviare",
        "full_name": "San José del Guaviare (Guaviare)",
        "region": "Guaviare",
        "badge": "Central Departamental",
        "description": "Parque Santander, Muelle Fluvial y CAD Central",
        "icon": "🏢",
        "cameras_count": 24,
        "status": "Inactivo",
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
        "status": "Inactivo",
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
        "status": "Inactivo",
        "color": "purple",
        "default_supervisor": "supervisor_guaviare"
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


def get_available_sites(db: Optional[Session] = None, active_only: bool = True) -> List[Dict[str, Any]]:
    """Obtiene las sedes territoriales dinámicas desde la tabla relacional 'sites' (SQLModel)."""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        query = db.query(Site)
        if active_only:
            query = query.filter(Site.is_active == True)
        sites = query.order_by(Site.name.asc()).all()
        if sites:
            return [s.to_dict() for s in sites]
        return AVAILABLE_SITES
    except Exception as e:
        logger.warning(f"Aviso al consultar sedes dinámicas en BD: {e}")
        return AVAILABLE_SITES
    finally:
        if should_close:
            db.close()


def get_current_site(request: Request, db: Optional[Session] = None) -> Dict[str, Any]:
    """Obtiene la sede/tenant activa desde la cookie 'active_site' o query param consultando la BD dinámicamente."""
    site_id = request.query_params.get("site") or request.cookies.get("active_site", "san-agustin")
    sites = get_available_sites(db=db, active_only=False)
    site = next((s for s in sites if s["id"] == site_id), sites[0] if sites else AVAILABLE_SITES[0])
    return site


from app.services.site_sync_service import get_canonical_site_filter

def get_site_filter_conditions(model_cls, current_site: Dict[str, Any]):
    """Construye condiciones OR para filtrar registros por la sede/municipio activo con total aislamiento y homogeneidad."""
    return get_canonical_site_filter(model_cls, current_site)


def check_site_access_or_redirect(
    request: Request,
    current_user: Optional[User],
    current_site: Dict[str, Any],
    db: Session
) -> Optional[RedirectResponse]:
    """
    Verifica que el sitio actual tenga permiso de operar:
    - En DEV_MODE retorna None (acceso libre total para el desarrollador).
    - Registra el timestamp de primer acceso del sitio (iniciando reloj de 24h).
    - Si el sitio está bloqueado por falta de contraseña (Año 1 tras 24h, o Año 2/3 tras 365 días):
      - Si es Administrador: redirige a /license?site={site_id}&error={mensaje}.
      - Si no es Administrador: redirige a /select-site?error={mensaje}.
    - Si el sitio está en período de gracia (24h) o activo: retorna None (acceso permitido).
    """
    if getattr(settings, "SUSPEND_SITE_LICENSING", True) or settings.DEV_MODE:
        return None

    site_id = current_site.get("id", "san-agustin")
    from app.services.site_license_service import record_site_first_access, get_site_license_status
    record_site_first_access(db, site_id)
    lic_status = get_site_license_status(db, site_id)

    if not lic_status.get("is_allowed", True):
        msg = urllib.parse.quote_plus(lic_status.get("message", "Licencia requerida"))
        if current_user and current_user.role == "Admin":
            return RedirectResponse(url=f"/license?site={site_id}&error={msg}", status_code=status.HTTP_303_SEE_OTHER)
        else:
            return RedirectResponse(url=f"/select-site?error={msg}", status_code=status.HTTP_303_SEE_OTHER)

    return None


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
    # 0. Creación automática de directorios al arrancar (volumen persistente y subidas)
    upload_dir = getattr(settings, "UPLOAD_DIR", os.path.join("static", "uploads"))
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(os.path.join("static", "uploads"), exist_ok=True)

    # Si la base de datos es SQLite basada en disco persistente, verificar y crear su directorio contenedor
    db_url = settings.effective_database_url
    if db_url.startswith("sqlite:///") and ":memory:" not in db_url:
        db_file_path = db_url.replace("sqlite:///", "")
        db_folder = os.path.dirname(db_file_path)
        if db_folder:
            os.makedirs(db_folder, exist_ok=True)

    # 1. Crear tablas en la base de datos efectiva si no existen y sincronizar esquema
    from app.database import ensure_database_schema
    Base.metadata.create_all(bind=engine)
    ensure_database_schema(engine)
    
    db = SessionLocal()
    try:
        # Sembrar sedes territoriales dinámicas en la tabla 'sites' si está vacía
        try:
            if db.query(Site).count() == 0:
                for s_data in AVAILABLE_SITES:
                    db.add(Site(
                        id=s_data["id"],
                        name=s_data["name"],
                        full_name=s_data["full_name"],
                        region=s_data.get("region", ""),
                        badge=s_data.get("badge", ""),
                        description=s_data.get("description", ""),
                        icon=s_data.get("icon", "🏛️"),
                        cameras_count=s_data.get("cameras_count", 0),
                        status=s_data.get("status", "Operativo"),
                        color=s_data.get("color", "blue"),
                        default_supervisor=s_data.get("default_supervisor", ""),
                        is_active=True
                    ))
                db.commit()
                print("[*] Sedes territoriales iniciales migradas y guardadas en la base de datos relacional.")
        except Exception as e_site:
            print(f"[!] Aviso al sincronizar sedes iniciales: {e_site}")

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
                    full_name="Administrador Principal",
                    document_id="0000000000",
                    assigned_site="Todas las Sedes",
                    hashed_password=hashed_pw,
                    role="Admin",
                    is_active=True,
                    must_change_password=False
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
                print("[*] Licencia de sistema sembrada y activada con éxito.")

        # 4. Sincronización permanente multi-sede (garantiza homogeneidad en las 4 sedes)
        try:
            from app.services.site_sync_service import ensure_all_sites_synchronized
            sync_res = ensure_all_sites_synchronized(db)
            print(f"[*] Sincronización multi-sede ejecutada: {sync_res}")
        except Exception as e_sync:
            print(f"[!] Error en sincronización multi-sede: {e_sync}")

        # 5. Inicialización de Licenciamiento por Sitio (4 sitios, 3 años, 12 llaves y PDFs)
        try:
            from app.services.site_license_service import ensure_all_site_licenses_initialized
            lic_res = ensure_all_site_licenses_initialized(db)
            print(f"[*] Licenciamiento multi-sede inicializado: {lic_res}")
        except Exception as e_lic:
            print(f"[!] Error al inicializar licenciamiento por sitio: {e_lic}")

        # 6. Inicialización de firmas digitales institucionales
        try:
            from app.utils.signature import ensure_seed_signatures
            ensure_seed_signatures(db)
            print("[*] Firmas digitales de usuarios inicializadas.")
        except Exception as e_sig:
            print(f"[!] Error al inicializar firmas digitales: {e_sig}")
    except Exception as e:
        print(f"[!] Error durante la inicialización en lifespan: {e}")
    finally:
        db.close()

    realtime_manager.bind_loop()
    yield


app = FastAPI(
    title="Aplicación Web de Soporte y Mantenimiento de Incidentes CCTV",
    description="Sistema de gestión de incidentes, control de mantenimientos y roles con licenciamiento multi-sede.",
    version="2.8.0",
    lifespan=lifespan
)

# Endpoint de chequeo de salud (Health Check) para Railway y orquestadores en la nube
@app.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
def health_check():
    """Endpoint de comprobación de salud para Railway y monitorización de infraestructura."""
    return {
        "status": "healthy",
        "service": "cctv-incidentes"
    }

# Montar archivos estáticos para servir fotos y evidencias locales
if os.path.abspath(settings.UPLOAD_DIR) != os.path.abspath(os.path.join("static", "uploads")):
    app.mount("/static/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="persistent_uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.middleware("http")
async def add_no_cache_headers_for_html(request: Request, call_next):
    """
    Garantiza que las vistas HTML dinámicas nunca se almacenen en caché del navegador (BFCache / disk cache),
    y emite notificaciones en tiempo real tras operaciones de modificación (POST/PUT/PATCH/DELETE).
    """
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        path = request.url.path
        excluded_paths = ("/login", "/logout", "/demo/quick-login", "/demo/exit", "/forgot-password", "/change-credentials")
        if not any(path.startswith(ep) for ep in excluded_paths) and response.status_code < 400:
            realtime_manager.notify(
                event_type="resource_mutated",
                payload={"method": request.method, "path": path}
            )

    # Renovación deslizante de sesión por actividad (20 minutos de inactividad para todos los roles)
    path = request.url.path
    is_realtime_bg = (
        path.startswith(("/api/realtime", "/ws/", "/static", "/logout", "/login", "/demo/exit"))
        or request.headers.get("X-Realtime-Sync") == "1"
    )
    if not is_realtime_bg and "set-cookie" not in (k.lower() for k in response.headers.keys()):
        cookie_token = request.cookies.get("access_token")
        if cookie_token:
            raw_token = cookie_token[7:] if cookie_token.startswith("Bearer ") else cookie_token
            try:
                from jose import jwt as _jwt
                payload = _jwt.decode(raw_token, settings.SECRET_KEY, algorithms=["HS256"])
                sub = payload.get("sub")
                if sub:
                    refreshed_token = create_access_token(data={"sub": sub})
                    response.set_cookie(
                        key="access_token",
                        value=f"Bearer {refreshed_token}",
                        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                        httponly=True,
                        samesite="lax"
                    )
            except Exception:
                pass

    return response


# ----------------- 0. Endpoints de Sincronización en Tiempo Real (SSE y WebSocket) -----------------

@app.get("/api/realtime/stream", include_in_schema=False)
async def realtime_sse_endpoint(request: Request):
    """Stream Server-Sent Events (SSE) para actualización reactiva del DOM en tiempo real."""
    return realtime_manager.create_sse_response(request)


@app.websocket("/ws/updates")
async def realtime_ws_endpoint(websocket: WebSocket):
    """Canal WebSocket para actualización reactiva en tiempo real."""
    await realtime_manager.handle_websocket(websocket)


# ----------------- 1. Landpage / Portal de Entrada (/) -----------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing_portal(
    request: Request,
    msg: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Portal de inicio ejecutivo con acceso guiado por sede o entorno de demostración."""
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={"current_user": current_user, "available_sites": AVAILABLE_SITES, "msg": msg, "error": error}
    )


# ----------------- 2. Rutas de Autenticación Unificada (Single-Screen Login) -----------------

@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(
    request: Request,
    site: Optional[str] = Query("san-agustin"),
    error: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional)
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
    current_user: Optional[User] = Depends(get_current_user_optional)
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

def check_email_mx_records(email: str) -> tuple[bool, str]:
    """
    Verifica que el formato del correo sea válido y consulta los registros DNS MX del dominio
    para comprobar si el servidor de correo realmente existe y puede recibir mensajes.
    """
    clean_email = email.strip().lower()
    email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(email_pattern, clean_email):
        return False, "El formato del correo electrónico no es válido."
    
    parts = clean_email.split("@")
    if len(parts) != 2:
        return False, "Formato de correo electrónico inválido."
    domain = parts[1].strip()

    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = 3.5
        resolver.lifetime = 3.5
        try:
            records = resolver.resolve(domain, 'MX')
            if records and len(records) > 0:
                return True, ""
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            try:
                a_records = resolver.resolve(domain, 'A')
                if a_records and len(a_records) > 0:
                    return True, ""
            except Exception:
                return False, f"El dominio '@{domain}' no existe o no cuenta con servidores de correo (registros MX) activos."
        except Exception as e:
            if "NXDOMAIN" in str(e) or "does not exist" in str(e):
                return False, f"El dominio '@{domain}' no existe en los registros globales de Internet."
            return True, ""
    except Exception as e:
        if "NXDOMAIN" in str(e) or "does not exist" in str(e):
            return False, f"El dominio '@{domain}' no existe en los registros globales de Internet."
        return True, ""
    return True, ""


def generate_temp_password() -> str:
    """Genera una contraseña temporal segura aleatoria y única de 8 caracteres alfanuméricos."""
    upper = random.choice(string.ascii_uppercase)
    lower = "".join(random.choices(string.ascii_lowercase, k=4))
    digits = "".join(random.choices(string.digits, k=3))
    chars = list(upper + lower + digits)
    random.shuffle(chars)
    return "".join(chars) + "*"

@app.post("/login", response_class=HTMLResponse, include_in_schema=False)
def login_post(
    request: Request,
    username: str = Form(...),
    password: Optional[str] = Form(""),
    site_id: str = Form("san-agustin"),
    role_type: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Procesa el inicio de sesión institucional y valida obligatoriamente la correspondencia de Sitio, Rol y Credenciales."""
    clean_site_id = site_id if any(s["id"] == site_id for s in AVAILABLE_SITES) else "san-agustin"
    referer = request.headers.get("referer", "")
    template_name = "login.html" if "/login" in referer else "landing.html"
    
    def redirect_login_error(msg: str):
        quoted = urllib.parse.quote(msg)
        target = f"/login?site={clean_site_id}&error={quoted}" if "/login" in referer else f"/?site={clean_site_id}&error={quoted}"
        return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)

    # 1. Autenticación por correo/usuario y contraseña
    user = authenticate_user(db, username=username.strip(), password=password)
    
    if not user:
        create_audit_log(
            db,
            user_id=None,
            username=username,
            action="WEB_LOGIN_FAILED",
            details={"reason": "Credenciales inválidas", "attempted_site": clean_site_id, "attempted_role": role_type}
        )
        return redirect_login_error("Las credenciales ingresadas son incorrectas.")

    if not user.is_active:
        create_audit_log(
            db,
            user_id=user.id,
            username=user.username,
            action="WEB_LOGIN_FAILED",
            details={"reason": "Cuenta desactivada"}
        )
        return redirect_login_error("Esta cuenta se encuentra desactivada.")

    # 2. VALIDACIÓN OBLIGATORIA DE COINCIDENCIA DE ROL
    if role_type and role_type.strip():
        rt = role_type.strip().lower()
        user_role_lower = (user.role or "").strip().lower()
        
        role_map = {
            "admin": ["admin", "administrador"],
            "administrador": ["admin", "administrador"],
            "validador": ["validador", "validator"],
            "supervisor": ["supervisor"],
            "mantenimiento": ["empresa de mantenimiento", "mantenimiento", "operario", "tecnico", "responsable"],
            "empresa de mantenimiento": ["empresa de mantenimiento", "mantenimiento", "operario", "tecnico", "responsable"]
        }
        
        allowed_user_roles = role_map.get(rt, [rt])
        if user_role_lower not in allowed_user_roles:
            create_audit_log(
                db,
                user_id=user.id,
                username=user.username,
                action="WEB_LOGIN_FAILED_ROLE_MISMATCH",
                details={"attempted_role": role_type, "actual_role": user.role, "site_id": clean_site_id}
            )
            return redirect_login_error("Las credenciales ingresadas son incorrectas.")

    # 3. VALIDACIÓN OBLIGATORIA DE COINCIDENCIA DE SEDE TERRITORIAL
    selected_site_obj = next((s for s in AVAILABLE_SITES if s["id"] == clean_site_id), None)
    site_name = selected_site_obj["name"] if selected_site_obj else clean_site_id
    site_full = selected_site_obj["full_name"] if selected_site_obj else clean_site_id

    assigned = (user.assigned_site or "").strip()
    if assigned and assigned not in ["Todas las Sedes", "Todas", "Global", ""]:
        norm_assigned = assigned.lower()
        norm_site_id = clean_site_id.lower().replace("-", " ")
        norm_site_name = site_name.lower()
        norm_site_full = site_full.lower()

        matches_site = False
        if "agustin" in norm_assigned or "agustín" in norm_assigned:
            matches_site = ("agustin" in norm_site_name or "agustín" in norm_site_name or "agustin" in norm_site_id or "agustín" in norm_site_id)
        elif "guaviare" in norm_assigned or "josé" in norm_assigned or "jose" in norm_assigned:
            matches_site = ("guaviare" in norm_site_name or "josé" in norm_site_name or "jose" in norm_site_name or "guaviare" in norm_site_id)
        elif "retorno" in norm_assigned:
            matches_site = ("retorno" in norm_site_name or "retorno" in norm_site_id)
        elif "calamar" in norm_assigned:
            matches_site = ("calamar" in norm_site_name or "calamar" in norm_site_id)
        elif "prueba" in norm_assigned or "demo" in norm_assigned:
            matches_site = ("prueba" in norm_site_id or "demo" in norm_site_id or "prueba" in norm_site_name or "demo" in norm_site_name)
        else:
            matches_site = (norm_assigned in norm_site_full or norm_assigned in norm_site_name or norm_assigned == norm_site_id)

        if not matches_site:
            create_audit_log(
                db,
                user_id=user.id,
                username=user.username,
                action="WEB_LOGIN_FAILED_SITE_MISMATCH",
                details={"assigned_site": user.assigned_site, "attempted_site": clean_site_id}
            )
            return redirect_login_error("Las credenciales ingresadas son incorrectas o no corresponden a la sede seleccionada.")

    # Validar vigencia de 24 horas para credenciales temporales
    if user.must_change_password and user.temp_expires_at:
        if get_local_now() > user.temp_expires_at:
            create_audit_log(
                db,
                user_id=user.id,
                username=user.username,
                action="WEB_LOGIN_FAILED_EXPIRED_TEMP_CREDENTIALS",
                details={"reason": "Credenciales temporales expiradas (24 horas)"}
            )
            return redirect_login_error("Las credenciales temporales han expirado (límite de 24 horas de vigencia). Por favor comuníquese con el Administrador para generar un nuevo acceso.")

    # Registrar primer acceso del sitio para activar el reloj de 24 horas
    from app.services.site_license_service import record_site_first_access
    record_site_first_access(db, clean_site_id)

    # Validar licencia activa para usuarios sin rol Admin (si no está suspendida)
    if not getattr(settings, "SUSPEND_SITE_LICENSING", True) and not settings.DEV_MODE and user.role != "Admin":
        is_valid, reason = check_license_validity(db, site_id=clean_site_id)
        if not is_valid:
            create_audit_log(
                db,
                user_id=user.id,
                username=user.username,
                action="WEB_LOGIN_FAILED",
                details={"reason": f"Falta de licencia: {reason}", "site_id": clean_site_id}
            )
            return templates.TemplateResponse(
                request=request,
                name=template_name,
                context={
                    "current_user": None,
                    "selected_site": clean_site_id,
                    "username": username,
                    "error": f"Acceso restringido por licencia: {reason}",
                    "available_sites": AVAILABLE_SITES,
                    "demo_mode": settings.DEMO_MODE,
                    "dev_mode": settings.DEV_MODE
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
        details={"role": user.role, "site_id": clean_site_id, "must_change_password": user.must_change_password}
    )

    target_url = "/change-credentials" if user.must_change_password else "/dashboard"
    response = RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)
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


# ----------------- Rutas de Recuperación de Contraseña (Olvidó su contraseña) -----------------

@app.get("/forgot-password", response_class=HTMLResponse, include_in_schema=False)
def forgot_password_get():
    """Redirige al portal principal indicando apertura de formulario de recuperación."""
    return RedirectResponse(url="/?forgot=1", status_code=status.HTTP_302_FOUND)


@app.post("/forgot-password")
def forgot_password_post(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    """Procesa la solicitud de recuperación de contraseña institucional y despacha una clave temporal al correo."""
    clean_email = email.strip().lower()
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or \
              "application/json" in request.headers.get("accept", "")

    # 1. Validar que se haya ingresado un correo con formato válido
    email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(email_pattern, clean_email):
        err = "El correo electrónico ingresado no tiene un formato válido."
        if is_ajax:
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"success": False, "error": err})
        return RedirectResponse(url=f"/?error={urllib.parse.quote_plus(err)}", status_code=status.HTTP_303_SEE_OTHER)

    # 2. Buscar usuario por correo electrónico o nombre de usuario
    user = db.query(User).filter((User.email == clean_email) | (User.username == clean_email)).first()
    if not user:
        err = f"No existe ninguna cuenta registrada con el correo electrónico '{clean_email}'."
        if is_ajax:
            return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"success": False, "error": err})
        return RedirectResponse(url=f"/?error={urllib.parse.quote_plus(err)}", status_code=status.HTTP_303_SEE_OTHER)

    if not user.is_active:
        err = "Esta cuenta institucional se encuentra inactiva. Contacte al Administrador del Sistema."
        if is_ajax:
            return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"success": False, "error": err})
        return RedirectResponse(url=f"/?error={urllib.parse.quote_plus(err)}", status_code=status.HTTP_303_SEE_OTHER)

    # 3. Generar contraseña temporal segura garantizando que sea única en el sistema
    temp_password = generate_temp_password()
    while is_password_already_in_use(temp_password, db):
        temp_password = generate_temp_password()

    # 4. Actualizar usuario con contraseña temporal (24 horas) y requerimiento de cambio obligatorio
    user.hashed_password = get_password_hash(temp_password)
    user.must_change_password = True
    user.temp_expires_at = get_local_now() + datetime.timedelta(hours=24)
    db.commit()
    db.refresh(user)

    # 5. Registrar en auditoría
    temp_exp = user.temp_expires_at
    create_audit_log(
        db,
        user_id=user.id,
        username=user.username,
        action="PASSWORD_RESET_REQUESTED",
        details={
            "email": clean_email,
            "role": user.role,
            "temp_expires_at": temp_exp.isoformat() if temp_exp else None
        }
    )
    db.commit()

    # 6. Despachar correo electrónico
    email_result = send_temporary_password_email(
        to_email=user.email or clean_email,
        full_name=user.full_name or "Funcionario CCTV",
        temp_password=temp_password,
        site_name=user.assigned_site
    )

    success_msg = f"Se ha enviado una contraseña temporal a su correo '{clean_email}' (vigencia 24 horas). Ingrese con esta clave para configurar su contraseña definitiva."

    if is_ajax:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "message": success_msg,
                "email": clean_email,
                "temp_password": temp_password,
                "sent_via_smtp": email_result.get("sent_via_smtp", False)
            }
        )

    return RedirectResponse(
        url=f"/?msg={urllib.parse.quote_plus(success_msg)}",
        status_code=status.HTTP_303_SEE_OTHER
    )


# ----------------- Rutas de Primer Ingreso / Cambio Obligatorio de Credenciales -----------------

# ----------------- Rutas de Primer Ingreso / Cambio Obligatorio de Credenciales -----------------

@app.get("/change-credentials", response_class=HTMLResponse, include_in_schema=False)
def change_credentials_page(
    request: Request,
    error: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Pantalla obligatoria para actualizar correo institucional y contraseña en el primer ingreso."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    if not current_user.must_change_password:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

    is_admin = (current_user.role == "Admin" or current_user.username == "admin")

    return templates.TemplateResponse(
        request=request,
        name="change_credentials.html",
        context={
            "current_user": current_user,
            "is_admin": is_admin,
            "error": error,
            "demo_mode": settings.DEMO_MODE
        }
    )


@app.post("/change-credentials", response_class=HTMLResponse, include_in_schema=False)
def change_credentials_post(
    request: Request,
    email: Optional[str] = Form(None),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    signature_data: Optional[str] = Form(None),
    is_executive_signatory: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Procesa la actualización obligatoria de correo institucional, contraseña definitiva y firma digital."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    is_admin = (current_user.role == "Admin" or current_user.username == "admin")

    # Si se envía un correo electrónico (ej. Administrador inicial o actualización de correo)
    target_email = current_user.email
    if email and email.strip():
        clean_email = email.strip().lower()
        if clean_email != (current_user.email or "").lower():
            # 1. Validar registros MX del dominio de correo
            is_valid_mx, mx_err = check_email_mx_records(clean_email)
            if not is_valid_mx:
                return templates.TemplateResponse(
                    request=request,
                    name="change_credentials.html",
                    context={"current_user": current_user, "is_admin": is_admin, "error": mx_err}
                )

            # 2. Validar que no esté registrado por otra cuenta
            existing_user = db.query(User).filter(
                (User.email == clean_email) | (User.username == clean_email),
                User.id != current_user.id
            ).first()
            if existing_user:
                return templates.TemplateResponse(
                    request=request,
                    name="change_credentials.html",
                    context={"current_user": current_user, "is_admin": is_admin, "error": f"El correo electrónico '{clean_email}' ya se encuentra registrado por otro usuario."}
                )
            target_email = clean_email

    if len(new_password) < 6:
        return templates.TemplateResponse(
            request=request,
            name="change_credentials.html",
            context={"current_user": current_user, "is_admin": is_admin, "error": "La nueva contraseña debe tener al menos 6 caracteres."}
        )

    if new_password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="change_credentials.html",
            context={"current_user": current_user, "is_admin": is_admin, "error": "Las contraseñas ingresadas no coinciden."}
        )

    # Validar que la nueva contraseña no sea idéntica a la anterior
    if verify_password(new_password, current_user.hashed_password):
        return templates.TemplateResponse(
            request=request,
            name="change_credentials.html",
            context={"current_user": current_user, "is_admin": is_admin, "error": "La nueva contraseña no puede ser idéntica a tu contraseña anterior."}
        )

    # Validar que la contraseña no exista previamente en ningún usuario del sistema
    if is_password_already_in_use(new_password, db, exclude_user_id=current_user.id):
        return templates.TemplateResponse(
            request=request,
            name="change_credentials.html",
            context={"current_user": current_user, "is_admin": is_admin, "error": "La contraseña ingresada ya se encuentra registrada en el sistema por otro usuario. Por seguridad, debes elegir una contraseña diferente y única."}
        )

    # Validar firma digital obligatoria en primer ingreso
    if not signature_data or not signature_data.strip():
        return templates.TemplateResponse(
            request=request,
            name="change_credentials.html",
            context={"current_user": current_user, "is_admin": is_admin, "error": "La firma digital es obligatoria. Debes dibujarla con el mouse o cargar una imagen de tu firma."}
        )

    try:
        from app.utils.signature import save_signature_image
        sig_path = save_signature_image(signature_data, current_user.id)
        current_user.signature_path = sig_path
    except Exception as e_sig:
        return templates.TemplateResponse(
            request=request,
            name="change_credentials.html",
            context={"current_user": current_user, "is_admin": is_admin, "error": f"Error al procesar la firma digital: {str(e_sig)}"}
        )

    # Actualizar credenciales definitivas y remover banderas de cambio temporal
    old_email = current_user.email
    current_user.email = target_email
    current_user.username = target_email
    current_user.hashed_password = get_password_hash(new_password)
    current_user.must_change_password = False
    current_user.temp_expires_at = None

    if current_user.role == "Validador":
        is_sig_checked = (is_executive_signatory in ["true", "on", "1"])
        if is_sig_checked:
            db.query(User).filter(User.role == "Validador", User.id != current_user.id).update({"is_executive_signatory": False})
            current_user.is_executive_signatory = True
        else:
            current_user.is_executive_signatory = False

    db.commit()

    create_audit_log(
        db,
        user_id=current_user.id,
        username=target_email,
        action="USER_FIRST_LOGIN_CREDENTIALS_UPDATED",
        details={"old_email": old_email, "new_email": target_email}
    )

    # Generar nuevo token JWT con el correo como identificador
    access_token = create_access_token(data={"sub": target_email})

    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
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
    Autentica el rol solicitado sin contraseña usando cuentas exclusivas de Demo
    con los permisos exactos de cada perfil.
    """
    clean_site_id = "sitio-prueba"
    demo_site_full = "Sitio de Prueba (Entorno Demo)"

    demo_profiles = {
        "admin": {
            "username": "admin_demo",
            "email": "admin.demo@cctv-seguridad.gov.co",
            "full_name": "Administrador Demo",
            "role": "Admin",
            "document_id": "9000000001",
            "badge_number": None,
            "signature_path": "/static/uploads/signatures/seed_sig_1_admin.png",
        },
        "validador": {
            "username": "validador_demo",
            "email": "validador.demo@cctv-seguridad.gov.co",
            "full_name": "Validador Policial Demo",
            "role": "Validador",
            "document_id": "9000000002",
            "badge_number": "DEMO-109845",
            "signature_path": "/static/uploads/signatures/seed_sig_10_validador.png",
        },
        "supervisor": {
            "username": "supervisor_demo",
            "email": "supervisor.demo@cctv-seguridad.gov.co",
            "full_name": "Supervisor de Contrato Demo",
            "role": "Supervisor",
            "document_id": "9000000003",
            "badge_number": None,
            "signature_path": None,
        },
        "mantenimiento": {
            "username": "mantenimiento_demo",
            "email": "mantenimiento.demo@cctv-seguridad.gov.co",
            "full_name": "Empresa de Mantenimiento Demo",
            "role": "Empresa de Mantenimiento",
            "document_id": "9000000004",
            "badge_number": None,
            "signature_path": None,
        },
    }

    role_key = (demo_role or "admin").strip().lower()
    profile = demo_profiles.get(role_key, demo_profiles["admin"])

    user = db.query(User).filter(User.username == profile["username"]).first()
    if not user:
        user = User(
            username=profile["username"],
            email=profile["email"],
            full_name=profile["full_name"],
            document_id=profile["document_id"],
            badge_number=profile["badge_number"],
            assigned_site=demo_site_full,
            hashed_password=get_password_hash("demo123"),
            role=profile["role"],
            is_active=True,
            is_deleted=False,
            must_change_password=False,
            signature_path=profile["signature_path"],
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        changed = False
        if not user.is_active or user.is_deleted or user.must_change_password or user.role != profile["role"]:
            user.is_active = True
            user.is_deleted = False
            user.must_change_password = False
            user.role = profile["role"]
            user.assigned_site = demo_site_full
            changed = True
        if profile["signature_path"] and not user.signature_path:
            user.signature_path = profile["signature_path"]
            changed = True
        if profile["badge_number"] and not user.badge_number:
            user.badge_number = profile["badge_number"]
            changed = True
        if changed:
            db.commit()
            db.refresh(user)

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
    # Si DEMO_MODE está activo a nivel de servidor, se restablece el sandbox en memoria
    if settings.DEMO_MODE:
        try:
            from app.seeder_demo import seed_demo_data
            seed_demo_data(db)
            print("[*] [Modo Demo] Sesión de memoria restablecida.")
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
    sede: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Panel Principal de Control y Monitoreo Ejecutivo.
    Muestra un resumen ejecutivo, gráfico y en tiempo real del estado de la infraestructura CCTV,
    incidentes y mantenimientos, conectado 100% a la base de datos viva.
    """
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request, db=db)

    lic_redirect = check_site_access_or_redirect(request, current_user, current_site, db)
    if lic_redirect:
        return lic_redirect

    # Condiciones base de filtrado por sede
    site_device_cond = get_site_filter_conditions(Device, current_site)
    site_inc_cond = get_site_filter_conditions(Incident, current_site)
    site_maint_cond = get_site_filter_conditions(Maintenance, current_site)

    # Filtro opcional por punto/sede secundaria
    selected_sede_name = sede if (sede and sede != "all" and sede != current_site["full_name"]) else "all"
    if selected_sede_name != "all":
        sub_dev_filter = or_(Device.location_detail == selected_sede_name, Device.sede == selected_sede_name, Device.location_detail.ilike(f"%{selected_sede_name}%"))
        sub_inc_filter = or_(Incident.sede == selected_sede_name, Incident.location_detail == selected_sede_name, Incident.location_detail.ilike(f"%{selected_sede_name}%"))
        sub_maint_filter = or_(Maintenance.sede == selected_sede_name, Maintenance.location_detail == selected_sede_name, Maintenance.location_detail.ilike(f"%{selected_sede_name}%"))
        
        # Verificar si hay equipos en esa sede secundaria
        if (db.query(func.count(Device.id)).filter(and_(site_device_cond, sub_dev_filter)).scalar() or 0) > 0:
            site_device_cond = and_(site_device_cond, sub_dev_filter)
            site_inc_cond = and_(site_inc_cond, sub_inc_filter)
            site_maint_cond = and_(site_maint_cond, sub_maint_filter)
        else:
            selected_sede_name = "all"

    # Subconsultas para cálculo operativo de dispositivos en BD (evita carga a RAM)
    falla_subq = select(Incident.device_id).filter(
        Incident.status.in_(["Abierto", "En Proceso", "Rechazado"]),
        Incident.device_id.isnot(None)
    )
    maint_subq = select(Maintenance.device_id).filter(
        Maintenance.status.in_(["En Ejecución", "Programado"]),
        Maintenance.device_id.isnot(None)
    )

    camera_cond = or_(
        Device.device_type.ilike("%cámara%"),
        Device.device_type.ilike("%camara%"),
        Device.device_type.ilike("%ptz%"),
        Device.device_type.ilike("%domo%"),
        Device.device_type.ilike("%bala%")
    )

    # 1. Agregación SQL directa para métricas de Dispositivos (Cero carga a RAM)
    dev_agg = db.query(
        func.count(Device.id).label("total"),
        func.count(case((Device.status == "Inactivo", 1))).label("inactivos"),
        func.count(case(((Device.status != "Inactivo") & (Device.id.in_(falla_subq)), 1))).label("fallas"),
        func.count(case(((Device.status != "Inactivo") & (~Device.id.in_(falla_subq)) & (Device.id.in_(maint_subq)), 1))).label("mantenimiento"),
        func.count(case((camera_cond, 1))).label("cameras_total"),
        func.count(case((camera_cond & (Device.status != "Inactivo") & (Device.id.in_(falla_subq)), 1))).label("cameras_falla"),
    ).filter(site_device_cond).first()

    total_devices = (dev_agg.total if dev_agg else 0) or 0
    inactivo_devices = (dev_agg.inactivos if dev_agg else 0) or 0
    falla_devices = (dev_agg.fallas if dev_agg else 0) or 0
    maint_devices = (dev_agg.mantenimiento if dev_agg else 0) or 0
    operativo_devices = max(0, total_devices - inactivo_devices - falla_devices - maint_devices)
    availability_pct = round((operativo_devices / total_devices * 100), 1) if total_devices > 0 else 100.0

    cameras_total = (dev_agg.cameras_total if dev_agg else 0) or 0
    cameras_falla = (dev_agg.cameras_falla if dev_agg else 0) or 0
    cameras_active = max(0, cameras_total - cameras_falla)
    cameras_pct = round((cameras_active / cameras_total * 100), 1) if cameras_total > 0 else 100.0

    # 2. Agregación SQL directa para métricas de Incidentes (Cero carga a RAM)
    resolved_statuses = ["Cerrado", "Resuelto", "Validado / Conforme", "Conforme / Validado"]
    inc_agg = db.query(
        func.count(Incident.id).label("total"),
        func.count(case((~Incident.status.in_(resolved_statuses), 1))).label("open_count"),
        func.count(case((Incident.status.in_(resolved_statuses), 1))).label("closed_count"),
        func.count(case(((~Incident.status.in_(resolved_statuses)) & ((Incident.priority == "Crítica") | (Incident.fault_type == "Falla Crítica")), 1))).label("critical_count"),
        func.count(case(((~Incident.status.in_(resolved_statuses)) & (Incident.priority == "Alta"), 1))).label("high_count"),
    ).filter(site_inc_cond).first()

    total_incidents = (inc_agg.total if inc_agg else 0) or 0
    open_incidents_count = (inc_agg.open_count if inc_agg else 0) or 0
    closed_incidents_count = (inc_agg.closed_count if inc_agg else 0) or 0
    critical_incidents = (inc_agg.critical_count if inc_agg else 0) or 0
    high_incidents = (inc_agg.high_count if inc_agg else 0) or 0

    # Evaluación eficiente de SLA sobre incidentes abiertos (máx 50)
    open_incidents = db.query(Incident).filter(
        site_inc_cond,
        ~Incident.status.in_(resolved_statuses)
    ).order_by(Incident.created_at.desc()).limit(50).all()

    sla_expired_count = sum(1 for i in open_incidents if i.sla_info["status"] == "expired")
    sla_warning_count = sum(1 for i in open_incidents if i.sla_info["status"] == "warning")

    # Muestra de cumplimiento SLA para tickets resueltos/cerrados (máx 100)
    sample_closed = db.query(Incident).filter(
        site_inc_cond,
        Incident.status.in_(resolved_statuses)
    ).order_by(Incident.closed_at.desc().nullslast()).limit(100).all()
    sla_on_time_closed = sum(1 for i in sample_closed if i.sla_info["status"] in ["closed_on_time", "resolved_on_time"])
    sla_compliance_pct = round((sla_on_time_closed / len(sample_closed) * 100), 1) if sample_closed else 100.0

    # 3. Agregación SQL directa para métricas de Mantenimientos
    now = get_local_now()
    maint_agg = db.query(
        func.count(Maintenance.id).label("total"),
        func.count(case((Maintenance.status == "En Ejecución", 1))).label("in_exec"),
        func.count(case((Maintenance.status == "Programado", 1))).label("scheduled"),
        func.count(case((Maintenance.status.in_(["Completado", "Validado / Conforme", "Conforme / Validado"]), 1))).label("completed"),
        func.count(case(((Maintenance.status.in_(["Programado", "En Ejecución"])) & (Maintenance.scheduled_date < now), 1))).label("overdue"),
        func.count(case(((Maintenance.status == "Programado") & (Maintenance.scheduled_date >= now) & (Maintenance.scheduled_date <= now + datetime.timedelta(days=2)), 1))).label("due_soon"),
    ).filter(site_maint_cond).first()

    total_maintenances = (maint_agg.total if maint_agg else 0) or 0
    in_exec_maintenances = (maint_agg.in_exec if maint_agg else 0) or 0
    scheduled_maintenances = (maint_agg.scheduled if maint_agg else 0) or 0
    completed_maintenances = (maint_agg.completed if maint_agg else 0) or 0
    pending_maintenances = in_exec_maintenances + scheduled_maintenances
    overdue_maintenances = (maint_agg.overdue if maint_agg else 0) or 0
    due_soon_maintenances = (maint_agg.due_soon if maint_agg else 0) or 0

    # 4. Semáforo y Resumen Ejecutivo Global
    if critical_incidents > 0 or sla_expired_count > 0 or falla_devices >= 5:
        system_health = {
            "title": "Alerta Prioritaria Requerida",
            "badge": "Alerta Inmediata",
            "level": "critical",
            "color": "rose",
            "border": "border-rose-500/40",
            "bg_gradient": "from-rose-950/60 via-slate-900 to-slate-900",
            "badge_bg": "bg-rose-500/20 text-rose-300 border-rose-500/30",
            "dot": "bg-rose-500 animate-pulse",
            "headline": f"{falla_devices} novedades activas requieren intervención técnica",
            "description": f"Se registran {critical_incidents} fallas críticas o alertas SLA vencidas en {current_site['full_name']}. Se recomienda priorizar la atención técnica.",
            "action_needed": True
        }
    elif falla_devices > 0 or overdue_maintenances > 0 or in_exec_maintenances > 0:
        system_health = {
            "title": "Operativo con Actividades en Curso",
            "badge": "Atención / En Proceso",
            "level": "warning",
            "color": "amber",
            "border": "border-amber-500/40",
            "bg_gradient": "from-amber-950/50 via-slate-900 to-slate-900",
            "badge_bg": "bg-amber-500/20 text-amber-300 border-amber-500/30",
            "dot": "bg-amber-400 animate-pulse",
            "headline": f"{availability_pct}% de Disponibilidad Operativa ({operativo_devices}/{total_devices} equipos)",
            "description": f"{falla_devices} equipo(s) con novedad técnica y {pending_maintenances} mantenimiento(s) preventivos en gestión.",
            "action_needed": True
        }
    else:
        system_health = {
            "title": "Sistema 100% Operativo y Estable",
            "badge": "Operación Óptima",
            "level": "healthy",
            "color": "emerald",
            "border": "border-emerald-500/40",
            "bg_gradient": "from-emerald-950/40 via-slate-900 to-slate-900",
            "badge_bg": "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
            "dot": "bg-emerald-400 animate-pulse",
            "headline": f"100% de Disponibilidad ({total_devices} equipos en línea)",
            "description": "Toda la red de cámaras, NVRs y telecomunicaciones opera normalmente sin novedades abiertas.",
            "action_needed": False
        }

    # 5. Agrupación Dinámica en SQL de Puntos de Monitoreo (Zero RAM bottleneck)
    point_rows = db.query(
        func.coalesce(Device.location_detail, "Punto General").label("loc_name"),
        func.coalesce(Device.sede, current_site["full_name"]).label("address"),
        func.count(Device.id).label("total"),
        func.count(case((Device.status == "Inactivo", 1))).label("inactivos"),
        func.count(case(((Device.status != "Inactivo") & (Device.id.in_(falla_subq)), 1))).label("fallas"),
        func.count(case(((Device.status != "Inactivo") & (~Device.id.in_(falla_subq)) & (Device.id.in_(maint_subq)), 1))).label("mantenimiento"),
        func.count(case((camera_cond, 1))).label("cameras"),
        func.count(case((camera_cond & (Device.status != "Inactivo") & (~Device.id.in_(falla_subq)) & (~Device.id.in_(maint_subq)), 1))).label("cameras_operativas")
    ).filter(site_device_cond).group_by(
        func.coalesce(Device.location_detail, "Punto General"),
        func.coalesce(Device.sede, current_site["full_name"])
    ).all()

    monitoring_points = []
    for r in point_rows:
        t = r.total or 0
        f = r.fallas or 0
        m = r.mantenimiento or 0
        inact = r.inactivos or 0
        o = max(0, t - f - m - inact)
        pct = round((o / t * 100), 1) if t > 0 else 100.0

        if f > 0:
            st_label = "Con Novedades"
            badge_class = "bg-rose-50 text-rose-700 border-rose-200"
            dot_class = "bg-rose-500"
        elif m > 0:
            st_label = "Mantenimiento"
            badge_class = "bg-blue-50 text-blue-700 border-blue-200"
            dot_class = "bg-blue-500"
        else:
            st_label = "100% Operativo"
            badge_class = "bg-emerald-50 text-emerald-700 border-emerald-200"
            dot_class = "bg-emerald-500"

        monitoring_points.append({
            "name": r.loc_name,
            "total": t,
            "operativos": o,
            "fallas": f,
            "mantenimiento": m,
            "cameras": r.cameras or 0,
            "cameras_operativas": r.cameras_operativas or 0,
            "pct": pct,
            "status": st_label,
            "badge_class": badge_class,
            "dot_class": dot_class,
            "address": r.address
        })

    monitoring_points.sort(key=lambda p: (p["fallas"] * -10 - p["mantenimiento"] * 2, -p["total"], p["name"]))

    # 6. Alertas de Atención Inmediata (Top prioritarias limitadas)
    executive_alerts = []
    for inc in open_incidents:
        if inc.sla_info["status"] == "expired":
            executive_alerts.append({
                "type": "danger",
                "badge": "SLA Vencido",
                "title": f"Incidente #{inc.ticket_code}: {inc.title}",
                "detail": f"{inc.sla_info['detail']} - {inc.device.name if inc.device else inc.sede}",
                "url": "/incidents",
                "btn_text": "Ver Ticket"
            })
        elif inc.priority == "Crítica" or getattr(inc, "fault_type", "") == "Falla Crítica":
            executive_alerts.append({
                "type": "danger",
                "badge": "Falla Crítica",
                "title": f"Incidente #{inc.ticket_code}: {inc.title}",
                "detail": f"Prioridad Crítica en {inc.sede}. Requiere diagnóstico.",
                "url": "/incidents",
                "btn_text": "Atender"
            })

    top_urgent_maints = db.query(Maintenance).filter(
        site_maint_cond,
        Maintenance.status.in_(["Programado", "En Ejecución"])
    ).order_by(Maintenance.scheduled_date.asc()).limit(6).all()

    for m in top_urgent_maints:
        if m.status in ["Programado", "En Ejecución"] and m.proactive_status["status"] == "overdue":
            executive_alerts.append({
                "type": "warning",
                "badge": "Mantenimiento Atrasado",
                "title": f"{m.code}: {m.title}",
                "detail": f"{m.proactive_status['detail']} - {m.location_detail or m.sede}",
                "url": "/maintenance",
                "btn_text": "Gestionar"
            })
        elif m.status == "En Ejecución":
            executive_alerts.append({
                "type": "info",
                "badge": "En Terreno",
                "title": f"{m.code}: {m.title}",
                "detail": f"Cuadrilla técnica en sitio en {m.location_detail or m.sede}",
                "url": "/maintenance",
                "btn_text": "Seguimiento"
            })

    executive_alerts = executive_alerts[:4]

    # 7. Datos de Gráficos Ejecutivos (Serializados en JSON para Chart.js)
    chart_operatividad = {
        "labels": ["Operativos", "En Falla", "En Mantenimiento", "Inactivos"],
        "data": [operativo_devices, falla_devices, maint_devices, inactivo_devices],
        "colors": ["#10B981", "#EF4444", "#3B82F6", "#94A3B8"]
    }

    top_points = monitoring_points[:8]
    chart_puntos = {
        "labels": [p["name"].replace('Cam ', 'C').replace('"', '') for p in top_points],
        "operativos": [p["operativos"] for p in top_points],
        "novedades": [p["fallas"] + p["mantenimiento"] for p in top_points]
    }

    # 8. Actividad reciente
    recent_incidents = db.query(Incident).filter(site_inc_cond).order_by(Incident.created_at.desc()).limit(4).all()
    recent_maintenances = db.query(Maintenance).filter(site_maint_cond).order_by(Maintenance.scheduled_date.asc()).limit(4).all()

    metrics = {
        "total_devices": total_devices,
        "operativo_devices": operativo_devices,
        "falla_devices": falla_devices,
        "maint_devices": maint_devices,
        "inactivo_devices": inactivo_devices,
        "availability_pct": availability_pct,
        "cameras_total": cameras_total,
        "cameras_active": cameras_active,
        "cameras_falla": cameras_falla,
        "cameras_pct": cameras_pct,
        "open_incidents": open_incidents_count,
        "critical_incidents": critical_incidents,
        "high_incidents": high_incidents,
        "closed_incidents": closed_incidents_count,
        "total_incidents": total_incidents,
        "sla_expired_count": sla_expired_count,
        "sla_warning_count": sla_warning_count,
        "sla_compliance_pct": sla_compliance_pct,
        "in_exec_maintenances": in_exec_maintenances,
        "scheduled_maintenances": scheduled_maintenances,
        "pending_maintenances": pending_maintenances,
        "completed_maintenances": completed_maintenances,
        "overdue_maintenances": overdue_maintenances,
        "due_soon_maintenances": due_soon_maintenances,
        "total_maintenances": total_maintenances,
    }

    # 9. Conteo de órdenes pendientes de validación técnica policial
    pending_inc_val = db.query(Incident).filter(
        site_inc_cond,
        Incident.status == "Pendiente de Validación"
    ).count()
    pending_maint_val = db.query(Maintenance).filter(
        site_maint_cond,
        Maintenance.status == "Pendiente de Validación"
    ).count()
    pending_validation_count = pending_inc_val + pending_maint_val

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "current_user": current_user,
            "current_site": current_site,
            "available_sites": get_available_sites(db, active_only=True),
            "active_page": "dashboard",
            "selected_sede": selected_sede_name,
            "metrics": metrics,
            "system_health": system_health,
            "monitoring_points": monitoring_points,
            "executive_alerts": executive_alerts,
            "chart_operatividad_json": json.dumps(chart_operatividad),
            "chart_puntos_json": json.dumps(chart_puntos),
            "recent_incidents": recent_incidents,
            "recent_maintenances": recent_maintenances,
            "pending_validation_count": pending_validation_count
        }
    )



# ----------------- 6. Gestión de Inventario de Equipos (Filtrado por Sede) -----------------

def is_default_main_admin(user: Optional[User]) -> bool:
    """
    Verifica si el usuario es estrictamente el Administrador Principal por defecto del sistema ('admin' / id=1).
    Ningún otro usuario (incluso con rol 'Admin' creado posteriormente por el administrador principal,
    supervisores o contratistas) cuenta con autorización para borrar o trasladar equipos del inventario.
    """
    if not user:
        return False
    return user.role == "Admin" and (user.id == 1 or user.username == "admin" or user.username == settings.ADMIN_USERNAME or user.username == "admin_demo")


@app.get("/devices", response_class=HTMLResponse)
@app.get("/equipment", response_class=HTMLResponse)
def devices_view(
    request: Request,
    msg: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Vista web de inventario de equipos filtrada por la sede activa."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request)

    lic_redirect = check_site_access_or_redirect(request, current_user, current_site, db)
    if lic_redirect:
        return lic_redirect

    devices_list = db.query(Device).filter(
        get_site_filter_conditions(Device, current_site)
    ).order_by(Device.id.asc()).all()

    # Lista ordenada de sitios preconfigurados y adicionales existentes
    default_sitios = [
        "Parque Arqueológico",
        "Colegio CRRC",
        "Estación de Policía",
        "Carabineros",
        "Terminal de Transportes",
        "Cuatro Vientos",
        "Barrio Kennedy"
    ]
    ordered_sitios = list(default_sitios)
    for d in devices_list:
        if d.location_detail and d.location_detail not in ordered_sitios:
            ordered_sitios.append(d.location_detail)

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
            "sedes": site_sedes,
            "sitios": ordered_sitios,
            "msg": msg,
            "error": error,
            "is_default_admin": is_default_main_admin(current_user)
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
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Crea un nuevo equipo en el inventario del municipio activo."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.role in ["Supervisor", "Validador"]:
        if current_user.role == "Validador":
            err = urllib.parse.quote("Acceso denegado: El rol Validador (Policía Nacional) tiene funciones exclusivas de verificación y conformidad de incidentes y mantenimientos, y no puede registrar nuevos equipos.")
        else:
            err = urllib.parse.quote("Acceso denegado: El rol Supervisor tiene perfil de solo lectura y no puede registrar nuevos equipos.")
        return RedirectResponse(url=f"/devices?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    current_site = get_current_site(request)
    assigned_sede = sede if sede and sede.strip() else current_site["full_name"]

    clean_ip = ip_address.strip() if ip_address and ip_address.strip() and ip_address.strip().upper() not in ["NO APLICA", "N/A"] else None

    new_device = Device(
        name=name.strip(),
        device_type=device_type.strip(),
        sede=assigned_sede,
        location_detail=location_detail.strip() if location_detail else None,
        brand=brand.strip() if brand else None,
        model=model.strip() if model else None,
        serial_number=serial_number.strip() if serial_number else None,
        ip_address=clean_ip,
        status="Operativo"
    )
    db.add(new_device)
    db.commit()
    db.refresh(new_device)

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="DEVICE_CREATED",
        details={
            "device_id": new_device.id,
            "name": new_device.name,
            "sitio": new_device.location_detail,
            "type": device_type,
            "sede": assigned_sede
        }
    )
    db.commit()

    msg = urllib.parse.quote(f"Equipo '{new_device.name}' registrado exitosamente en {new_device.location_detail or 'el inventario'}.")
    return RedirectResponse(url=f"/devices?msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/devices/{device_id}/relocate")
def relocate_device_web(
    request: Request,
    device_id: int,
    new_sitio: str = Form(...),
    admin_password: str = Form(...),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Traslada un equipo de un sitio a otro dentro de la sede activa. Exclusivo para el Administrador Principal por defecto del sistema con contraseña."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    # 1. Validar que el usuario sea estrictamente el Administrador Principal por defecto del sistema
    if not is_default_main_admin(current_user):
        err = urllib.parse.quote("Acceso denegado: Únicamente el Administrador Principal por defecto del sistema tiene autorización para trasladar equipos.")
        return RedirectResponse(url=f"/devices?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    # 2. Validar contraseña del administrador
    if not verify_password(admin_password, current_user.hashed_password):
        err = urllib.parse.quote("Contraseña de administrador incorrecta. Autorización para traslado denegada.")
        return RedirectResponse(url=f"/devices?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    # 3. Buscar el equipo y verificar que pertenezca a la sede actual
    current_site = get_current_site(request)
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        err = urllib.parse.quote("El equipo especificado no existe.")
        return RedirectResponse(url=f"/devices?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    if device.sede != current_site["full_name"]:
        err = urllib.parse.quote("No se puede trasladar un equipo que no pertenece a la sede territorial activa.")
        return RedirectResponse(url=f"/devices?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    new_sitio_clean = new_sitio.strip()
    if not new_sitio_clean:
        err = urllib.parse.quote("Debe indicar el nuevo sitio o punto de instalación.")
        return RedirectResponse(url=f"/devices?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    old_sitio = device.location_detail or "Sin sitio asignado"
    device.location_detail = new_sitio_clean
    db.commit()

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="DEVICE_RELOCATED",
        details={
            "device_id": device.id,
            "device_name": device.name,
            "serial_number": device.serial_number,
            "old_sitio": old_sitio,
            "new_sitio": new_sitio_clean,
            "sede": device.sede
        }
    )
    db.commit()

    msg = urllib.parse.quote(f"Equipo '{device.name}' trasladado exitosamente a '{new_sitio_clean}'.")
    return RedirectResponse(url=f"/devices?msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/devices/{device_id}/delete")
def delete_device_web(
    request: Request,
    device_id: int,
    admin_password: str = Form(...),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Elimina permanentemente un equipo del inventario. Exclusivo para el Administrador Principal por defecto del sistema con contraseña."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    # 1. Validar que el usuario sea estrictamente el Administrador Principal por defecto del sistema
    if not is_default_main_admin(current_user):
        err = urllib.parse.quote("Acceso denegado: Únicamente el Administrador Principal por defecto del sistema tiene autorización para quitar equipos.")
        return RedirectResponse(url=f"/devices?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    # 2. Validar contraseña del administrador
    if not verify_password(admin_password, current_user.hashed_password):
        err = urllib.parse.quote("Contraseña de administrador incorrecta. Autorización para quitar equipo denegada.")
        return RedirectResponse(url=f"/devices?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    # 3. Buscar el equipo y verificar que pertenezca a la sede actual
    current_site = get_current_site(request)
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        err = urllib.parse.quote("El equipo especificado no existe.")
        return RedirectResponse(url=f"/devices?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    if device.sede != current_site["full_name"]:
        err = urllib.parse.quote("No se puede eliminar un equipo que no pertenece a la sede territorial activa.")
        return RedirectResponse(url=f"/devices?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    device_name = device.name
    device_serial = device.serial_number
    device_sitio = device.location_detail

    # Desvincular de incidentes y mantenimientos previos para preservar historial y auditoría
    db.query(Incident).filter(Incident.device_id == device.id).update({Incident.device_id: None})
    db.query(Maintenance).filter(Maintenance.device_id == device.id).update({Maintenance.device_id: None})

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="DEVICE_DELETED",
        details={
            "device_id": device.id,
            "device_name": device_name,
            "serial_number": device_serial,
            "sitio": device_sitio,
            "sede": device.sede
        }
    )
    db.delete(device)
    db.commit()

    msg = urllib.parse.quote(f"Equipo '{device_name}' (S/N: {device_serial or 'N/A'}) retirado exitosamente del inventario.")
    return RedirectResponse(url=f"/devices?msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/devices/{device_id}/status")
def update_device_status_web(
    device_id: int,
    new_status: str = Form(..., alias="status"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Actualiza el estado operativo de un equipo."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.role == "Supervisor":
        err = urllib.parse.quote("Acceso denegado: El rol Supervisor tiene perfil de solo lectura y no puede modificar el estado de los equipos.")
        return RedirectResponse(url=f"/devices?error={err}", status_code=status.HTTP_303_SEE_OTHER)

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


def is_main_admin(user: Optional[User]) -> bool:
    """Verifica si el usuario cuenta con privilegios de Administrador para gestionar usuarios."""
    if not user:
        return False
    return user.role == "Admin"


@app.get("/users", response_class=HTMLResponse)
def users_view(
    request: Request,
    msg: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    created_name: Optional[str] = Query(None),
    created_doc: Optional[str] = Query(None),
    created_badge: Optional[str] = Query(None),
    created_user: Optional[str] = Query(None),
    created_pass: Optional[str] = Query(None),
    created_role: Optional[str] = Query(None),
    created_site: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Vista web de administración de usuarios institucionales."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)
    
    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    if current_user.role != "Admin":
        return RedirectResponse(url="/dashboard?error=Acceso+restringido:+La+opción+de+gestión+de+usuarios+es+exclusiva+del+Administrador.", status_code=status.HTTP_303_SEE_OTHER)

    current_site = get_current_site(request)
    if current_site.get("id") == "sitio-prueba" or current_user.username == "admin_demo" or request.cookies.get("is_demo_session") == "true":
        return RedirectResponse(url="/dashboard?error=Opción+deshabilitada+por+seguridad+en+el+entorno+Demo.", status_code=status.HTTP_303_SEE_OTHER)
    site_name = current_site["name"]
    users_list = db.query(User).filter(
        User.is_deleted == False,
        ((User.assigned_site.ilike(f"%{site_name}%")) | 
         (User.assigned_site == "Todas las Sedes") | 
         (User.assigned_site == None))
    ).order_by(User.created_at.desc()).all()

    new_credentials = None
    if created_user and created_pass:
        new_credentials = {
            "name": created_name or "",
            "doc": created_doc or "",
            "badge": created_badge or "",
            "user": created_user,
            "pass": created_pass,
            "role": created_role or "",
            "site": created_site or ""
        }

    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={
            "current_user": current_user,
            "is_main_admin": is_main_admin(current_user),
            "current_site": current_site,
            "available_sites": AVAILABLE_SITES,
            "active_page": "users",
            "users": users_list,
            "msg": msg,
            "error": error,
            "new_credentials": new_credentials
        }
    )


@app.post("/users")
def create_user_web(
    request: Request,
    full_name: str = Form(...),
    document_id: str = Form(...),
    email: str = Form(...),
    role: str = Form("Validador"),
    badge_number: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Crea una nueva cuenta de usuario institucional con credenciales temporales generadas automáticamente (24h vigencia) o contraseña manual única."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    if current_user.role != "Admin":
        return RedirectResponse(url="/users?error=Solo+el+Administrador+Principal+puede+crear+cuentas+de+usuario", status_code=status.HTTP_303_SEE_OTHER)

    if get_current_site(request).get("id") == "sitio-prueba" or current_user.username == "admin_demo" or request.cookies.get("is_demo_session") == "true":
        return RedirectResponse(url="/dashboard?error=Opción+deshabilitada+por+seguridad+en+el+entorno+Demo.", status_code=status.HTTP_303_SEE_OTHER)

    # 1. Regla estricta: Solo un (1) Administrador Principal en todo el sistema
    if role == "Admin":
        return RedirectResponse(url="/users?error=No+es+posible+crear+administradores+adicionales.+Existe+únicamente+un+(1)+Administrador+Principal+en+todo+el+sistema.", status_code=status.HTTP_303_SEE_OTHER)

    # 2. Roles operativos exclusivos asignados por el Administrador
    valid_roles = ["Validador", "Supervisor", "Empresa de Mantenimiento", "Operario"]
    if role not in valid_roles:
        return RedirectResponse(url="/users?error=Rol+no+válido.+Seleccione+uno+de+los+tres+perfiles+operativos:+Validador,+Supervisor+o+Empresa+de+Mantenimiento.", status_code=status.HTTP_303_SEE_OTHER)

    # Validar límite de usuarios activos de la licencia
    try:
        verify_user_limit(db)
    except HTTPException as exc:
        return RedirectResponse(url=f"/users?error={urllib.parse.quote(exc.detail)}", status_code=status.HTTP_303_SEE_OTHER)

    clean_fullname = full_name.strip()
    clean_doc = document_id.strip()
    clean_email = email.strip().lower()
    clean_badge = (badge_number or "").strip()

    # 1. Validar que en el nombre se reciban solo letras y espacios (el nombre sí puede ser igual a otros)
    if not re.match(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]+$", clean_fullname):
        return RedirectResponse(url="/users?error=El+nombre+completo+solo+puede+contener+letras+y+espacios.", status_code=status.HTTP_303_SEE_OTHER)

    # 2. Validar que en el documento de identidad solo se reciban números
    if not clean_doc.isdigit():
        return RedirectResponse(url="/users?error=El+documento+de+identidad+debe+contener+solo+números+(sin+puntos+ni+espacios).", status_code=status.HTTP_303_SEE_OTHER)

    # 3. Validación exclusiva para Validador: Número de placa policial obligatorio y numérico (Policía Nacional)
    if role == "Validador":
        if not clean_badge:
            return RedirectResponse(url="/users?error=El+número+de+placa+policial+es+obligatorio+para+el+rol+Validador.", status_code=status.HTTP_303_SEE_OTHER)
        if not clean_badge.isdigit():
            return RedirectResponse(url="/users?error=El+número+de+placa+policial+debe+contener+únicamente+dígitos+numéricos.", status_code=status.HTTP_303_SEE_OTHER)
    else:
        clean_badge = clean_badge if clean_badge else None

    # 4. Validar existencia real del dominio de correo mediante registros DNS MX
    is_valid_mx, mx_err = check_email_mx_records(clean_email)
    if not is_valid_mx:
        encoded_err = urllib.parse.quote(mx_err)
        return RedirectResponse(url=f"/users?error={encoded_err}", status_code=status.HTTP_303_SEE_OTHER)

    # 5. Comprobar registros coincidentes activos en base de datos (excluyendo cuentas eliminadas para no colisionar)
    existing_by_email = db.query(User).filter(User.is_deleted == False, (User.email == clean_email) | (User.username == clean_email)).first()
    existing_by_doc = db.query(User).filter(User.is_deleted == False, User.document_id == clean_doc).first()
    existing_by_badge = db.query(User).filter(User.is_deleted == False, User.badge_number == clean_badge).first() if clean_badge else None

    # Regla: La cuenta del Administrador Principal no puede ser sobrescrita ni duplicada
    for ex in [existing_by_email, existing_by_doc, existing_by_badge]:
        if ex and (ex.id == 1 or ex.role == "Admin" or ex.username == 'admin'):
            return RedirectResponse(url="/users?error=No+es+posible+utilizar+los+datos+asociados+al+Administrador+Principal.", status_code=status.HTTP_303_SEE_OTHER)

    # Regla: Si un usuario fue borrado previamente (inactivo) o se están reutilizando sus datos para recrearlo,
    # el sistema no debe tomarlo como datos existentes conflictivos y debe permitir al Administrador crearlo/recrearlo.
    target_user_to_reuse = None

    if existing_by_email:
        target_user_to_reuse = existing_by_email
        # Si la cédula ingresada ya existe en OTRA cuenta activa distinta:
        if existing_by_doc and existing_by_doc.id != target_user_to_reuse.id and existing_by_doc.is_active:
            return RedirectResponse(url="/users?error=El+número+de+documento+de+identidad+(cédula)+ya+se+encuentra+registrado+para+otro+usuario+activo.", status_code=status.HTTP_303_SEE_OTHER)
        # Si la placa ingresada ya existe en OTRA cuenta activa distinta:
        if existing_by_badge and existing_by_badge.id != target_user_to_reuse.id and existing_by_badge.is_active:
            return RedirectResponse(url="/users?error=El+número+de+placa+policial+ya+se+encuentra+registrado+para+otro+usuario+activo.", status_code=status.HTTP_303_SEE_OTHER)
    elif existing_by_doc:
        target_user_to_reuse = existing_by_doc
        # Si la placa ingresada ya existe en OTRA cuenta activa distinta:
        if existing_by_badge and existing_by_badge.id != target_user_to_reuse.id and existing_by_badge.is_active:
            return RedirectResponse(url="/users?error=El+número+de+placa+policial+ya+se+encuentra+registrado+para+otro+usuario+activo.", status_code=status.HTTP_303_SEE_OTHER)
    elif existing_by_badge:
        target_user_to_reuse = existing_by_badge

    # 6. Sede territorial: la misma con la que ingresó el Administrador
    current_site = get_current_site(request)
    assigned_sede = current_site["full_name"]

    # 7. Generar contraseña temporal segura garantizando que sea única en el sistema (vigencia 24h)
    assigned_pass = generate_temp_password()
    while is_password_already_in_use(assigned_pass, db):
        assigned_pass = generate_temp_password()
    temp_expires = get_local_now() + datetime.timedelta(hours=24)
    must_change = True

    hashed_pw = get_password_hash(assigned_pass)

    if target_user_to_reuse:
        # Reutilizar y actualizar limpiamente la cuenta existente (permite recreación fluida)
        target_user_to_reuse.username = clean_email
        target_user_to_reuse.email = clean_email
        target_user_to_reuse.full_name = clean_fullname
        target_user_to_reuse.document_id = clean_doc
        target_user_to_reuse.badge_number = clean_badge
        target_user_to_reuse.assigned_site = assigned_sede
        target_user_to_reuse.hashed_password = hashed_pw
        target_user_to_reuse.role = role
        target_user_to_reuse.is_active = True
        target_user_to_reuse.must_change_password = must_change
        target_user_to_reuse.temp_expires_at = temp_expires
        new_user = target_user_to_reuse
        db.commit()
        db.refresh(new_user)
    else:
        new_user = User(
            username=clean_email,
            email=clean_email,
            full_name=clean_fullname,
            document_id=clean_doc,
            badge_number=clean_badge,
            assigned_site=assigned_sede,
            hashed_password=hashed_pw,
            role=role,
            is_active=True,
            must_change_password=must_change,
            temp_expires_at=temp_expires
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

    # Enviar correo institucional con la clave temporal de acceso
    send_temporary_password_email(
        to_email=clean_email,
        full_name=clean_fullname,
        temp_password=assigned_pass,
        site_name=assigned_sede,
        badge_number=clean_badge
    )

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="USER_CREATED_WEB",
        details={
            "created_user_id": new_user.id,
            "created_email": clean_email,
            "full_name": clean_fullname,
            "document_id": clean_doc,
            "badge_number": clean_badge,
            "role": role,
            "assigned_site": assigned_sede,
            "temp_expires_at": temp_expires.isoformat() if temp_expires else None
        }
    )
    db.commit()

    params = urllib.parse.urlencode({
        "created_name": clean_fullname,
        "created_doc": clean_doc,
        "created_badge": clean_badge or "",
        "created_user": clean_email,
        "created_pass": assigned_pass,
        "created_role": role,
        "created_site": assigned_sede
    })
    return RedirectResponse(url=f"/users?{params}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/users/me/profile")
def update_admin_profile(
    request: Request,
    full_name: str = Form(...),
    document_id: str = Form(...),
    email: str = Form(...),
    new_password: Optional[str] = Form(None),
    confirm_password: Optional[str] = Form(None),
    signature_data: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Permite al Administrador actualizar voluntariamente sus datos personales (nombre, cédula, correo, contraseña, firma digital) preservando su rol de Administrador."""
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    if current_user.role != "Admin":
        return RedirectResponse(url="/users?error=Solo+un+administrador+puede+modificar+estos+datos", status_code=status.HTTP_303_SEE_OTHER)

    if get_current_site(request).get("id") == "sitio-prueba" or current_user.username == "admin_demo" or request.cookies.get("is_demo_session") == "true":
        return RedirectResponse(url="/dashboard?error=Opción+deshabilitada+por+seguridad+en+el+entorno+Demo.", status_code=status.HTTP_303_SEE_OTHER)

    clean_fullname = full_name.strip()
    clean_doc = document_id.strip()
    clean_email = email.strip().lower()

    # 1. Validar letras en nombre
    if not re.match(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]+$", clean_fullname):
        return RedirectResponse(url="/users?error=El+nombre+completo+solo+puede+contener+letras+y+espacios.&edit_profile=1", status_code=status.HTTP_303_SEE_OTHER)

    # 2. Validar números en documento
    if not clean_doc.isdigit():
        return RedirectResponse(url="/users?error=El+documento+de+identidad+debe+contener+solo+números+(sin+puntos+ni+espacios).&edit_profile=1", status_code=status.HTTP_303_SEE_OTHER)

    # 2.1 Validar que la cédula no esté en uso por otra cuenta
    existing_doc = db.query(User).filter(
        User.document_id == clean_doc,
        User.id != current_user.id
    ).first()
    if existing_doc:
        return RedirectResponse(url="/users?error=El+número+de+documento+de+identidad+(cédula)+ya+se+encuentra+asociado+a+otra+cuenta.&edit_profile=1", status_code=status.HTTP_303_SEE_OTHER)

    # 3. Validar registros DNS MX del correo si cambió
    if clean_email != (current_user.email or "").lower():
        is_valid_mx, mx_err = check_email_mx_records(clean_email)
        if not is_valid_mx:
            encoded_err = urllib.parse.quote(mx_err)
            return RedirectResponse(url=f"/users?error={encoded_err}&edit_profile=1", status_code=status.HTTP_303_SEE_OTHER)

        # Validar que no esté en uso por otra cuenta
        existing_user = db.query(User).filter(
            (User.email == clean_email) | (User.username == clean_email),
            User.id != current_user.id
        ).first()
        if existing_user:
            return RedirectResponse(url="/users?error=El+correo+electrónico+ya+está+asociado+a+otra+cuenta.&edit_profile=1", status_code=status.HTTP_303_SEE_OTHER)

    # 4. Validar contraseña si se proporcionó una nueva
    if new_password and new_password.strip():
        if len(new_password) < 6:
            return RedirectResponse(url="/users?error=La+nueva+contraseña+debe+tener+al+menos+6+caracteres.&edit_profile=1", status_code=status.HTTP_303_SEE_OTHER)
        if new_password != confirm_password:
            return RedirectResponse(url="/users?error=Las+contraseñas+ingresadas+no+coinciden.&edit_profile=1", status_code=status.HTTP_303_SEE_OTHER)
        if verify_password(new_password, current_user.hashed_password):
            return RedirectResponse(url="/users?error=La+nueva+contraseña+no+puede+ser+igual+a+tu+contraseña+actual.&edit_profile=1", status_code=status.HTTP_303_SEE_OTHER)
        if is_password_already_in_use(new_password, db, exclude_user_id=current_user.id):
            return RedirectResponse(url="/users?error=La+contraseña+ingresada+ya+se+encuentra+registrada+en+el+sistema+para+otro+usuario.&edit_profile=1", status_code=status.HTTP_303_SEE_OTHER)
        current_user.hashed_password = get_password_hash(new_password)

    # 4.1 Validar y procesar firma digital del Administrador
    if signature_data and signature_data.strip():
        try:
            from app.utils.signature import save_signature_image
            sig_path = save_signature_image(signature_data, current_user.id)
            current_user.signature_path = sig_path
        except Exception as e_sig:
            encoded_err = urllib.parse.quote(f"Error procesando firma digital: {str(e_sig)}")
            return RedirectResponse(url=f"/users?error={encoded_err}&edit_profile=1", status_code=status.HTTP_303_SEE_OTHER)
    elif not current_user.signature_path:
        return RedirectResponse(
            url="/users?error=La+firma+digital+es+obligatoria+para+el+Administrador.+Debes+dibujarla+o+cargar+una+imagen.&edit_profile=1",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # 5. Actualizar datos (el rol NO cambia, permanece Admin)
    current_user.full_name = clean_fullname
    current_user.document_id = clean_doc
    current_user.email = clean_email
    current_user.username = clean_email
    db.commit()

    create_audit_log(
        db,
        user_id=current_user.id,
        username=clean_email,
        action="ADMIN_PROFILE_UPDATED",
        details={"full_name": clean_fullname, "document_id": clean_doc, "email": clean_email}
    )
    db.commit()

    # Re-generar token JWT con el email actualizado
    access_token = create_access_token(data={"sub": clean_email})

    response = RedirectResponse(url="/users?msg=Tus+datos+de+administrador+han+sido+actualizados+exitosamente.", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax"
    )
    return response


@app.post("/users/{user_id}/toggle-active")
def toggle_user_active_web(
    user_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Activa o desactiva una cuenta de usuario (Exclusivo Administrador Principal)."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    if not is_main_admin(current_user):
        return RedirectResponse(url="/users?error=Solo+el+Administrador+Principal+puede+activar+o+suspender+cuentas+de+usuario", status_code=status.HTTP_303_SEE_OTHER)

    if user_id == current_user.id:
        return RedirectResponse(url="/users?error=No+puedes+desactivar+tu+propia+cuenta+de+administrador", status_code=status.HTTP_303_SEE_OTHER)

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        return RedirectResponse(url="/users?error=Usuario+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)

    if user_id == 1 or target_user.username == 'admin':
        return RedirectResponse(url="/users?error=La+cuenta+del+Administrador+Inicial+del+sistema+no+puede+ser+desactivada", status_code=status.HTTP_303_SEE_OTHER)

    # Si se va a activar la cuenta y no es Admin, validar el límite de licencia
    if not target_user.is_active and target_user.role != "Admin":
        try:
            verify_user_limit(db)
        except HTTPException as exc:
            return RedirectResponse(url=f"/users?error={urllib.parse.quote(exc.detail)}", status_code=status.HTTP_303_SEE_OTHER)

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


@app.post("/users/{user_id}/delete")
def delete_user_web(
    user_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Elimina permanentemente una cuenta de usuario institucional (Exclusivo Administrador Principal)."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    if not is_main_admin(current_user):
        return RedirectResponse(url="/users?error=Solo+el+Administrador+Principal+puede+eliminar+cuentas+de+usuario", status_code=status.HTTP_303_SEE_OTHER)

    if user_id == current_user.id:
        return RedirectResponse(url="/users?error=No+puedes+eliminar+tu+propia+cuenta+de+administrador", status_code=status.HTTP_303_SEE_OTHER)

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        return RedirectResponse(url="/users?error=Usuario+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)

    if user_id == 1 or target_user.username == 'admin':
        return RedirectResponse(url="/users?error=La+cuenta+del+Administrador+Inicial+del+sistema+no+puede+ser+eliminada", status_code=status.HTTP_303_SEE_OTHER)

    target_username = target_user.username
    target_name = target_user.full_name or target_username

    # PRESERVAR INTEGRIDAD HISTÓRICA COMPLETA CONFORME A REQUERIMIENTO:
    # 1. NO desvincular las referencias de auditoría en Incident, Maintenance ni Event
    #    (Se conservan intactos validator_id, closed_by_id, completed_by_id, created_by_id)
    # 2. NO borrar el archivo físico de firma digital (signature_path) para que las actas oficiales,
    #    certificados PDF, trazabilidad y el informe ejecutivo continúen mostrando la firma y datos auténticos.

    # 3. Marcar la cuenta como eliminada e inactiva
    now = get_local_now()
    target_user.is_deleted = True
    target_user.is_active = False
    target_user.deleted_at = now

    # 4. Modificar el email, username y placa con sufijo de eliminación para liberar
    #    las restricciones de unicidad (unique constraints) en la base de datos, permitiendo
    #    que en el futuro el Administrador pueda registrar a un nuevo usuario con ese mismo correo/documento/placa.
    ts = int(now.timestamp())
    if not target_user.username.startswith("deleted_"):
        target_user.username = f"deleted_{ts}_{target_user.username}"
    if not target_user.email.startswith("deleted_"):
        target_user.email = f"deleted_{ts}_{target_user.email}"
    if target_user.badge_number and not target_user.badge_number.startswith("del_"):
        target_user.badge_number = f"del_{ts}_{target_user.badge_number}"

    db.commit()

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="USER_DELETED_WEB",
        details={"deleted_user_id": user_id, "deleted_username": target_username, "preserved_historical_data": True}
    )
    db.commit()

    return RedirectResponse(url=f"/users?msg=La+cuenta+de+{urllib.parse.quote(target_name)}+ha+sido+eliminada+exitosamente.+Sus+firmas+y+registros+históricos+han+sido+preservados+en+actas+y+trazabilidad.", status_code=status.HTTP_303_SEE_OTHER)


# ----------------- 7.5 Gestión y Administración de Licencias del Sistema por Sitio -----------------

@app.get("/license", response_class=HTMLResponse)
def license_view(
    request: Request,
    msg: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Panel de administración y activación de licencias exclusivo para la sede actual activa.
    Aislamiento estricto: Cada sitio solo visualiza y gestiona su propia licencia.
    """
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    if current_user.role != "Admin":
        return RedirectResponse(url="/dashboard?error=Acceso+restringido:+La+opción+de+licencias+es+exclusiva+del+Administrador.", status_code=status.HTTP_303_SEE_OTHER)

    from app.services.site_license_service import (
        get_site_license_status,
        record_site_first_access
    )

    # La sede es única y exclusivamente la sede territorial actualmente activa en la sesión
    current_site = get_current_site(request, db=db)
    if current_site.get("id") == "sitio-prueba" or current_user.username == "admin_demo" or request.cookies.get("is_demo_session") == "true":
        return RedirectResponse(url="/dashboard?error=Opción+deshabilitada+por+seguridad+en+el+entorno+Demo.", status_code=status.HTTP_303_SEE_OTHER)
    target_site_id = current_site["id"]

    # Registrar primer acceso del sitio si aplica
    record_site_first_access(db, target_site_id)

    # Estado detallado ÚNICAMENTE de la sede territorial activa
    target_status = get_site_license_status(db, target_site_id)

    return templates.TemplateResponse(
        request=request,
        name="license.html",
        context={
            "current_user": current_user,
            "current_site": current_site,
            "site_status": target_status,
            "active_page": "license",
            "dev_mode": settings.DEV_MODE,
            "msg": msg,
            "error": error
        }
    )


@app.post("/license/activate", response_class=HTMLResponse)
def license_activate_web(
    request: Request,
    password_key: str = Form(...),
    site_id: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Procesa la validación y activación de la contraseña de 16 dígitos exclusivamente para la sede activa."""
    if not current_user or current_user.role != "Admin":
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    # Bloquear activación a la sede territorial activa en sesión
    current_site = get_current_site(request, db=db)
    if current_site.get("id") == "sitio-prueba" or current_user.username == "admin_demo" or request.cookies.get("is_demo_session") == "true":
        return RedirectResponse(url="/dashboard?error=Opción+deshabilitada+por+seguridad+en+el+entorno+Demo.", status_code=status.HTTP_303_SEE_OTHER)
    clean_site_id = current_site["id"]

    from app.services.site_license_service import activate_site_year_license

    success, message, details = activate_site_year_license(
        db=db,
        site_id=clean_site_id,
        password_input=password_key.strip(),
        user=current_user
    )

    if success:
        return RedirectResponse(
            url=f"/license?msg={urllib.parse.quote_plus(message)}",
            status_code=status.HTTP_303_SEE_OTHER
        )
    else:
        return RedirectResponse(
            url=f"/license?error={urllib.parse.quote_plus(message)}",
            status_code=status.HTTP_303_SEE_OTHER
        )


# ----------------- 8. Rutas Operativas: Incidentes (Filtrado por Sede) -----------------

@app.get("/incidents", response_class=HTMLResponse)
def incidents_view(
    request: Request,
    page: int = Query(1, ge=1, description="Número de página actual"),
    page_size: int = Query(1000, ge=1, le=5000, description="Cantidad de incidentes por página"),
    created_ticket_id: Optional[int] = Query(None, description="ID del ticket recién creado para confirmación"),
    msg: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Vista web operativa de incidentes con paginación obligatoria y priorización optimizada en base de datos."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request, db=db)

    lic_redirect = check_site_access_or_redirect(request, current_user, current_site, db)
    if lic_redirect:
        return lic_redirect

    # Consulta base filtrada por la sede activa
    incidents_base = db.query(Incident).filter(
        get_site_filter_conditions(Incident, current_site)
    )
    total_records = incidents_base.count()
    effective_page_size = max(page_size, total_records) if total_records > 0 else page_size
    total_pages = (total_records + effective_page_size - 1) // effective_page_size if total_records > 0 else 1
    current_page = min(page, total_pages) if total_records > 0 else 1
    offset = (current_page - 1) * effective_page_size

    resolved_statuses = ["Cerrado", "Resuelto", "Validado / Conforme", "Conforme / Validado"]
    active_statuses = ["Abierto", "En Proceso", "Pendiente de Validación", "Rechazado"]

    all_site_incidents = incidents_base.all()

    # Métrica exclusiva: SLA sobre tickets SOLAMENTE RESUELTOS
    resolved_incidents = [
        inc for inc in all_site_incidents 
        if inc.status in resolved_statuses or getattr(inc, 'is_resolved', False)
    ]
    resolved_total = len(resolved_incidents)
    resolved_sla_within = sum(1 for inc in resolved_incidents if not inc.is_overtime)
    resolved_sla_overdue = sum(1 for inc in resolved_incidents if inc.is_overtime)
    resolved_sla_rate = round((resolved_sla_within / resolved_total) * 100, 1) if resolved_total > 0 else 0.0

    # Métrica global: SLA sobre todos los tickets registrados
    sla_within = sum(1 for inc in all_site_incidents if not inc.is_overtime)
    sla_overdue = sum(1 for inc in all_site_incidents if inc.is_overtime)
    sla_rate = round((sla_within / total_records) * 100, 1) if total_records > 0 else 0.0

    site_kpis = {
        # 1. Panorama Operativo y Ciclo de Vida
        "total_records": total_records,
        "active_total": incidents_base.filter(Incident.status.in_(active_statuses)).count(),
        "open_total": incidents_base.filter(Incident.status == "Abierto").count(),
        "in_process": incidents_base.filter(Incident.status == "En Proceso").count(),
        "pending_validation": incidents_base.filter(Incident.status.in_(["Pendiente de Validación", "Pendiente de Validación Policial"])).count(),
        "closed_total": incidents_base.filter(Incident.status.in_(resolved_statuses)).count(),
        # 2. Nueva Métrica: SLA de Tickets Solamente Resueltos
        "resolved_total": resolved_total,
        "resolved_sla_within": resolved_sla_within,
        "resolved_sla_overdue": resolved_sla_overdue,
        "resolved_sla_rate": resolved_sla_rate,
        # 3. Cumplimiento de Niveles de Servicio (SLA Global)
        "sla_within": sla_within,
        "sla_overdue": sla_overdue,
        "sla_rate": sla_rate,
        # 4. Panorama Completo por Tipo de Falla / Severidad
        "critical_total": incidents_base.filter(Incident.fault_type == "Falla Crítica").count(),
        "critical_open": incidents_base.filter(Incident.fault_type == "Falla Crítica", Incident.status.in_(active_statuses)).count(),
        "change_total": incidents_base.filter(Incident.fault_type == "Cambio").count(),
        "change_open": incidents_base.filter(Incident.fault_type == "Cambio", Incident.status.in_(active_statuses)).count(),
        "minor_total": incidents_base.filter(Incident.fault_type == "Falla Menor").count(),
        "minor_open": incidents_base.filter(Incident.fault_type == "Falla Menor", Incident.status.in_(active_statuses)).count(),
        "inactive_total": incidents_base.filter(Incident.fault_type == "Inactivo").count(),
        "inactive_open": incidents_base.filter(Incident.fault_type == "Inactivo", Incident.status.in_(active_statuses)).count(),
    }

    # Paginación y ordenamiento optimizado:
    # 1. Incidentes activos primero (Abierto, En Proceso), luego cerrados/resueltos
    # 2. Por criticidad y severidad dentro de los abiertos
    # 3. Por fecha de creación más reciente
    incidents_list = incidents_base.order_by(
        case((Incident.status.in_(active_statuses), 0), else_=1),
        case(
            (Incident.priority == "Crítica", 0),
            (Incident.fault_type == "Falla Crítica", 0),
            (Incident.priority == "Alta", 1),
            (Incident.fault_type == "Inactivo", 2),
            (Incident.priority == "Media", 3),
            else_=4
        ),
        Incident.created_at.desc()
    ).offset(offset).limit(effective_page_size).all()

    devices_list = db.query(Device).filter(
        get_site_filter_conditions(Device, current_site)
    ).order_by(Device.name.asc()).all()

    # Extraer sitios físicos específicos del municipio activo
    db_points = [d.location_detail.strip() for d in devices_list if d.location_detail and d.location_detail.strip()]
    default_points = [
        'Parque Arqueológico',
        'Colegio CRRC',
        'Estación de Policía',
        'Carabineros',
        'Terminal de Transportes',
        'Cuatro Vientos',
        'Barrio Kennedy'
    ]
    physical_sites = []
    for pt in default_points:
        if pt not in physical_sites:
            physical_sites.append(pt)
    for pt in db_points:
        if pt not in physical_sites:
            physical_sites.append(pt)

    site_sedes = [s for s in SEDES_CATALOG if s.get("site_id") == current_site["id"]]

    devices_data = [
        {
            "id": d.id,
            "name": d.name,
            "type": d.device_type,
            "location": d.location_detail or "",
            "brand": d.brand or "",
            "serial": d.serial_number or "",
            "status": d.calculated_status
        }
        for d in devices_list
    ]
    devices_json = json.dumps(devices_data, ensure_ascii=False)
    pending_validation_count = (
        incidents_base.filter(Incident.status == "Pendiente de Validación").count()
        + db.query(Maintenance).filter(
            get_site_filter_conditions(Maintenance, current_site),
            Maintenance.status == "Pendiente de Validación"
        ).count()
    )

    created_incident = None
    if created_ticket_id:
        created_incident = db.query(Incident).filter(Incident.id == created_ticket_id).first()

    return templates.TemplateResponse(
        request=request,
        name="incidents.html",
        context={
            "current_user": current_user,
            "current_site": current_site,
            "available_sites": get_available_sites(db, active_only=True),
            "active_page": "incidents",
            "incidents": incidents_list,
            "site_kpis": site_kpis,
            "devices": devices_list,
            "devices_json": devices_json,
            "sedes": site_sedes,
            "physical_sites": physical_sites,
            "page": current_page,
            "page_size": page_size,
            "total_records": total_records,
            "total_pages": total_pages,
            "has_prev": current_page > 1,
            "has_next": current_page < total_pages,
            "pending_validation_count": pending_validation_count,
            "created_incident": created_incident,
            "msg": msg,
            "error": error
        }
    )


@app.post("/incidents")
async def create_incident_web(
    request: Request,
    fault_type: str = Form("Falla Menor"),
    priority: str = Form("Media"),
    location_detail: str = Form(...),
    custom_location: Optional[str] = Form(None),
    device_id: Optional[str] = Form(None),
    description: str = Form(...),
    photo: Optional[UploadFile] = File(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Procesa el reporte de un nuevo incidente en el municipio activo con serial/ticket y título correctivo autogenerado."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    if current_user.role == "Supervisor":
        err = urllib.parse.quote("Acceso denegado: El rol Supervisor tiene perfil de solo lectura y no puede crear tickets de incidentes.")
        return RedirectResponse(url=f"/incidents?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    current_site = get_current_site(request)
    assigned_sede = current_site["full_name"]
    image_path = await save_uploaded_photo(photo)
    parsed_device_id = int(device_id) if device_id and device_id.strip() else None

    # Determinar sitio físico
    final_location = custom_location.strip() if (location_detail == "Otro" and custom_location and custom_location.strip()) else location_detail.strip()

    # Generación de Serial / Ticket único
    year = get_local_now().year
    count = db.query(Incident).filter(Incident.ticket_number.like(f"TKT-{year}-%")).count()
    ticket_number = f"TKT-{year}-{count + 1:04d}"
    while db.query(Incident).filter(Incident.ticket_number == ticket_number).first():
        count += 1
        ticket_number = f"TKT-{year}-{count + 1:04d}"

    # Buscar nombre del equipo si fue seleccionado o resolverlo automáticamente según el punto físico
    device_obj = None
    if parsed_device_id:
        device_obj = db.query(Device).filter(Device.id == parsed_device_id).first()
    elif final_location:
        device_obj = (
            db.query(Device).filter(
                Device.sede == assigned_sede,
                Device.location_detail.ilike(f"%{final_location}%"),
                Device.device_type.ilike("%cámara%")
            ).first()
            or db.query(Device).filter(
                Device.sede == assigned_sede,
                Device.location_detail.ilike(f"%{final_location}%")
            ).first()
            or db.query(Device).filter(
                Device.location_detail.ilike(f"%{final_location}%"),
                Device.device_type.ilike("%cámara%")
            ).first()
            or db.query(Device).filter(
                Device.location_detail.ilike(f"%{final_location}%")
            ).first()
        )
        if device_obj:
            parsed_device_id = device_obj.id

    # Generación automática de título de Mantenimiento Correctivo
    dev_suffix = f" [{device_obj.name}]" if device_obj else ""
    title = f"Mantenimiento Correctivo - {fault_type} - {final_location}{dev_suffix}"

    new_incident = Incident(
        ticket_number=ticket_number,
        title=title,
        description=description.strip(),
        priority=priority,
        fault_type=fault_type,
        location_detail=final_location,
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
        description=f"Ticket {ticket_number} reportado para {final_location} ({fault_type}) por {current_user.full_name or current_user.username}."
    )
    db.add(creation_event)

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="INCIDENT_CREATED_WEB",
        details={
            "incident_id": new_incident.id,
            "ticket_number": ticket_number,
            "title": new_incident.title,
            "fault_type": fault_type,
            "location_detail": final_location,
            "sede": assigned_sede,
            "device_id": parsed_device_id
        }
    )
    db.commit()

    return RedirectResponse(url=f"/incidents?created_ticket_id={new_incident.id}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/incidents/{incident_id}/status")
def update_incident_status_web(
    incident_id: int,
    request: Request,
    new_status: str = Form(..., alias="status"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Actualiza el estado de un incidente (atención o avance de ciclo)."""
    referer = request.headers.get("referer", "")
    if "/validation" in referer:
        err = urllib.parse.quote("En Validación Policial el Administrador y la Empresa de Mantenimiento solo tienen acceso de observación. Gestione 'Atender' en el módulo Incidentes.")
        return RedirectResponse(url=f"/validation?error={err}", status_code=status.HTTP_303_SEE_OTHER)
    target_base = "/incidents"

    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        return RedirectResponse(url=target_base, status_code=status.HTTP_303_SEE_OTHER)

    # 1. Bloqueo estricto para el personal técnico si la orden está pendiente de validación o validada
    if incident.status in ["Pendiente de Validación", "Validado / Conforme", "Conforme / Validado"] and current_user.role not in ["Admin", "Validador"]:
        return RedirectResponse(
            url=f"{target_base}?error=La+orden+de+trabajo+{incident.ticket_code}+se+encuentra+en+estado+'{urllib.parse.quote(incident.status)}'+y+la+edición+técnica+está+bloqueada.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    if current_user.role == "Supervisor":
        err = urllib.parse.quote("Acceso denegado: El rol Supervisor tiene perfil de solo lectura y no puede modificar el estado de los tickets.")
        return RedirectResponse(url=f"{target_base}?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    allowed_roles = ["Admin", "Operario", "Responsable", "Empresa de Mantenimiento"]
    if current_user.role not in allowed_roles:
        return RedirectResponse(url=target_base, status_code=status.HTTP_303_SEE_OTHER)

    old_status = incident.status
    if old_status != new_status:
        incident.status = new_status
        incident.updated_at = get_local_now()

        if new_status == "En Proceso":
            incident.attended_at = get_local_now()
            incident.assigned_to_id = current_user.id

        if new_status in ["Cerrado", "Validado / Conforme"]:
            incident.closed_at = get_local_now()
            incident.closed_by_id = current_user.id

        db.add(Event(
            incident_id=incident.id,
            user_id=current_user.id,
            event_type="STATUS_CHANGE",
            description=f"Estado del Ticket {incident.ticket_code} cambiado de '{old_status}' a '{new_status}' por {current_user.full_name or current_user.username}."
        ))

        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="INCIDENT_STATUS_CHANGE",
            details={"incident_id": incident.id, "ticket_number": incident.ticket_code, "old_status": old_status, "new_status": new_status}
        )
        db.commit()

    return RedirectResponse(url=f"{target_base}?msg=Ticket+{incident.ticket_code}+en+proceso+de+atención+técnica.", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/incidents/{incident_id}/close")
async def close_incident_web(
    incident_id: int,
    request: Request,
    root_cause: str = Form(...),
    solution: str = Form(...),
    closing_photo: Optional[UploadFile] = File(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Cierre técnico de incidente que cambia automáticamente a 'Pendiente de Validación' para revisión policial."""
    referer = request.headers.get("referer", "")
    if "/validation" in referer:
        err = urllib.parse.quote("En Validación Policial el Administrador y la Empresa de Mantenimiento solo tienen acceso de observación. Gestione 'Finalizar y Remitir' en el módulo Incidentes.")
        return RedirectResponse(url=f"/validation?error={err}", status_code=status.HTTP_303_SEE_OTHER)
    target_base = "/incidents"

    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        return RedirectResponse(url=target_base, status_code=status.HTTP_303_SEE_OTHER)

    if incident.status in ["Pendiente de Validación", "Validado / Conforme", "Conforme / Validado"] and current_user.role not in ["Admin", "Validador"]:
        return RedirectResponse(
            url=f"{target_base}?error=La+orden+de+trabajo+{incident.ticket_code}+se+encuentra+en+estado+'{urllib.parse.quote(incident.status)}'+y+la+edición+técnica+está+bloqueada.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    if current_user.role == "Supervisor":
        err = urllib.parse.quote("Acceso denegado: El rol Supervisor tiene perfil de solo lectura y no puede cerrar ni finalizar tickets.")
        return RedirectResponse(url=f"{target_base}?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    allowed_roles = ["Admin", "Operario", "Responsable", "Empresa de Mantenimiento"]
    if current_user.role not in allowed_roles:
        return RedirectResponse(url=target_base, status_code=status.HTTP_303_SEE_OTHER)

    if incident.status in ["Abierto", "Rechazado"]:
        err = urllib.parse.quote(f"Debe iniciar primero la atención del ticket {incident.ticket_code} haciendo clic en 'Atender' antes de finalizar y remitir.")
        return RedirectResponse(url=f"{target_base}?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    closing_image_path = await save_uploaded_photo(closing_photo)
    if not closing_image_path:
        err = urllib.parse.quote("Debe cargar la fotografía de evidencia que soporta la finalización y remisión a validación.")
        return RedirectResponse(url=f"{target_base}?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    # Transición automática a Pendiente de Validación
    incident.status = "Pendiente de Validación"
    incident.validation_status = "Pendiente"
    incident.closed_at = get_local_now()
    incident.closed_by_id = current_user.id
    incident.root_cause = root_cause.strip()
    incident.solution = solution.strip()
    incident.closing_image_path = closing_image_path
    incident.validator_id = None
    incident.validated_at = None
    incident.updated_at = get_local_now()

    db.add(Event(
        incident_id=incident.id,
        user_id=current_user.id,
        event_type="INCIDENT_PENDING_VALIDATION",
        description=f"Ticket {incident.ticket_code} finalizado por técnico {current_user.full_name or current_user.username} y remitido a Pendiente de Validación Policial."
    ))

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="INCIDENT_SUBMITTED_VALIDATION",
        details={
            "incident_id": incident.id,
            "ticket_number": incident.ticket_code,
            "closed_by": current_user.username,
            "root_cause": root_cause.strip(),
            "solution": solution.strip(),
            "status": incident.status
        }
    )
    db.commit()

    return RedirectResponse(
        url=f"{target_base}?msg=Ticket+{incident.ticket_code}+marcado+como+finalizado.+Ha+pasado+a+estado+'Pendiente+de+Validación'+para+revisión+y+firma+de+la+Estación+de+Policía.",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/incidents/{incident_id}/validate")
async def validate_incident_web(
    incident_id: int,
    request: Request,
    action: str = Form(...),  # "approve" or "reject"
    validation_notes: Optional[str] = Form(None),
    rejection_photo: Optional[UploadFile] = File(None),
    redirect_to: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Dictamen formal y certificación del Validador sobre un incidente (mantenimiento correctivo):
    - 'approve': Certifica conformidad técnica ('Validado / Conforme').
    - 'reject': Devuelve la orden al técnico con observaciones y reinicia el ticket con tiempo cero.
    """
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    referer = request.headers.get("referer", "")
    if "/incidents" in referer and redirect_to != "/validation":
        err = urllib.parse.quote("El validador solo puede validar un ticket desde la opción 'Validación Policial'.")
        return RedirectResponse(url=f"/incidents?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    target_redirect = redirect_to or "/validation"

    if current_user.role != "Validador":
        return RedirectResponse(
            url=f"{target_redirect}?error=Acceso+denegado:+Solo+el+rol+Validador+(Policía+Nacional)+tiene+permisos+para+revisar+y+validar+trabajos+técnicos.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        return RedirectResponse(
            url=f"{target_redirect}?error=Incidente+no+encontrado",
            status_code=status.HTTP_303_SEE_OTHER
        )

    now = get_local_now()

    if action == "approve":
        incident.status = "Validado / Conforme"
        incident.validation_status = "Conforme"
        incident.validator_id = current_user.id
        incident.validated_at = now
        incident.validation_notes = (
            validation_notes.strip()
            if validation_notes and validation_notes.strip()
            else "Trabajo correctivo revisado, verificado y validado formalmente conforme a los estándares técnicos y evidencias fotográficas."
        )

        badge_txt = f" (Placa #{current_user.badge_number})" if current_user.badge_number else ""
        db.add(Event(
            incident_id=incident.id,
            user_id=current_user.id,
            event_type="INCIDENT_VALIDATED",
            description=f"Ticket {incident.ticket_code} aprobado con visto bueno técnico y conformidad por Validador {current_user.full_name or current_user.username}{badge_txt}."
        ))

        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="INCIDENT_VALIDATED_WEB",
            details={
                "incident_id": incident.id,
                "ticket_code": incident.ticket_code,
                "validator": current_user.username,
                "badge_number": current_user.badge_number,
                "status": incident.status,
                "notes": incident.validation_notes
            }
        )
        db.commit()
        return RedirectResponse(
            url=f"{target_redirect}?msg=Ticket+{incident.ticket_code}+Aprobado+con+éxito.+Se+ha+certificado+su+Conformidad+técnica+policial.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    elif action == "reject":
        if not validation_notes or not validation_notes.strip():
            return RedirectResponse(
                url=f"{target_redirect}?error=Debe+especificar+las+observaciones+técnicas+de+rechazo+para+que+el+equipo+de+mantenimiento+pueda+subsanar.",
                status_code=status.HTTP_303_SEE_OTHER
            )

        rejection_photo_path = await save_uploaded_photo(rejection_photo)
        if rejection_photo_path:
            incident.rejection_photo = rejection_photo_path

        # Reinicio del ticket desde el Paso 2 (se activa nuevamente Atender)
        incident.status = "Rechazado"
        incident.validation_status = "Rechazado"
        incident.validator_id = current_user.id
        incident.validated_at = now
        incident.validation_notes = validation_notes.strip()
        incident.timer_reset_at = now  # TIEMPO CERO
        incident.attended_at = None   # Reinicia atención para que vuelva a hacer clic en Atender (Paso 2)
        incident.closed_at = None     # Reabierto para que el equipo de mantenimiento regrese a corregir

        badge_txt = f" (Placa #{current_user.badge_number})" if current_user.badge_number else ""
        db.add(Event(
            incident_id=incident.id,
            user_id=current_user.id,
            event_type="INCIDENT_REJECTED",
            description=f"Ticket {incident.ticket_code} rechazado y devuelto a subsanación técnica con tiempo cero por Validador {current_user.full_name or current_user.username}{badge_txt}. Obs: {(incident.validation_notes or '')[:100]}"
        ))

        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="INCIDENT_REJECTED_WEB",
            details={
                "incident_id": incident.id,
                "ticket_code": incident.ticket_code,
                "validator": current_user.username,
                "status": incident.status,
                "notes": incident.validation_notes,
                "rejection_photo": rejection_photo_path,
                "timer_reset": True
            }
        )
        db.commit()
        return RedirectResponse(
            url=f"{target_redirect}?msg=Ticket+{incident.ticket_code}+Rechazado+y+devuelto+al+equipo+técnico+con+tiempo+cero+para+su+corrección.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    return RedirectResponse(url=target_redirect, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/incidents/{incident_id}/certificate.pdf")
def download_incident_certificate_pdf(
    incident_id: int,
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Descarga el Acta Oficial de Conformidad y Validación Técnica Policial para un incidente."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    # Restricción de seguridad: Administrador, Validador, Supervisor, Empresa de Mantenimiento y Operario
    if current_user.role not in ["Admin", "Validador", "Supervisor", "Empresa de Mantenimiento", "Operario"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso Denegado: Este informe técnico oficial de validación solo puede ser consultado por usuarios autorizados."
        )

    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incidente no encontrado.")

    if not incident.is_validated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La orden técnica aún no ha sido aprobada ni validada formalmente por la Estación de Policía."
        )

    # Resolver la sede técnica propia del incidente
    matched_site = None
    if incident.sede:
        incident_sede_norm = incident.sede.strip().lower()
        matched_site = next((s for s in AVAILABLE_SITES if s["name"].lower() in incident_sede_norm or s["full_name"].lower() in incident_sede_norm or incident_sede_norm in s["full_name"].lower()), None)

    if not matched_site:
        active_site_id = request.cookies.get("active_site", "san-agustin")
        matched_site = next((s for s in AVAILABLE_SITES if s["id"] == active_site_id), AVAILABLE_SITES[0])
    current_site = matched_site

    validator_user = incident.validator
    if not validator_user:
        validator_user = db.query(User).filter(User.role == "Validador", User.is_active == True, User.is_deleted == False).first() or current_user

    pdf_bytes = generate_validation_conformity_pdf(
        item=incident,
        item_type="incident",
        validator=validator_user,
        current_site=current_site
    )

    filename = f"Acta_Conformidad_Policial_{incident.ticket_code}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )


# ----------------- 9. Rutas Operativas: Mantenimientos Preventivos -----------------

@app.get("/maintenance", response_class=HTMLResponse)
@app.get("/maintenances", response_class=HTMLResponse)
def maintenance_view(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status"),
    created_maint_id: Optional[int] = Query(None, description="ID del mantenimiento recién creado para confirmación"),
    msg: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Vista web operativa de mantenimientos preventivos filtrada por el municipio activo."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request)

    lic_redirect = check_site_access_or_redirect(request, current_user, current_site, db)
    if lic_redirect:
        return lic_redirect

    maintenances_list = db.query(Maintenance).filter(
        get_site_filter_conditions(Maintenance, current_site)
    ).order_by(Maintenance.scheduled_date.asc()).all()

    active_incidents = db.query(Incident).filter(
        get_site_filter_conditions(Incident, current_site),
        Incident.status != "Cerrado"
    ).all()

    devices_list = db.query(Device).filter(
        get_site_filter_conditions(Device, current_site)
    ).order_by(Device.name.asc()).all()

    # Extraer sitios físicos específicos del municipio activo
    db_points = [d.location_detail.strip() for d in devices_list if d.location_detail and d.location_detail.strip()]
    default_points = [
        'Parque Arqueológico',
        'Colegio CRRC',
        'Estación de Policía',
        'Carabineros',
        'Terminal de Transportes',
        'Cuatro Vientos',
        'Barrio Kennedy'
    ]
    physical_sites = []
    for pt in default_points:
        if pt not in physical_sites:
            physical_sites.append(pt)
    for pt in db_points:
        if pt not in physical_sites:
            physical_sites.append(pt)

    devices_data = [
        {
            "id": d.id,
            "name": d.name,
            "type": d.device_type,
            "location": d.location_detail or "",
            "brand": d.brand or "",
            "serial": d.serial_number or "",
            "status": d.calculated_status
        }
        for d in devices_list
    ]
    devices_json = json.dumps(devices_data, ensure_ascii=False)

    pending_validation_count = sum(1 for m in maintenances_list if m.status == "Pendiente de Validación")
    total_maint = len(maintenances_list)

    maint_kpis = {
        "total_records": total_maint,
        "scheduled": sum(1 for m in maintenances_list if m.status == "Programado"),
        "in_progress": sum(1 for m in maintenances_list if m.status in ["En Ejecución", "En Ejecucion"]),
        "pending_validation": pending_validation_count,
        "validated_ok": sum(1 for m in maintenances_list if m.status in ["Validado / Conforme", "Conforme / Validado", "Completado", "Cerrado"]),
        "rejected": sum(1 for m in maintenances_list if m.status == "Rechazado"),
        "points_count": len(physical_sites),
        "devices_count": len(devices_list),
        "mensual_count": sum(1 for m in maintenances_list if (m.maintenance_type or "") == "Preventivo Mensual"),
        "rutinaria_count": sum(1 for m in maintenances_list if (m.maintenance_type or "") == "Inspección Rutinaria"),
    }

    created_maintenance = None
    if created_maint_id:
        created_maintenance = db.query(Maintenance).filter(Maintenance.id == created_maint_id).first()

    return templates.TemplateResponse(
        request=request,
        name="maintenances.html",
        context={
            "current_user": current_user,
            "current_site": current_site,
            "available_sites": AVAILABLE_SITES,
            "active_page": "maintenance",
            "maintenances": maintenances_list,
            "maint_kpis": maint_kpis,
            "active_incidents": active_incidents,
            "devices": devices_list,
            "devices_json": devices_json,
            "physical_sites": physical_sites,
            "initial_status": status_filter or "all",
            "pending_validation_count": pending_validation_count,
            "min_scheduled_date": get_local_now().strftime("%Y-%m-%dT00:00"),
            "created_maintenance": created_maintenance,
            "msg": msg,
            "error": error
        }
    )


@app.post("/maintenance")
@app.post("/maintenances")
async def create_maintenance_web(
    request: Request,
    type: str = Form("Preventivo"),
    maintenance_type: str = Form("Preventivo Mensual"),
    priority: str = Form("Media"),
    location_detail: str = Form(...),
    custom_location: Optional[str] = Form(None),
    device_id: Optional[str] = Form(None),
    incident_id: Optional[str] = Form(None),
    scheduled_date: str = Form(...),
    description: str = Form(...),
    technical_findings: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Procesa la programación de un nuevo mantenimiento preventivo con serial y título autogenerado."""
    type = "Preventivo"
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    if current_user.role == "Supervisor":
        err = urllib.parse.quote("Acceso denegado: El rol Supervisor tiene perfil de solo lectura y no puede programar protocolos de mantenimiento.")
        return RedirectResponse(url=f"/maintenance?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    current_site = get_current_site(request)
    assigned_sede = current_site["full_name"]

    try:
        clean_date_str = scheduled_date.strip().replace(" ", "T")
        parsed_date = datetime.datetime.fromisoformat(clean_date_str)
    except Exception:
        try:
            parsed_date = datetime.datetime.strptime(scheduled_date.strip(), "%d/%m/%Y %H:%M")
        except Exception:
            err = urllib.parse.quote("Formato de fecha y hora inválido para la programación del mantenimiento.")
            return RedirectResponse(url=f"/maintenance?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    if parsed_date.tzinfo is not None:
        parsed_date = parsed_date.replace(tzinfo=None)

    current_today = get_local_now().date()
    if parsed_date.date() < current_today:
        err = urllib.parse.quote(
            "No se permite programar una inspección rutinaria o un mantenimiento preventivo con fecha anterior a la fecha actual."
        )
        return RedirectResponse(url=f"/maintenance?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    image_path = await save_uploaded_photo(photo)

    parsed_incident_id = int(incident_id) if incident_id and incident_id.strip() else None
    parsed_device_id = int(device_id) if device_id and device_id.strip() else None

    # Determinar sitio físico
    final_location = custom_location.strip() if (location_detail == "Otro" and custom_location and custom_location.strip()) else location_detail.strip()

    # Generación de Serial / Código de Protocolo Preventivo único (MP-YYYY-XXXX)
    year = get_local_now().year
    count = db.query(Maintenance).filter(Maintenance.protocol_code.like(f"MP-{year}-%")).count()
    protocol_code = f"MP-{year}-{count + 1:04d}"
    while db.query(Maintenance).filter(Maintenance.protocol_code == protocol_code).first():
        count += 1
        protocol_code = f"MP-{year}-{count + 1:04d}"

    # Buscar nombre del equipo si fue seleccionado
    device_obj = None
    if parsed_device_id:
        device_obj = db.query(Device).filter(Device.id == parsed_device_id).first()

    # Generación automática de título de Mantenimiento
    dev_suffix = f" [{device_obj.name}]" if device_obj else ""
    title = f"Mantenimiento {type} - {maintenance_type} - {final_location}{dev_suffix}"

    new_maint = Maintenance(
        type=type,
        protocol_code=protocol_code,
        title=title,
        maintenance_type=maintenance_type,
        priority=priority,
        location_detail=final_location,
        description=description.strip(),
        technical_findings=technical_findings.strip() if technical_findings else None,
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
        description=f"Protocolo preventivo {protocol_code} programado ({maintenance_type}) para {final_location} por {current_user.full_name or current_user.username}."
    ))

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="MAINTENANCE_CREATED_WEB",
        details={
            "maintenance_id": new_maint.id,
            "protocol_code": protocol_code,
            "title": new_maint.title,
            "sede": assigned_sede,
            "location_detail": final_location,
            "device_id": parsed_device_id
        }
    )
    db.commit()

    return RedirectResponse(url=f"/maintenance?created_maint_id={new_maint.id}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/maintenance/{maintenance_id}/status")
def update_maintenance_status_web(
    maintenance_id: int,
    request: Request,
    new_status: str = Form(..., alias="status"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Actualiza el estado de un mantenimiento (p.ej. inicio de ejecución técnica en campo)."""
    referer = request.headers.get("referer", "")
    if "/validation" in referer:
        err = urllib.parse.quote("En Validación Policial el Administrador y la Empresa de Mantenimiento solo tienen acceso de observación. Gestione 'Iniciar Labores' en el módulo Mantenimientos.")
        return RedirectResponse(url=f"/validation?error={err}", status_code=status.HTTP_303_SEE_OTHER)
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.role == "Supervisor":
        err = urllib.parse.quote("Acceso denegado: El rol Supervisor tiene perfil de solo lectura y no puede modificar el estado de los mantenimientos.")
        return RedirectResponse(url=f"/maintenance?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    maint = db.query(Maintenance).filter(Maintenance.id == maintenance_id).first()
    if not maint:
        return RedirectResponse(url="/maintenance", status_code=status.HTTP_303_SEE_OTHER)

    # Bloqueo: un mantenimiento ya validado no puede cambiar de estado (salvo Admin o Validador)
    if maint.status in ["Validado / Conforme", "Conforme / Validado"] and current_user.role not in ["Admin", "Validador"]:
        err = urllib.parse.quote(f"La orden de trabajo {maint.code} ya fue validada y su estado no puede modificarse.")
        return RedirectResponse(url=f"/maintenance?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    old_status = maint.status
    if old_status != new_status:
        maint.status = new_status
        if new_status == "En Ejecución" and not maint.execution_date:
            maint.execution_date = get_local_now()
        elif new_status == "Completado":
            maint.completed_date = get_local_now()
            maint.completed_by_id = current_user.id

        db.add(Event(
            maintenance_id=maint.id,
            user_id=current_user.id,
            event_type="STATUS_CHANGE",
            description=f"Protocolo {maint.code} cambió a '{new_status}' por {current_user.full_name or current_user.username}."
        ))

        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="MAINTENANCE_STATUS_CHANGE",
            details={"maintenance_id": maint.id, "protocol_code": maint.code, "old_status": old_status, "new_status": new_status}
        )
        db.commit()

    return RedirectResponse(url="/maintenance", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/maintenance/{maintenance_id}/complete")
async def complete_maintenance_web(
    maintenance_id: int,
    request: Request,
    actions_taken: str = Form(...),
    recommendations: Optional[str] = Form(None),
    technical_findings: Optional[str] = Form(None),
    check_optica: Optional[str] = Form(None),
    check_voltajes: Optional[str] = Form(None),
    check_reapriete: Optional[str] = Form(None),
    check_ups: Optional[str] = Form(None),
    check_nvr: Optional[str] = Form(None),
    check_estanco: Optional[str] = Form(None),
    completion_photo: Optional[UploadFile] = File(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Cierre técnico y firma digital de protocolo de mantenimiento (Empresa de Mantenimiento o Admin) que remite a Pendiente de Validación."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    maint = db.query(Maintenance).filter(Maintenance.id == maintenance_id).first()
    if not maint:
        return RedirectResponse(url="/maintenance", status_code=status.HTTP_303_SEE_OTHER)

    # 1. Bloqueo estricto de edición para el técnico si está pendiente de validación o validado conforme
    if maint.status in ["Pendiente de Validación", "Validado / Conforme", "Conforme / Validado"] and current_user.role not in ["Admin", "Validador"]:
        return RedirectResponse(
            url=f"/maintenance?error=La+orden+de+trabajo+{maint.code}+se+encuentra+en+estado+'{urllib.parse.quote(maint.status)}'+y+la+edición+técnica+está+bloqueada.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    if current_user.role == "Supervisor":
        err = urllib.parse.quote("Acceso denegado: El rol Supervisor tiene perfil de solo lectura y no puede finalizar ni cerrar mantenimientos.")
        return RedirectResponse(url=f"/maintenance?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    allowed_roles = ["Admin", "Empresa de Mantenimiento", "Operario", "Responsable"]
    if current_user.role not in allowed_roles:
        return RedirectResponse(url="/maintenance?error=No+tienes+permisos+técnicos+para+finalizar+mantenimientos.", status_code=status.HTTP_303_SEE_OTHER)

    completion_photo_path = await save_uploaded_photo(completion_photo)

    checklist_dict = {
        "optica_limpieza": check_optica == "on",
        "voltajes_fuentes_poe": check_voltajes == "on",
        "reapriete_estructural": check_reapriete == "on",
        "autonomia_ups_planta": check_ups == "on",
        "grabacion_nvr_almacenamiento": check_nvr == "on",
        "empaques_estancos_sellado": check_estanco == "on"
    }

    # Transición automática a Pendiente de Validación
    maint.status = "Pendiente de Validación"
    maint.validation_status = "Pendiente"
    maint.completed_date = get_local_now()
    maint.completed_by_id = current_user.id
    maint.actions_taken = actions_taken.strip()
    if recommendations and recommendations.strip():
        maint.recommendations = recommendations.strip()
    if technical_findings and technical_findings.strip():
        maint.technical_findings = technical_findings.strip()
    maint.checklist_results = json.dumps(checklist_dict, ensure_ascii=False)
    if completion_photo_path:
        maint.completion_photo = completion_photo_path
    if not maint.execution_date:
        maint.execution_date = maint.completed_date

    # Reset de campos de validación previa (en caso de reapertura tras rechazo)
    maint.validator_id = None
    maint.validated_at = None
    maint.validation_notes = None

    db.add(Event(
        maintenance_id=maint.id,
        user_id=current_user.id,
        event_type="MAINTENANCE_PENDING_VALIDATION",
        description=f"Protocolo {maint.code} finalizado por técnico {current_user.full_name or current_user.username} y remitido a Pendiente de Validación."
    ))

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="MAINTENANCE_SUBMITTED_VALIDATION",
        details={
            "maintenance_id": maint.id,
            "protocol_code": maint.code,
            "completed_by": current_user.username,
            "status": maint.status,
            "actions_taken": actions_taken.strip(),
            "checklist": checklist_dict
        }
    )
    db.commit()

    return RedirectResponse(
        url=f"/maintenance?msg=Protocolo+{maint.code}+finalizado+exitosamente.+La+orden+de+trabajo+ha+pasado+a+estado+'Pendiente+de+Validación'+para+revisión+del+Validador.",
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/maintenance/{maintenance_id}/validate")
async def validate_maintenance_web(
    maintenance_id: int,
    request: Request,
    action: str = Form(...),  # "approve" or "reject"
    validation_notes: Optional[str] = Form(None),
    rejection_photo: Optional[UploadFile] = File(None),
    redirect_to: Optional[str] = Form(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Dictamen formal y certificación del Validador sobre una orden de mantenimiento:
    - 'approve': Certifica conformidad técnica ('Validado / Conforme').
    - 'reject': Devuelve la orden al técnico con observaciones y reinicia el ticket con tiempo cero.
    """
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    referer = request.headers.get("referer", "")
    if "/maintenance" in referer and redirect_to != "/validation":
        err = urllib.parse.quote("El validador solo puede validar un ticket preventivo desde la opción 'Validación Policial'.")
        return RedirectResponse(url=f"/maintenance?error={err}", status_code=status.HTTP_303_SEE_OTHER)

    target_redirect = redirect_to or "/validation"

    if current_user.role != "Validador":
        return RedirectResponse(
            url=f"{target_redirect}?error=Acceso+denegado:+Solo+el+rol+Validador+(Policía+Nacional)+tiene+permisos+para+revisar+y+validar+trabajos+técnicos.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    maint = db.query(Maintenance).filter(Maintenance.id == maintenance_id).first()
    if not maint:
        return RedirectResponse(url=f"{target_redirect}?error=Mantenimiento+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)

    now = get_local_now()

    if action == "approve":
        maint.status = "Validado / Conforme"
        maint.validation_status = "Conforme"
        maint.validator_id = current_user.id
        maint.validated_at = now
        maint.validation_notes = (
            validation_notes.strip()
            if validation_notes and validation_notes.strip()
            else "Trabajo revisado, verificado y validado formalmente conforme a los estándares técnicos y evidencias fotográficas."
        )

        badge_txt = f" (Placa #{current_user.badge_number})" if current_user.badge_number else ""
        db.add(Event(
            maintenance_id=maint.id,
            user_id=current_user.id,
            event_type="MAINTENANCE_VALIDATED",
            description=f"Protocolo {maint.code} aprobado con visto bueno técnico y conformidad por Validador {current_user.full_name or current_user.username}{badge_txt}."
        ))

        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="MAINTENANCE_VALIDATED_WEB",
            details={
                "maintenance_id": maint.id,
                "protocol_code": maint.code,
                "validator": current_user.username,
                "badge_number": current_user.badge_number,
                "status": maint.status,
                "notes": maint.validation_notes
            }
        )
        db.commit()
        return RedirectResponse(
            url=f"{target_redirect}?msg=Orden+de+trabajo+{maint.code}+Aprobada+con+éxito.+Se+ha+certificado+su+Conformidad+técnica+policial.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    elif action == "reject":
        if not validation_notes or not validation_notes.strip():
            return RedirectResponse(
                url=f"{target_redirect}?error=Debe+especificar+las+observaciones+técnicas+de+rechazo+para+que+el+contratista+pueda+subsanar.",
                status_code=status.HTTP_303_SEE_OTHER
            )

        rejection_photo_path = await save_uploaded_photo(rejection_photo)
        if rejection_photo_path:
            maint.rejection_photo = rejection_photo_path

        # Reinicio del ticket con tiempo cero y devolución a la Empresa de Mantenimiento
        maint.status = "Rechazado"
        maint.validation_status = "Rechazado"
        maint.validator_id = current_user.id
        maint.validated_at = now
        maint.validation_notes = validation_notes.strip()
        maint.timer_reset_at = now  # TIEMPO CERO
        maint.scheduled_date = now   # Cronograma reactivado desde cero
        maint.completed_date = None  # Reabierto para subsanación técnica

        badge_txt = f" (Placa #{current_user.badge_number})" if current_user.badge_number else ""
        db.add(Event(
            maintenance_id=maint.id,
            user_id=current_user.id,
            event_type="MAINTENANCE_REJECTED",
            description=f"Protocolo {maint.code} rechazado y devuelto a subsanación técnica con tiempo cero por Validador {current_user.full_name or current_user.username}{badge_txt}. Obs: {(maint.validation_notes or '')[:100]}"
        ))

        create_audit_log(
            db,
            user_id=current_user.id,
            username=current_user.username,
            action="MAINTENANCE_REJECTED_WEB",
            details={
                "maintenance_id": maint.id,
                "protocol_code": maint.code,
                "validator": current_user.username,
                "status": maint.status,
                "notes": maint.validation_notes,
                "rejection_photo": rejection_photo_path,
                "timer_reset": True
            }
        )
        db.commit()
        return RedirectResponse(
            url=f"{target_redirect}?msg=Orden+de+trabajo+{maint.code}+Rechazada+y+devuelta+al+técnico+con+tiempo+cero+para+su+corrección.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    return RedirectResponse(url=target_redirect, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/maintenance/{maintenance_id}/certificate.pdf")
def download_maintenance_certificate_pdf(
    maintenance_id: int,
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Descarga el Acta Oficial de Conformidad y Validación Técnica Policial para un mantenimiento."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    # Restricción de seguridad: Administrador, Validador, Supervisor, Empresa de Mantenimiento y Operario
    if current_user.role not in ["Admin", "Validador", "Supervisor", "Empresa de Mantenimiento", "Operario"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso Denegado: Este informe técnico oficial de validación solo puede ser consultado por usuarios autorizados."
        )

    maint = db.query(Maintenance).filter(Maintenance.id == maintenance_id).first()
    if not maint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mantenimiento no encontrado.")

    if not maint.is_validated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este protocolo preventivo aún no ha sido aprobado ni validado formalmente por la Estación de Policía."
        )

    # Resolver la sede técnica propia del mantenimiento
    matched_site = None
    if maint.sede:
        maint_sede_norm = maint.sede.strip().lower()
        matched_site = next((s for s in AVAILABLE_SITES if s["name"].lower() in maint_sede_norm or s["full_name"].lower() in maint_sede_norm or maint_sede_norm in s["full_name"].lower()), None)

    if not matched_site:
        active_site_id = request.cookies.get("active_site", "san-agustin")
        matched_site = next((s for s in AVAILABLE_SITES if s["id"] == active_site_id), AVAILABLE_SITES[0])
    current_site = matched_site

    validator_user = maint.validator
    if not validator_user:
        validator_user = db.query(User).filter(User.role == "Validador", User.is_active == True, User.is_deleted == False).first() or current_user

    pdf_bytes = generate_validation_conformity_pdf(
        item=maint,
        item_type="maintenance",
        validator=validator_user,
        current_site=current_site
    )

    filename = f"Acta_Conformidad_Policial_{maint.code}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )


@app.get("/validation", response_class=HTMLResponse)
def validation_view(
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status"),
    type_filter: Optional[str] = Query(None, alias="type"),
    msg: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Panel Exclusivo de Auditoría, Supervisión y Validación Policial:
    Permite al personal de la Estación de Policía (Validador), Administrador y Supervisor
    consultar el detalle exhaustivo de trabajos finalizados (Preventivos y Correctivos)
    y dictaminar su Aprobación / Validación de Conformidad o Rechazo con observaciones.
    """
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    if current_user.role not in ["Validador", "Admin", "Supervisor", "Empresa de Mantenimiento", "Operario"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: El panel de validación policial es exclusivo para Validador, Administrador, Supervisor y Empresa de Mantenimiento."
        )

    active_site_id = request.cookies.get("active_site", "san-agustin")
    current_site = next((s for s in AVAILABLE_SITES if s["id"] == active_site_id), AVAILABLE_SITES[0])

    lic_redirect = check_site_access_or_redirect(request, current_user, current_site, db)
    if lic_redirect:
        return lic_redirect

    site_filter_inc = get_site_filter_conditions(Incident, current_site)
    site_filter_maint = get_site_filter_conditions(Maintenance, current_site)

    # 1. Incidentes relevantes para validación
    all_incidents = db.query(Incident).filter(
        site_filter_inc,
        Incident.status.in_(["Pendiente de Validación", "Validado / Conforme", "Conforme / Validado", "Rechazado", "Cerrado", "En Proceso", "Abierto"])
    ).order_by(Incident.updated_at.desc()).all()

    # 2. Mantenimientos preventivos relevantes
    all_maintenances = db.query(Maintenance).filter(
        site_filter_maint,
        Maintenance.status.in_(["Pendiente de Validación", "Validado / Conforme", "Conforme / Validado", "Rechazado", "Completado", "En Ejecución", "Programado"])
    ).order_by(Maintenance.completed_date.desc(), Maintenance.created_at.desc()).all()

    # Conteos de indicadores
    pending_incidents = [i for i in all_incidents if i.status == "Pendiente de Validación"]
    pending_maintenances = [m for m in all_maintenances if m.status == "Pendiente de Validación"]
    pending_count = len(pending_incidents) + len(pending_maintenances)

    validated_incidents = [i for i in all_incidents if i.status in ["Validado / Conforme", "Conforme / Validado"] or i.validation_status == "Conforme"]
    validated_maintenances = [m for m in all_maintenances if m.status in ["Validado / Conforme", "Conforme / Validado"] or m.validation_status == "Conforme"]
    validated_count = len(validated_incidents) + len(validated_maintenances)

    rejected_incidents = [i for i in all_incidents if i.validation_status == "Rechazado" or i.status == "Rechazado"]
    rejected_maintenances = [m for m in all_maintenances if m.validation_status == "Rechazado" or m.status == "Rechazado"]
    rejected_count = len(rejected_incidents) + len(rejected_maintenances)

    return templates.TemplateResponse(
        request=request,
        name="validation.html",
        context={
            "current_user": current_user,
            "current_site": current_site,
            "available_sites": AVAILABLE_SITES,
            "all_sites": AVAILABLE_SITES,
            "active_page": "validation",
            "pending_validation_count": pending_count,
            "pending_count": pending_count,
            "validated_count": validated_count,
            "rejected_count": rejected_count,
            "pending_incidents": pending_incidents,
            "pending_maintenances": pending_maintenances,
            "all_incidents": all_incidents,
            "all_maintenances": all_maintenances,
            "status_filter": status_filter or "all",
            "type_filter": type_filter or "all",
            "msg": msg,
            "error": error
        }
    )


# ----------------- 10. Rutas Operativas: Estadísticas e Informes (PDF) -----------------

def resolve_date_range(period: str, start_date_str: Optional[str], end_date_str: Optional[str]):
    """Calcula y estandariza el rango de fechas para las consultas analíticas e informes."""
    now = get_local_now()
    end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    if period == "custom" and start_date_str and end_date_str:
        try:
            start_dt = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
            end_dt = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999999)
            period_label = "Personalizado"
            return start_dt, end_dt, period_label
        except Exception:
            pass

    if period == "monthly":
        start_dt = (now - datetime.timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "Mensual (Últimos 30 días)"
    elif period == "quarterly":
        start_dt = (now - datetime.timedelta(days=90)).replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "Trimestral (Últimos 90 días)"
    elif period == "semiannual":
        start_dt = (now - datetime.timedelta(days=180)).replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "Semestral (Últimos 180 días)"
    elif period == "annual":
        start_dt = (now - datetime.timedelta(days=365)).replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "Anual (Últimos 365 días)"
    else:  # por defecto 'weekly'
        start_dt = (now - datetime.timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "Semanal (Últimos 7 días)"
        period = "weekly"

    return start_dt, end_dt, period_label


@app.get("/reports", response_class=HTMLResponse)
@app.get("/statistics", response_class=HTMLResponse)
@app.get("/analytics", response_class=HTMLResponse)
def reports_view(
    request: Request,
    period: str = Query("weekly"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Vista web ejecutiva de estadísticas e informes con gráficos dinámicos y exportación PDF."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request)

    lic_redirect = check_site_access_or_redirect(request, current_user, current_site, db)
    if lic_redirect:
        return lic_redirect
    start_dt, end_dt, period_label = resolve_date_range(period, start_date, end_date)

    stats = get_reports_statistics(db, current_site, start_dt, end_dt)
    
    chart_payload = {
        "kpis": stats["kpis"],
        "charts": stats["charts"],
        "period": stats["period"],
        "period_label": period_label
    }
    chart_json = json.dumps(chart_payload, ensure_ascii=False)

    return templates.TemplateResponse(
        request=request,
        name="reports.html",
        context={
            "current_user": current_user,
            "current_site": current_site,
            "available_sites": AVAILABLE_SITES,
            "active_page": "reports",
            "stats": stats,
            "chart_json": chart_json,
            "period": period,
            "period_label": period_label,
            "start_date": start_dt.strftime("%Y-%m-%d"),
            "end_date": end_dt.strftime("%Y-%m-%d")
        }
    )


@app.get("/api/reports/stats", response_class=JSONResponse)
def get_reports_stats_api(
    request: Request,
    period: str = Query("weekly"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Endpoint REST JSON para recarga dinámica automática de estadísticas y gráficos."""
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")

    current_site = get_current_site(request)
    start_dt, end_dt, period_label = resolve_date_range(period, start_date, end_date)
    stats = get_reports_statistics(db, current_site, start_dt, end_dt)

    return JSONResponse(content={
        "kpis": stats["kpis"],
        "charts": stats["charts"],
        "period": stats["period"],
        "period_label": period_label
    })


@app.get("/reports/export/pdf")
def export_cctv_pdf_report(
    request: Request,
    period: str = Query("weekly"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Genera y descarga el informe oficial en PDF para el rango de fechas seleccionado."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request)
    start_dt, end_dt, period_label = resolve_date_range(period, start_date, end_date)

    pdf_bytes = generate_cctv_pdf_report(
        db=db,
        current_site=current_site,
        start_date=start_dt,
        end_date=end_dt,
        requested_by=current_user,
        period_label=period_label
    )

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="PDF_REPORT_GENERATED",
        details={
            "site": current_site["full_name"],
            "period": period,
            "period_label": period_label,
            "range": f"{start_dt.strftime('%Y-%m-%d')} - {end_dt.strftime('%Y-%m-%d')}"
        }
    )
    db.commit()

    clean_site_slug = current_site["id"].replace("-", "_")
    filename = f"informe_tecnico_cctv_{clean_site_slug}_{period}_{start_dt.strftime('%Y%m%d')}_{end_dt.strftime('%Y%m%d')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"",
            "Cache-Control": "no-cache, no-store, must-revalidate"
        }
    )


@app.get("/reports/export/executive-pdf")
def export_cctv_executive_pdf_report(
    request: Request,
    period: str = Query("weekly"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Genera y descarga el Informe Ejecutivo Oficial en PDF para el rango de fechas seleccionado."""
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request)
    start_dt, end_dt, period_label = resolve_date_range(period, start_date, end_date)

    pdf_bytes = generate_cctv_executive_pdf_report(
        db=db,
        current_site=current_site,
        start_date=start_dt,
        end_date=end_dt,
        requested_by=current_user,
        period_label=period_label
    )

    create_audit_log(
        db,
        user_id=current_user.id,
        username=current_user.username,
        action="EXECUTIVE_PDF_REPORT_GENERATED",
        details={
            "site": current_site["full_name"],
            "period": period,
            "period_label": period_label,
            "range": f"{start_dt.strftime('%Y-%m-%d')} - {end_dt.strftime('%Y-%m-%d')}"
        }
    )
    db.commit()

    clean_site_slug = current_site["id"].replace("-", "_")
    filename = f"informe_ejecutivo_cctv_{clean_site_slug}_{period}_{start_dt.strftime('%Y%m%d')}_{end_dt.strftime('%Y%m%d')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"",
            "Cache-Control": "no-cache, no-store, must-revalidate"
        }
    )


@app.get("/schedule", response_class=HTMLResponse)
@app.get("/cronograma", response_class=HTMLResponse)
def schedule_view(
    request: Request,
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Cronograma de Operaciones y Mantenimiento CCTV:
    Muestra en vista de calendario mensual unificado todos los tickets de incidentes y mantenimientos
    programados o registrados en la sede activa, con desglose interactivo y ventana modal compacta.
    """
    if not current_user:
        return RedirectResponse(url="/select-site", status_code=status.HTTP_302_FOUND)

    if current_user.must_change_password:
        return RedirectResponse(url="/change-credentials", status_code=status.HTTP_302_FOUND)

    current_site = get_current_site(request, db=db)
    lic_redirect = check_site_access_or_redirect(request, current_user, current_site, db)
    if lic_redirect:
        return lic_redirect

    now = get_local_now()
    target_year = year if (year and 2000 <= year <= 2100) else now.year
    target_month = month if (month and 1 <= month <= 12) else now.month

    # Cálculo de meses anterior y siguiente
    if target_month == 1:
        prev_month, prev_year = 12, target_year - 1
    else:
        prev_month, prev_year = target_month - 1, target_year

    if target_month == 12:
        next_month, next_year = 1, target_year + 1
    else:
        next_month, next_year = target_month + 1, target_year

    cal = calendar.Calendar(firstweekday=0)  # Lunes = 0
    month_weeks = cal.monthdatescalendar(target_year, target_month)
    grid_start_date = month_weeks[0][0]
    grid_end_date = month_weeks[-1][-1]

    start_dt = datetime.datetime.combine(grid_start_date, datetime.time.min)
    end_dt = datetime.datetime.combine(grid_end_date, datetime.time.max)

    site_filter_inc = get_site_filter_conditions(Incident, current_site)
    site_filter_maint = get_site_filter_conditions(Maintenance, current_site)

    # 1. Incidentes registrados en el periodo del calendario
    incidents = db.query(Incident).filter(
        site_filter_inc,
        Incident.created_at >= start_dt,
        Incident.created_at <= end_dt
    ).order_by(Incident.created_at.asc()).all()

    # 2. Mantenimientos programados en el periodo del calendario
    maintenances = db.query(Maintenance).filter(
        site_filter_maint,
        Maintenance.scheduled_date >= start_dt,
        Maintenance.scheduled_date <= end_dt
    ).order_by(Maintenance.scheduled_date.asc()).all()

    # Mapear tickets agrupados por fecha ISO (YYYY-MM-DD)
    tickets_by_date: Dict[str, Dict[str, Any]] = {}

    for inc in incidents:
        if not inc.created_at:
            continue
        d_str = inc.created_at.strftime("%Y-%m-%d")
        if d_str not in tickets_by_date:
            tickets_by_date[d_str] = {"incidents": [], "maintenances": []}

        dev_name = inc.device.name if inc.device else "CCTV General"
        dev_loc = inc.device.location_detail if (inc.device and inc.device.location_detail) else (inc.device.sede if inc.device else inc.sede or "")
        tickets_by_date[d_str]["incidents"].append({
            "type": "incident",
            "type_label": "Incidente",
            "id": inc.id,
            "ticket_code": inc.ticket_code,
            "title": inc.title or f"Incidente en {dev_name}",
            "status": inc.status or "Abierto",
            "fault_type": inc.fault_type or "Falla Técnica",
            "priority": inc.priority or "Media",
            "device_name": dev_name,
            "location": dev_loc,
            "time": inc.created_at.strftime("%H:%M"),
            "date_display": inc.created_at.strftime("%d/%m/%Y"),
            "link": f"/incidents?search={urllib.parse.quote(inc.ticket_code)}"
        })

    for m in maintenances:
        if not m.scheduled_date:
            continue
        d_str = m.scheduled_date.strftime("%Y-%m-%d")
        if d_str not in tickets_by_date:
            tickets_by_date[d_str] = {"incidents": [], "maintenances": []}

        dev_name = m.device.name if m.device else "CCTV General"
        dev_loc = m.device.location_detail if (m.device and m.device.location_detail) else (m.device.sede if m.device else m.sede or "")
        tickets_by_date[d_str]["maintenances"].append({
            "type": "maintenance",
            "type_label": "Mantenimiento",
            "id": m.id,
            "ticket_code": m.code,
            "title": m.title or f"Mantenimiento en {dev_name}",
            "status": m.status or "Programado",
            "frequency": m.frequency or "Preventivo",
            "device_name": dev_name,
            "location": dev_loc,
            "time": m.scheduled_date.strftime("%H:%M"),
            "date_display": m.scheduled_date.strftime("%d/%m/%Y"),
            "link": f"/maintenance?search={urllib.parse.quote(m.code)}"
        })

    SPANISH_MONTHS = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                      "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    month_name = SPANISH_MONTHS[target_month]

    calendar_weeks = []
    total_month_incidents = 0
    total_month_maintenances = 0
    active_days_count = 0
    today_str = now.strftime("%Y-%m-%d")

    for week in month_weeks:
        week_days = []
        for day in week:
            d_str = day.strftime("%Y-%m-%d")
            day_data = tickets_by_date.get(d_str, {"incidents": [], "maintenances": []})
            day_incidents = day_data["incidents"]
            day_maintenances = day_data["maintenances"]
            inc_count = len(day_incidents)
            maint_count = len(day_maintenances)
            total_day_tickets = inc_count + maint_count

            is_current_month = (day.month == target_month)
            if is_current_month:
                total_month_incidents += inc_count
                total_month_maintenances += maint_count
                if total_day_tickets > 0:
                    active_days_count += 1

            if inc_count > 0 and maint_count > 0:
                hover_type = "both"
                hover_text = f"Incidentes ({inc_count}) y Mantenimientos ({maint_count})"
                hover_badge = f"⚡ {inc_count} Inc. | {maint_count} Mant."
            elif inc_count > 0:
                hover_type = "incident"
                hover_text = f"Incidentes ({inc_count})"
                hover_badge = f"🔴 {inc_count} Incidente{'s' if inc_count > 1 else ''}"
            elif maint_count > 0:
                hover_type = "maintenance"
                hover_text = f"Mantenimientos ({maint_count})"
                hover_badge = f"🔵 {maint_count} Mantenimiento{'s' if maint_count > 1 else ''}"
            else:
                hover_type = "none"
                hover_text = "Sin tickets registrados"
                hover_badge = ""

            week_days.append({
                "date": day,
                "date_str": d_str,
                "day_num": day.day,
                "is_current_month": is_current_month,
                "is_today": (d_str == today_str),
                "incidents": day_incidents,
                "maintenances": day_maintenances,
                "inc_count": inc_count,
                "maint_count": maint_count,
                "total_tickets": total_day_tickets,
                "has_tickets": total_day_tickets > 0,
                "hover_type": hover_type,
                "hover_text": hover_text,
                "hover_badge": hover_badge,
                "formatted_date_es": f"{day.day} de {SPANISH_MONTHS[day.month]} de {day.year}"
            })
        calendar_weeks.append(week_days)

    available_years = list(range(now.year - 2, now.year + 4))

    return templates.TemplateResponse(
        request=request,
        name="schedule.html",
        context={
            "current_user": current_user,
            "current_site": current_site,
            "available_sites": AVAILABLE_SITES,
            "active_page": "schedule",
            "calendar_weeks": calendar_weeks,
            "tickets_by_date_json": json.dumps(tickets_by_date, ensure_ascii=False),
            "target_year": target_year,
            "target_month": target_month,
            "month_name": month_name,
            "prev_year": prev_year,
            "prev_month": prev_month,
            "next_year": next_year,
            "next_month": next_month,
            "today_year": now.year,
            "today_month": now.month,
            "today_str": today_str,
            "total_month_incidents": total_month_incidents,
            "total_month_maintenances": total_month_maintenances,
            "total_month_tickets": total_month_incidents + total_month_maintenances,
            "active_days_count": active_days_count,
            "available_years": available_years,
            "spanish_months": [(i, SPANISH_MONTHS[i]) for i in range(1, 13)]
        }
    )


# ----------------- Routers de la API REST -----------------
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sites_api.router)
app.include_router(license.router)
app.include_router(incidents_api.router)
app.include_router(maintenance_api.router)
app.include_router(events_api.router)
