# 📹 Sistema de Gestión de Incidentes y Mantenimiento CCTV

Aplicación Web integral, segura y escalable para la gestión de incidentes técnicos, programación de mantenimientos preventivos/correctivos y monitoreo territorial de circuitos cerrados de televisión (CCTV) con almacenamiento local de evidencias y control de sedes en **4 Municipios Oficiales**:
1. **San Agustín (Huila)**
2. **San José del Guaviare (Guaviare)**
3. **El Retorno (Guaviare)**
4. **Calamar (Guaviare)**

---

## 🚀 Características Principales

- 📍 **Flujo Guiado por Sede Territorial**: Acceso institucional organizado en dos pasos (Paso 1: Selección de Municipio &rarr; Paso 2: Ingreso por Rol en la Sede).
- 👥 **3 Perfiles Institucionales Contextualizados por Sede**:
  1. **Administrador(a)**: Control total, gestión global y configuración del sitio seleccionado.
  2. **Supervisor(a) del Contrato**: Acceso de auditoría, revisión de estado e informes de la sede activa.
  3. **Empresa de Mantenimiento (Preventivo / Correctivo)**: Acceso operativo para registrar diagnósticos, atender incidencias y actualizar equipos.
- 🧪 **Modo Demostración / Sandbox (Volátil en Memoria)**: Entorno aislado en memoria (`sqlite:///:memory:`) que simula la operación completa en los 4 municipios sin persistir cambios en disco ni alterar los registros reales.
- 📊 **Panel Principal (Dashboard) Dinámico**: Métricas en vivo de incidentes abiertos, mantenimientos pendientes, disponibilidad de cámaras y **filtro estricto por sede activa**.
- 🚨 **Módulo de Incidentes**: Reporte y seguimiento de novedades con niveles de prioridad (*Baja, Media, Alta, Crítica*), flujo de estados (*Abierto, En Proceso, Resuelto, Cerrado*), vinculación a equipos específicos y registro de auditoría.
- 🛠️ **Módulo de Mantenimientos**: Planificación de órdenes preventivas y correctivas con fechas programadas, finalización y vinculación a incidentes y equipos del inventario.
- 🖲️ **Gestión de Inventario de Equipos**: Registro y control técnico de Cámaras (PTZ, Domo, Bala), NVRs, Switches PoE y UPS asignados a cada municipio, con control de direcciones IP, seriales y estados operativos.
- 📸 **Evidencias Fotográficas 100% Locales**: Carga y almacenamiento directo en `static/uploads/` sin dependencias de servicios externos ni nubes de terceros, con visor modal (*lightbox*).
- 📜 **Licenciamiento y Trazabilidad**: Control de llaves de activación HMAC y auditoría completa de eventos y cambios de estado.

---

## 📋 Requisitos Previos

- **Python 3.10** o superior (Probado en Python 3.11, 3.12 y 3.13)
- **Pip** (administrador de paquetes de Python)
- **Docker** y **Docker Compose** (Opcional, para ejecución en contenedores con PostgreSQL)

---

## 💻 Opción 1: Instalación y Ejecución Local (Desarrollo / Producción Local)

Sigue estos pasos exactos en tu terminal (PowerShell o CMD en Windows, Bash en Linux/macOS):

### 1. Clonar o ubicarse en el directorio del proyecto
```bash
cd "c:\A. Bodega\Desarrollo de software\Antigravity\Gestión incidentes CCTV"
```

### 2. Crear y activar el entorno virtual
- **En Windows (PowerShell)**:
  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  ```
- **En Windows (CMD)**:
  ```cmd
  python -m venv venv
  .\venv\Scripts\activate.bat
  ```
- **En Linux / macOS**:
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### 3. Instalar las dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno (Opcional)
El sistema funciona automáticamente con base de datos SQLite local (`sqlite.db`). Si deseas personalizar parámetros, puedes crear un archivo `.env` en la raíz:

```env
DATABASE_URL=sqlite:///./sqlite.db
SECRET_KEY=clave-secreta-personalizada-de-seguridad-cctv-2026
ACCESS_TOKEN_EXPIRE_MINUTES=60
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=admin123
```

### 5. Iniciar el servidor web (Modo Normal)
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 🧪 Opción 2: Ejecución en Modo Demo (Sandbox Aislado)

Para demostraciones a clientes o pruebas comerciales con datos realistas pre-cargados (usuarios, inventario de cámaras PTZ, NVRs, switches PoE, UPS, tickets e historial de mantenimiento) **sin tocar ni alterar la base de datos real**:

### En Windows (PowerShell):
```powershell
$env:DEMO_MODE="True"; uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### En Windows (CMD):
```cmd
set DEMO_MODE=True && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### En Linux / macOS:
```bash
DEMO_MODE=True uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### O mediante el script directo:
```bash
python seeder_demo.py
```

