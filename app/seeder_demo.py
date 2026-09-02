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


def seed_demo_data(db: Session):
    """
    Puebla la base de datos volátil en memoria con datos realistas para los 4 municipios
    y los 3 perfiles institucionales (Administrador, Supervisor de Contrato, Empresa de Mantenimiento).
    """
    print("[*] [Modo Demo] Inicializando entorno Sandbox volátil en memoria...")

    # 1. Limpieza de tablas
    db.query(Event).delete()
    db.query(Maintenance).delete()
    db.query(Incident).delete()
    db.query(Device).delete()
    db.query(AuditLog).delete()
    db.query(User).delete()
    db.query(License).delete()
    db.commit()

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
        hashed_password=get_password_hash("admin123"),
        role="Admin",
        is_active=True,
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
    # Perfil 3: Empresa de Mantenimiento (Preventivo / Correctivo)
    user_mantenimiento = User(
        username="mantenimiento_cctv",
        email="operaciones@contratistacctv.com",
        hashed_password=get_password_hash("mantenimiento123"),
        role="Operario",
        is_active=True,
        created_at=now - datetime.timedelta(days=50)
    )
    user_tecnico = User(
        username="tecnico_campo",
        email="soporte.tecnico@contratistacctv.com",
        hashed_password=get_password_hash("tecnico123"),
        role="Operario",
        is_active=True,
        created_at=now - datetime.timedelta(days=45)
    )

    db.add_all([user_admin, user_sup_general, user_sup_huila, user_sup_guaviare, user_mantenimiento, user_tecnico])
    db.commit()
    for u in [user_admin, user_sup_general, user_sup_huila, user_sup_guaviare, user_mantenimiento, user_tecnico]:
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

    # 5. Tickets de Incidencias Contextualizados
    incidents_data = [
        # San Agustín
        Incident(
            title="Pérdida de señal de video por sulfatación en conector RJ45",
            description="La cámara domo de la terminal presentó pérdida de sincronismo IP. Se detectó humedad en conector pasante.",
            priority="Media",
            status="Resuelto",
            sede="San Agustín (Huila)",
            device_id=devices_data[1].id,
            created_by_id=user_sup_huila.id,
            assigned_to_id=user_mantenimiento.id,
            created_at=now - datetime.timedelta(days=4),
            updated_at=now - datetime.timedelta(days=2)
        ),
        Incident(
            title="Mantenimiento preventivo y limpieza óptica de domo PTZ",
            description="Limpieza de burbuja de policarbonato, revisión de zoom óptico 25x y verificación de paneo continuo.",
            priority="Baja",
            status="Cerrado",
            sede="San Agustín (Huila)",
            device_id=devices_data[0].id,
            created_by_id=user_admin.id,
            assigned_to_id=user_tecnico.id,
            created_at=now - datetime.timedelta(days=8),
            updated_at=now - datetime.timedelta(days=6)
        ),

        # San José del Guaviare
        Incident(
            title="Fallo de alimentación en switch PoE tras tormenta eléctrica",
            description="Descarga atmosférica afectó puerto 8 del switch PoE alimentador de la cámara del puerto fluvial.",
            priority="Alta",
            status="En Proceso",
            sede="San José del Guaviare (Guaviare)",
            device_id=devices_data[5].id,
            created_by_id=user_sup_guaviare.id,
            assigned_to_id=user_mantenimiento.id,
            created_at=now - datetime.timedelta(hours=18),
            updated_at=now - datetime.timedelta(hours=6)
        ),
        Incident(
            title="Alerta de sobretemperatura en banco de baterías UPS Sala CAD",
            description="El sensor SNMP reporta 36°C en rack eléctrico. Se requiere inspección de sistema de climatización.",
            priority="Media",
            status="Abierto",
            sede="San José del Guaviare (Guaviare)",
            device_id=devices_data[7].id,
            created_by_id=user_admin.id,
            assigned_to_id=user_mantenimiento.id,
            created_at=now - datetime.timedelta(hours=10),
            updated_at=now - datetime.timedelta(hours=10)
        ),

        # El Retorno
        Incident(
            title="Atenuación en enlace de radiofrecuencia por desalineación",
            description="Enlace 5GHz de la entrada municipal reporta pérdida de paquetes del 12% debido a vientos fuertes.",
            priority="Alta",
            status="Abierto",
            sede="El Retorno (Guaviare)",
            device_id=devices_data[8].id,
            created_by_id=user_sup_guaviare.id,
            assigned_to_id=user_tecnico.id,
            created_at=now - datetime.timedelta(hours=22),
            updated_at=now - datetime.timedelta(hours=22)
        ),

        # Calamar
        Incident(
            title="Ajuste de enfoque nocturno y sellado estanco en muelle fluvial",
            description="Se evidenció condensación leve en cristal frontal de cámara PTZ Río Unilla en horario nocturno.",
            priority="Media",
            status="En Proceso",
            sede="Calamar (Guaviare)",
            device_id=devices_data[11].id,
            created_by_id=user_sup_guaviare.id,
            assigned_to_id=user_mantenimiento.id,
            created_at=now - datetime.timedelta(days=1),
            updated_at=now - datetime.timedelta(hours=8)
        ),

        # Sitio de Prueba (Demo)
        Incident(
            title="Pérdida intermitente de señal de video en cámara PTZ",
            description="La cámara de acceso principal reporta intermitencias en la transmisión en horas de alto tráfico.",
            priority="Alta",
            status="Abierto",
            sede="Sitio de Prueba",
            device_id=devices_data[12].id,
            created_by_id=user_admin.id,
            assigned_to_id=user_mantenimiento.id,
            created_at=now - datetime.timedelta(hours=6),
            updated_at=now - datetime.timedelta(hours=6)
        ),
        Incident(
            title="Alerta de reinicio por fluctuación de voltaje en Switch PoE",
            description="El switch PoE principal registró evento de fluctuación eléctrica y reinicio automático.",
            priority="Media",
            status="En Proceso",
            sede="Sitio de Prueba",
            device_id=devices_data[15].id,
            created_by_id=user_sup_huila.id,
            assigned_to_id=user_tecnico.id,
            created_at=now - datetime.timedelta(days=1),
            updated_at=now - datetime.timedelta(hours=4)
        )
    ]
    db.add_all(incidents_data)
    db.commit()
    for inc in incidents_data:
        db.refresh(inc)

    # 6. Órdenes de Mantenimiento Preventivo y Correctivo
    maint_data = [
        # San Agustín
        Maintenance(
            type="Preventivo",
            title="Mantenimiento preventivo semestral circuito San Agustín",
            description="Revisión de voltajes en fuentes, reapriete de borneras y limpieza de ópticas en puntos de control.",
            scheduled_date=now - datetime.timedelta(days=6),
            completed_date=now - datetime.timedelta(days=6),
            status="Completado",
            sede="San Agustín (Huila)",
            device_id=devices_data[0].id,
            incident_id=incidents_data[1].id,
            created_by_id=user_admin.id
        ),
        Maintenance(
            type="Correctivo",
            title="Sustitución de conector estanco RJ45 en Terminal",
            description="Reemplazo por conector blindado con gel antihumedad y prueba de reflectometría OK.",
            scheduled_date=now - datetime.timedelta(days=2),
            completed_date=now - datetime.timedelta(days=2),
            status="Completado",
            sede="San Agustín (Huila)",
            device_id=devices_data[1].id,
            incident_id=incidents_data[0].id,
            created_by_id=user_sup_huila.id
        ),

        # San José del Guaviare
        Maintenance(
            type="Correctivo",
            title="Reemplazo de módulo protector de sobretensión PoE",
            description="Instalación de supresor de transitorios en línea de red de cámara muelle fluvial.",
            scheduled_date=now + datetime.timedelta(hours=12),
            status="En Ejecución",
            sede="San José del Guaviare (Guaviare)",
            device_id=devices_data[5].id,
            incident_id=incidents_data[2].id,
            created_by_id=user_sup_guaviare.id
        ),

        # El Retorno
        Maintenance(
            type="Preventivo",
            title="Inspección y alineación de mástil de telecomunicaciones",
            description="Calibración de ángulo de azimut y elevación en antena punto a punto entrada Retorno.",
            scheduled_date=now + datetime.timedelta(days=1),
            status="Programado",
            sede="El Retorno (Guaviare)",
            device_id=devices_data[8].id,
            incident_id=incidents_data[4].id,
            created_by_id=user_mantenimiento.id
        ),

        # Calamar
        Maintenance(
            type="Correctivo",
            title="Mantenimiento correctivo de sellado O-ring y silica gel",
            description="Cambio de empaques estancos IP67 y recambio de pastillas antihumedad en domo fluvial.",
            scheduled_date=now + datetime.timedelta(hours=24),
            status="En Ejecución",
            sede="Calamar (Guaviare)",
            device_id=devices_data[11].id,
            incident_id=incidents_data[5].id,
            created_by_id=user_mantenimiento.id
        ),
        Maintenance(
            type="Preventivo",
            title="Revisión y sellado estanco de domos perimetrales",
            description="Inspección de empaques O-ring y verificación de estanqueidad IP67 en circuito Calamar.",
            scheduled_date=now + datetime.timedelta(days=2),
            status="Programado",
            sede="Calamar (Guaviare)",
            device_id=devices_data[11].id,
            incident_id=incidents_data[5].id,
            created_by_id=user_sup_guaviare.id
        ),

        # Sitio de Prueba (Demo)
        Maintenance(
            type="Preventivo",
            title="Mantenimiento preventivo general circuito Sitio de Prueba",
            description="Limpieza de domos, calibración de presets PTZ y verificación de fuentes de poder.",
            scheduled_date=now + datetime.timedelta(days=3),
            status="Programado",
            sede="Sitio de Prueba",
            device_id=devices_data[12].id,
            incident_id=incidents_data[6].id,
            created_by_id=user_admin.id
        )
    ]
    db.add_all(maint_data)
    db.commit()

    # 7. Eventos de Bitácora
    events_data = [
        Event(
            incident_id=incidents_data[0].id,
            user_id=user_tecnico.id,
            event_type="STATUS_CHANGE",
            description="Conector ponchado y verificado con tester de red. Video 100% restablecido.",
            created_at=now - datetime.timedelta(days=2)
        ),
        Event(
            incident_id=incidents_data[2].id,
            user_id=user_mantenimiento.id,
            event_type="STATUS_CHANGE",
            description="Técnico en sitio realizando medición de voltaje y reemplazo de supresor PoE.",
            created_at=now - datetime.timedelta(hours=6)
        )
    ]
    db.add_all(events_data)

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

    print("[+] [Modo Demo] Entorno Sandbox volátil en memoria generado exitosamente:")
    print(f"    - Municipios: 4 (San Agustín, San José del Guaviare, El Retorno, Calamar)")
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
