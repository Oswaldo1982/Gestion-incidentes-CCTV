"""
Script y Módulo de Poblado de Datos para Modo Demo / Sandbox (Volátil en Memoria).
Genera datos contextualizados de videovigilancia pública y privada en los 4 municipios:
1. San Agustín (Huila)
2. San José del Guaviare (Guaviare)
3. El Retorno (Guaviare)
4. Calamar (Guaviare)
"""
import datetime
from sqlalchemy.orm import Session
from app.models import User, Device, Incident, Maintenance, Event, AuditLog, License
from app.auth import get_password_hash
from app.services.license_service import generate_dev_license
from app.config import settings


def seed_demo_data(db: Session):
    """
    Puebla la base de datos persistente con el catálogo inicial de demostración
    sin eliminar registros existentes.
    """
    from app.services.seed_loader import ensure_golden_data_seeded
    ensure_golden_data_seeded(db)

    now = datetime.datetime.utcnow()

    # 2. Licencia del Sistema (365 días, 100 usuarios concurrentes)
    demo_license_key = generate_dev_license(expires_days=365, max_users=100)
    db.add(License(
        license_key=demo_license_key,
        is_active=True,
        activated_at=now - datetime.timedelta(days=30)
    ))

    # 3. Cuentas de Acceso por Perfil Institucional
    # Perfil 1: Administrador(a)
    user_admin = User(
        username="admin",
        email="admin@cctv-seguridad.gov.co",
        full_name="Administrador Principal",
        assigned_site="Todas las Sedes",
        document_id="0000000000",
        hashed_password=get_password_hash("admin123"),
        role="Admin",
        is_active=True,
        must_change_password=False,
        created_at=now - datetime.timedelta(days=90)
    )
    # Perfil 2: Supervisor(a) del Contrato (General / Demo)
    user_sup_general = User(
        username="supervisor",
        email="supervision.cctv@supervision-cctv.gov.co",
        hashed_password=get_password_hash("supervisor123"),
        role="Supervisor",
        is_active=True,
        created_at=now - datetime.timedelta(days=60)
    )
    # Perfil 2: Supervisor(a) del Contrato (Huila)
    user_sup_huila = User(
        username="supervisor_sanagustin",
        email="supervision.cctv@sanagustin-huila.gov.co",
        hashed_password=get_password_hash("supervisor123"),
        role="Supervisor",
        is_active=True,
        created_at=now - datetime.timedelta(days=60)
    )
    # Perfil 2: Supervisor(a) del Contrato (Guaviare)
    user_sup_guaviare = User(
        username="supervisor_guaviare",
        email="supervision.cctv@guaviare.gov.co",
        hashed_password=get_password_hash("supervisor123"),
        role="Supervisor",
        is_active=True,
        created_at=now - datetime.timedelta(days=60)
    )
    # Perfil 3: Validador Técnico (Revisión y Conformidad - Policía Nacional)
    user_validador = User(
        username="validador",
        email="validador.cctv@seguridad-cctv.gov.co",
        full_name="Oficial Validador de Calidad CCTV (Policía Nacional)",
        assigned_site="Todas las Sedes",
        document_id="1010202303",
        badge_number="109845",
        hashed_password=get_password_hash("validador123"),
        role="Validador",
        is_active=True,
        must_change_password=False,
        created_at=now - datetime.timedelta(days=70)
    )
    # Perfil 4: Empresa de Mantenimiento (Preventivo y Correctivo)
    user_mantenimiento = User(
        username="mantenimiento_cctv",
        email="operaciones@contratistacctv.com",
        full_name="Consorcio Mantenimiento CCTV",
        document_id="9008887771",
        assigned_site="Todas las Sedes",
        hashed_password=get_password_hash("mantenimiento123"),
        role="Empresa de Mantenimiento",
        is_active=True,
        must_change_password=False,
        created_at=now - datetime.timedelta(days=50)
    )
    user_tecnico = User(
        username="tecnico_campo",
        email="soporte.tecnico@contratistacctv.com",
        full_name="Técnico de Campo Especialista",
        document_id="1085234567",
        assigned_site="Todas las Sedes",
        hashed_password=get_password_hash("tecnico123"),
        role="Empresa de Mantenimiento",
        is_active=True,
        must_change_password=False,
        created_at=now - datetime.timedelta(days=45)
    )

    all_seed_users = [
        user_admin, user_validador, user_sup_general, user_sup_huila, user_sup_guaviare, user_mantenimiento, user_tecnico
    ]
    db.add_all(all_seed_users)
    db.commit()
    for u in all_seed_users:
        db.refresh(u)

    # 4. Inventario de Equipos CCTV en los 4 Municipios
    devices_data = [
        # --- 1. San Agustín (Huila) ---
        Device(
            name="Cámara PTZ 01 - Parque Arqueológico",
            device_type="Cámara PTZ",
            brand="Hikvision",
            model="DS-2DE4425IW-DE",
            serial_number="HK-PTZ-88101",
            ip_address="192.168.10.21",
            mac_address="00:1A:E8:3B:42:11",
            sede="San Agustín (Huila)",
            location_detail="Acceso Principal Bosque de las Estatuas",
            status="Operativo",
            created_at=now - datetime.timedelta(days=90)
        ),
        Device(
            name="Cámara Domo 02 - Terminal de Transportes",
            device_type="Cámara Domo",
            brand="Dahua",
            model="IPC-HDBW2431E",
            serial_number="DH-DOM-44319",
            ip_address="192.168.10.22",
            mac_address="38:AF:29:44:91:02",
            sede="San Agustín (Huila)",
            location_detail="Bahía de Despacho de Vehículos",
            status="Operativo",
            created_at=now - datetime.timedelta(days=85)
        ),
        Device(
            name="NVR Central 32CH - Estación Policía San Agustín",
            device_type="NVR",
            brand="Dahua",
            model="NVR5232-4KS2",
            serial_number="DH-NVR-32CH-09",
            ip_address="192.168.10.200",
            mac_address="38:AF:29:88:AA:CC",
            sede="San Agustín (Huila)",
            location_detail="Rack Principal de Comunicaciones Sala CAD",
            status="Operativo",
            created_at=now - datetime.timedelta(days=90)
        ),
        Device(
            name="Switch PoE 24P - Nodo Hospital Arsenio Repizo",
            device_type="Switch PoE",
            brand="Cisco",
            model="CBS350-24P-4G",
            serial_number="CS-POE-24P-77",
            ip_address="192.168.10.250",
            mac_address="00:27:10:99:BB:11",
            sede="San Agustín (Huila)",
            location_detail="Gabinete de Telecomunicaciones Urgencias",
            status="Operativo",
            created_at=now - datetime.timedelta(days=70)
        ),

        # --- 2. San José del Guaviare (Guaviare) ---
        Device(
            name="Cámara PTZ 01 - Parque Principal Santander",
            device_type="Cámara PTZ",
            brand="Hikvision",
            model="DS-2DE7A432IW-AEB",
            serial_number="HK-PTZ-SJG-01",
            ip_address="192.168.20.15",
            mac_address="00:1A:E8:55:10:33",
            sede="San José del Guaviare (Guaviare)",
            location_detail="Torre Metálica Centro Plaza Santander",
            status="Operativo",
            created_at=now - datetime.timedelta(days=100)
        ),
        Device(
            name="Cámara Bala 02 - Puerto Fluvial Río Guaviare",
            device_type="Cámara Bala",
            brand="Uniview",
            model="IPC2322EBR5-DUPX28",
            serial_number="UNV-BAL-SJG-02",
            ip_address="192.168.20.16",
            mac_address="6C:59:79:33:12:88",
            sede="San José del Guaviare (Guaviare)",
            location_detail="Muelle Principal de Embarcaciones",
            status="Operativo",
            created_at=now - datetime.timedelta(days=95)
        ),
        Device(
            name="NVR Departamental 64CH - Central Guaviare",
            device_type="NVR",
            brand="Hikvision",
            model="DS-9664NI-I8",
            serial_number="HK-NVR-64CH-SJG",
            ip_address="192.168.20.200",
            mac_address="00:1A:E8:99:FF:01",
            sede="San José del Guaviare (Guaviare)",
            location_detail="Centro de Comando y Control Policía Departamental",
            status="Operativo",
            created_at=now - datetime.timedelta(days=100)
        ),
        Device(
            name="UPS Online 6000VA - Sala CAD San José",
            device_type="UPS",
            brand="APC",
            model="Smart-UPS RT 6000VA",
            serial_number="APC-UPS-6000-SJG",
            ip_address="192.168.20.254",
            mac_address="00:02:6F:11:22:33",
            sede="San José del Guaviare (Guaviare)",
            location_detail="Subestación de Respaldo Eléctrico CAD",
            status="Operativo",
            created_at=now - datetime.timedelta(days=100)
        ),

        # --- 3. El Retorno (Guaviare) ---
        Device(
            name="Cámara Domo PTZ 01 - Entrada Vía Nacional",
            device_type="Cámara PTZ",
            brand="Dahua",
            model="SD59432XA-HNR",
            serial_number="DH-PTZ-RET-01",
            ip_address="192.168.30.11",
            mac_address="38:AF:29:77:44:11",
            sede="El Retorno (Guaviare)",
            location_detail="Puesto de Control Entrada Municipal",
            status="Operativo",
            created_at=now - datetime.timedelta(days=80)
        ),
        Device(
            name="Cámara Bala 02 - Polideportivo Central",
            device_type="Cámara Bala",
            brand="Hikvision",
            model="DS-2CD2043G2-I",
            serial_number="HK-BAL-RET-02",
            ip_address="192.168.30.12",
            mac_address="00:1A:E8:22:88:99",
            sede="El Retorno (Guaviare)",
            location_detail="Cobertura Perimetral Cancha Múltiple",
            status="Operativo",
            created_at=now - datetime.timedelta(days=75)
        ),
        Device(
            name="Switch PoE 16P - Alcaldía El Retorno",
            device_type="Switch PoE",
            brand="Cisco",
            model="CBS250-16P-2G",
            serial_number="CS-POE-RET-16",
            ip_address="192.168.30.250",
            mac_address="00:27:10:33:44:55",
            sede="El Retorno (Guaviare)",
            location_detail="Rack Piso 2 Despacho Municipal",
            status="Operativo",
            created_at=now - datetime.timedelta(days=80)
        ),

        # --- 4. Calamar (Guaviare) ---
        Device(
            name="Cámara PTZ 01 - Muelle Fluvial Río Unilla",
            device_type="Cámara PTZ",
            brand="Hikvision",
            model="DS-2DE4425IW-DE",
            serial_number="HK-PTZ-CAL-01",
            ip_address="192.168.40.10",
            mac_address="00:1A:E8:66:77:88",
            sede="Calamar (Guaviare)",
            location_detail="Control Fluvial y Llegada de Carga Río Unilla",
            status="Operativo",
            created_at=now - datetime.timedelta(days=60)
        ),
        Device(
            name="Cámara Domo 02 - Parque Central Calamar",
            device_type="Cámara Domo",
            brand="Dahua",
            model="IPC-HDBW2431E",
            serial_number="DH-DOM-CAL-02",
            ip_address="192.168.40.11",
            mac_address="38:AF:29:11:55:66",
            sede="Calamar (Guaviare)",
            location_detail="Zona Comercial y Bancaria",
            status="Operativo",
            created_at=now - datetime.timedelta(days=60)
        ),

        # --- 5. Sitio de Prueba (Entorno General Demo) ---
        Device(
            name="Cámara PTZ Demo 01 - Acceso Principal",
            device_type="Cámara PTZ",
            brand="Hikvision",
            model="DS-2DE4425IW-DE",
            serial_number="DEMO-PTZ-001",
            ip_address="192.168.1.10",
            mac_address="00:1A:E8:11:22:33",
            sede="Sitio de Prueba",
            location_detail="Entrada Principal y Perímetro General",
            status="Operativo",
            created_at=now - datetime.timedelta(days=30)
        ),
        Device(
            name="Cámara Domo Demo 02 - Centro de Monitoreo",
            device_type="Cámara Domo",
            brand="Dahua",
            model="IPC-HDBW2431E",
            serial_number="DEMO-DOM-002",
            ip_address="192.168.1.11",
            mac_address="38:AF:29:11:22:33",
            sede="Sitio de Prueba",
            location_detail="Sala de Control de Operaciones",
            status="Operativo",
            created_at=now - datetime.timedelta(days=25)
        ),
        Device(
            name="NVR Central Demo 32CH",
            device_type="NVR",
            brand="Hikvision",
            model="DS-7732NI-I4",
            serial_number="DEMO-NVR-032",
            ip_address="192.168.1.100",
            mac_address="00:1A:E8:44:55:66",
            sede="Sitio de Prueba",
            location_detail="Gabinete de Comunicaciones Demo",
            status="Operativo",
            created_at=now - datetime.timedelta(days=30)
        ),
        Device(
            name="Switch PoE Demo 24P",
            device_type="Switch PoE",
            brand="Cisco",
            model="CBS350-24P-4G",
            serial_number="DEMO-SW-024",
            ip_address="192.168.1.250",
            mac_address="00:27:10:77:88:99",
            sede="Sitio de Prueba",
            location_detail="Rack de Distribución General",
            status="Operativo",
            created_at=now - datetime.timedelta(days=30)
        )
    ]
    db.add_all(devices_data)
    db.commit()
    for d in devices_data:
        db.refresh(d)

    # 5. Tickets de Incidencias Contextualizados (Desactivados: los incidentes solo existen cuando el usuario los crea)
    incidents_data = []

    # 6. Órdenes de Mantenimiento Preventivo y Correctivo (Desactivados: solo cuando el usuario los crea)
    maint_data = []

    # 7. Eventos de Bitácora (Solo se generan con la interacción operativa)
    # 8. Registro de Auditoría Inicial
    audit_data = [
        AuditLog(
            user_id=user_admin.id,
            username=user_admin.username,
            action="DEMO_SANDBOX_INITIALIZED",
            details="Entorno Sandbox volátil en memoria iniciado correctamente para los 4 municipios.",
            ip_address="127.0.0.1",
            timestamp=now
        )
    ]
    db.add_all(audit_data)
    db.commit()

    from app.utils.signature import ensure_seed_signatures
    ensure_seed_signatures(db)

    print("[+] [Modo Demo] Entorno Sandbox volátil en memoria generado exitosamente:")
    print("    - Municipios: 4 (San Agustín, San José del Guaviare, El Retorno, Calamar)")
    print(f"    - Usuarios Institucionales: {len([user_admin, user_sup_huila, user_sup_guaviare, user_mantenimiento, user_tecnico])}")
    print(f"    - Equipos CCTV: {len(devices_data)} (PTZ, Domo, Bala, NVR, PoE, UPS)")
    print(f"    - Incidentes Registrados: {len(incidents_data)}")
    print(f"    - Órdenes de Mantenimiento: {len(maint_data)}")


if __name__ == "__main__":
    from app.database import engine, Base, SessionLocal
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        seed_demo_data(session)
    finally:
        session.close()