> **Nota de Sandbox**: Al iniciar con `DEMO_MODE=True`, el sistema conmuta automáticamente a la base de datos aislada `demo_cctv.db`, ejecuta el *seeder* en el arranque y muestra un panel interactivo con credenciales en la pantalla de inicio de sesión.

---

## 🐳 Opción 3: Despliegue con Docker Compose (PostgreSQL)

Para desplegar la aplicación en contenedores aislados con base de datos PostgreSQL persistente:

### 1. Construir e iniciar los servicios
```bash
docker-compose up --build -d
```

### 2. Verificar el estado de los contenedores
```bash
docker-compose ps
```

### 3. Consultar los registros (logs)
```bash
docker-compose logs -f web
```

### 4. Detener y apagar los servicios
```bash
docker-compose down
```

---

## 🔑 Credenciales de Acceso por Defecto

Al iniciar el sistema por primera vez, se sembrará automáticamente el usuario **Administrador**:

| Campo | Valor por Defecto |
|---|---|
| **URL de Acceso** | [http://127.0.0.1:8000/login](http://127.0.0.1:8000/login) |
| **Usuario** | `admin` |
| **Contraseña** | `admin123` |
| **Rol** | `Admin` |

---

## 🌐 Rutas y Enlaces del Sistema

- 🚪 **Portal de Inicio (Landing)**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- 🧪 **Modo Demo (Sandbox)**: [http://127.0.0.1:8000/demo/login](http://127.0.0.1:8000/demo/login)
- 🔑 **Inicio de Sesión Real**: [http://127.0.0.1:8000/login](http://127.0.0.1:8000/login)
- 📍 **Selector de Sede Post-Login**: [http://127.0.0.1:8000/select-location](http://127.0.0.1:8000/select-location)
- 🖥️ **Panel Principal (Dashboard)**: [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard)
- 🖲️ **Inventario de Equipos CCTV**: [http://127.0.0.1:8000/devices](http://127.0.0.1:8000/devices)
- 🚨 **Gestión de Incidentes**: [http://127.0.0.1:8000/incidents](http://127.0.0.1:8000/incidents)
- 🛠️ **Gestión de Mantenimientos**: [http://127.0.0.1:8000/maintenance](http://127.0.0.1:8000/maintenance)
- 👥 **Gestión de Usuarios (Admin)**: [http://127.0.0.1:8000/users](http://127.0.0.1:8000/users)
- 🚪 **Cerrar Sesión**: [http://127.0.0.1:8000/logout](http://127.0.0.1:8000/logout)
- 📖 **Documentación API (Swagger UI)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 📘 **Documentación Alternativa (ReDoc)**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 📁 Estructura del Proyecto

```text
├── app/
│   ├── auth.py              # Seguridad, hashing bcrypt, tokens JWT y RBAC
│   ├── config.py            # Configuración pydantic y variables de entorno
│   ├── database.py          # Conexión SQLAlchemy y generador de sesiones
│   ├── main.py              # Aplicación FastAPI, rutas web y lifespan
│   ├── models/              # Modelos de base de datos (User, Incident, Maintenance, etc.)
│   ├── models.py            # Declaración unificada de modelos SQLAlchemy
│   ├── routers/             # Endpoints REST API de Fase 1 y Fase 2
│   ├── schemas/             # Esquemas de validación Pydantic
│   ├── services/            # Servicios de auditoría, licencias y autenticación
│   └── templates/           # Vistas Jinja2 con Tailwind CSS y Alpine.js
│       ├── base.html        # Plantilla base y navegación responsive
│       ├── dashboard.html   # Panel de control y filtrado territorial
│       ├── incidents.html   # Reportes de incidentes y subida de fotos
│       ├── login.html       # Interfaz moderna de inicio de sesión
│       └── maintenances.html# Programación técnica de mantenimientos
├── static/
│   └── uploads/             # Directorio local para almacenamiento de fotos
├── Dockerfile               # Configuración de imagen Docker para FastAPI
├── docker-compose.yml       # Orquestación de backend y PostgreSQL
├── requirements.txt         # Dependencias Python
└── README.md                # Documentación del proyecto
```

---

## 👥 Roles y Permisos del Sistema

1. **Admin**: Acceso total al sistema, gestión de licencias, administración de usuarios y cierre definitivo de incidentes y mantenimientos.
2. **Supervisor**: Visualización general, creación y asignación de incidentes, programación de mantenimientos y modificación de estados.
3. **Responsable / Operario**: Creación de reportes de novedades, adjunto de fotografías de evidencia y cambio de estado a En Proceso / Resuelto.
