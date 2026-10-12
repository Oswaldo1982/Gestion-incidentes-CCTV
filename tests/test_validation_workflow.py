import datetime
from fastapi import status
from app.models.maintenance import Maintenance
from app.models.incident import Incident
from app.models.event import Event
from app.models.audit import AuditLog
from app.models.user import User


def test_single_superadmin_create_forbidden(client, admin_headers, active_license):
    """Verifica que el sistema rechace la creación de cualquier administrador secundario."""
    payload = {
        "username": "second_admin",
        "email": "second_admin@test.gov.co",
        "full_name": "Administrador Secundario",
        "document_id": "9999999999",
        "assigned_site": "Todas las Sedes",
        "role": "Admin",
        "password": "Password123!"
    }
    r = client.post("/api/users", json=payload, headers=admin_headers)
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert "No es posible registrar administradores adicionales" in r.json()["detail"]


def test_single_superadmin_upgrade_forbidden(client, admin_headers, supervisor_user, active_license):
    """Verifica que no se permita ascender a ningún usuario existente al rol de Admin."""
    r = client.patch(
        f"/api/users/{supervisor_user.id}",
        json={"role": "Admin"},
        headers=admin_headers
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert "No es posible asignar el rol Administrador" in r.json()["detail"]


def test_operational_roles_creation_allowed(client, admin_headers, active_license):
    """Verifica que se puedan crear los 3 roles operativos: Validador, Supervisor y Empresa de Mantenimiento."""
    roles_to_test = [
        ("validador_2", "val2@test.gov.co", "1111111111", "Validador", "ValPass123_45!", "776655"),
        ("supervisor_2", "sup2@test.gov.co", "2222222222", "Supervisor", "SupPass123_45!", None),
        ("contratista_2", "con2@test.gov.co", "3333333333", "Empresa de Mantenimiento", "ConPass123_45!", None)
    ]
    for uname, email, doc, role, pwd, badge in roles_to_test:
        payload = {
            "username": uname,
            "email": email,
            "full_name": f"Usuario {role}",
            "document_id": doc,
            "assigned_site": "Todas las Sedes",
            "role": role,
            "password": pwd
        }
        if badge:
            payload["badge_number"] = badge
        r = client.post("/api/users", json=payload, headers=admin_headers)
        assert r.status_code == status.HTTP_201_CREATED, f"Failed for {role}: {r.text}"
        assert r.json()["role"] == role
        if badge:
            assert r.json()["badge_number"] == badge


def test_maintenance_completion_transitions_to_pending_validation(
    client, db, supervisor_headers, mantenimiento_headers, active_license, supervisor_user, mantenimiento_user
):
    """
    Cuando la Empresa de Mantenimiento finaliza un trabajo y lo marca como completado,
    la orden cambia automáticamente a 'Pendiente de Validación'.
    """
    maint = Maintenance(
        type="Preventivo",
        title="Inspección Semestral PTZ",
        description="Mantenimiento preventivo programado",
        scheduled_date=datetime.datetime.utcnow(),
        maintenance_type="Preventivo Semestral",
        priority="Media",
        status="Programado",
        created_by_id=supervisor_user.id
    )
    db.add(maint)
    db.commit()

    # Iniciar labores
    r_start = client.patch(
        f"/api/maintenance/{maint.id}",
        json={"status": "En Ejecución"},
        headers=mantenimiento_headers
    )
    assert r_start.status_code == status.HTTP_200_OK
    assert r_start.json()["status"] == "En Ejecución"

    # Marcar como 'Completado' -> debe auto-cambiar a 'Pendiente de Validación'
    r_done = client.patch(
        f"/api/maintenance/{maint.id}",
        json={
            "status": "Completado",
            "actions_taken": "Limpieza profunda de lente, calibración y reapriete.",
            "technical_findings": "Filtro de polvo con saturación normal.",
            "recommendations": "Revisar en 6 meses."
        },
        headers=mantenimiento_headers
    )
    assert r_done.status_code == status.HTTP_200_OK
    data = r_done.json()
    assert data["status"] == "Pendiente de Validación"
    assert data["validation_status"] == "Pendiente"
    assert data["completed_by_id"] == mantenimiento_user.id
    assert data["completed_date"] is not None


def test_technician_locked_while_pending_validation(
    client, db, mantenimiento_headers, validador_headers, active_license, mantenimiento_user
):
    """
    Verifica que la edición técnica esté bloqueada para el técnico mientras la orden
    está en 'Pendiente de Validación'.
    """
    maint = Maintenance(
        type="Correctivo",
        title="Cambio de Switch PoE",
        description="Falla en puerto de subida",
        scheduled_date=datetime.datetime.utcnow(),
        status="Pendiente de Validación",
        validation_status="Pendiente",
        actions_taken="Reemplazo de módulo PoE",
        completed_by_id=mantenimiento_user.id,
        completed_date=datetime.datetime.utcnow(),
        created_by_id=mantenimiento_user.id
    )
    db.add(maint)
    db.commit()

    # Técnico intenta modificar -> Bloqueado con HTTP 403
    r_locked = client.patch(
        f"/api/maintenance/{maint.id}",
        json={"description": "Modificación no permitida"},
        headers=mantenimiento_headers
    )
    assert r_locked.status_code == status.HTTP_403_FORBIDDEN
    assert "edición técnica se encuentra bloqueada" in r_locked.json()["detail"]


def test_validador_approval_workflow(
    client, db, validador_headers, active_license, validador_user, mantenimiento_user
):
    """
    El Validador aprueba formalmente el trabajo:
    - Estado cambia a 'Conforme / Validado'.
    - validation_status cambia a 'Conforme'.
    - Se registra validator_id, validated_at y notas de conformidad.
    """
    maint = Maintenance(
        type="Proactivo",
        title="Optimización de Tasa de Bits NVR",
        description="Ajuste proactivo de codecs H.265+",
        scheduled_date=datetime.datetime.utcnow(),
        status="Pendiente de Validación",
        validation_status="Pendiente",
        actions_taken="Ajuste de perfiles de compresión H.265+",
        completed_by_id=mantenimiento_user.id,
        completed_date=datetime.datetime.utcnow(),
        created_by_id=validador_user.id
    )
    db.add(maint)
    db.commit()

    # Validador emite dictamen aprobatorio
    r_val = client.post(
        f"/api/maintenance/{maint.id}/validate",
        json={
            "action": "approve",
            "validation_notes": "Trabajo verificado satisfactoriamente. Video fluido y sin pérdidas."
        },
        headers=validador_headers
    )
    assert r_val.status_code == status.HTTP_200_OK
    data = r_val.json()
    assert data["status"] == "Conforme / Validado"
    assert data["validation_status"] == "Conforme"
    assert data["validator_id"] == validador_user.id
    assert data["validated_at"] is not None
    assert "verificado satisfactoriamente" in data["validation_notes"]

    # Verificar registro en auditoría y eventos
    event = db.query(Event).filter(Event.maintenance_id == maint.id, Event.event_type == "MAINTENANCE_VALIDATED").first()
    assert event is not None
    assert "aprobado con visto bueno técnico" in event.description


def test_validador_rejection_requires_notes(
    client, db, validador_headers, active_license, mantenimiento_user
):
    """Si el Validador intenta rechazar sin notas, debe fallar con HTTP 400."""
    maint = Maintenance(
        type="Preventivo",
        title="Mantenimiento Preventivo Cámara 4",
        description="Limpieza y sellado",
        scheduled_date=datetime.datetime.utcnow(),
        status="Pendiente de Validación",
        validation_status="Pendiente",
        created_by_id=mantenimiento_user.id
    )
    db.add(maint)
    db.commit()

    r_reject_empty = client.post(
        f"/api/maintenance/{maint.id}/validate",
        json={"action": "reject", "validation_notes": ""},
        headers=validador_headers
    )
    assert r_reject_empty.status_code == status.HTTP_400_BAD_REQUEST
    assert "observaciones técnicas de rechazo" in r_reject_empty.json()["detail"]


def test_validador_rejection_workflow(
    client, db, validador_headers, active_license, validador_user, mantenimiento_user
):
    """
    El Validador rechaza con observaciones:
    - Estado cambia a 'Rechazado'.
    - validation_status cambia a 'Rechazado'.
    - Se guardan las observaciones y el técnico puede corregir.
    """
    maint = Maintenance(
        type="Preventivo",
        title="Mantenimiento Preventivo Domo 2",
        description="Limpieza de domo",
        scheduled_date=datetime.datetime.utcnow(),
        status="Pendiente de Validación",
        validation_status="Pendiente",
        created_by_id=mantenimiento_user.id
    )
    db.add(maint)
    db.commit()

    r_reject = client.post(
        f"/api/maintenance/{maint.id}/validate",
        json={
            "action": "reject",
            "validation_notes": "El lente continúa con manchas de humedad evidentes en la foto de cierre."
        },
        headers=validador_headers
    )
    assert r_reject.status_code == status.HTTP_200_OK
    data = r_reject.json()
    assert data["status"] == "Rechazado"
    assert data["validation_status"] == "Rechazado"
    assert data["validator_id"] == validador_user.id
    assert "manchas de humedad" in data["validation_notes"]


def test_web_routes_validation_flow(
    client, db, admin_user, validador_user, mantenimiento_user
):
    """Verifica los endpoints web de cierre técnico y dictamen de validación."""
    maint = Maintenance(
        type="Preventivo",
        title="Revisión General Web",
        description="Prueba web de mantenimiento",
        scheduled_date=datetime.datetime.utcnow(),
        status="En Ejecución",
        created_by_id=admin_user.id
    )
    db.add(maint)
    db.commit()

    # 1. Login simulado como Validador mediante cookies de sesión
    from app.auth import create_access_token
    token_val = create_access_token({"sub": validador_user.username})
    client.cookies.set("access_token", f"Bearer {token_val}")

    # 2. Enviar aprobación web
    r_web_val = client.post(
        f"/maintenance/{maint.id}/validate",
        data={
            "action": "approve",
            "validation_notes": "Conformidad técnica web validada."
        },
        follow_redirects=False
    )
    assert r_web_val.status_code == status.HTTP_303_SEE_OTHER

    db.refresh(maint)
    assert maint.status in ["Validado / Conforme", "Conforme / Validado"]
    assert maint.validation_status == "Conforme"
    assert maint.validator_id == validador_user.id


def test_validador_badge_numeric_validation(client, admin_headers, active_license):
    """
    Verifica que el rol Validador requiera estrictamente un número de placa policial
    compuesto únicamente por dígitos numéricos, y que no permita duplicados.
    """
    # 1. Sin placa policial -> Falla
    r_empty = client.post("/api/users", json={
        "username": "policia_val1",
        "email": "val1_police@seguridad.gov.co",
        "full_name": "Agente Uno",
        "document_id": "99001122",
        "assigned_site": "Todas las Sedes",
        "role": "Validador",
        "password": "PolicePass123_45!",
        "badge_number": ""
    }, headers=admin_headers)
    assert r_empty.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # 2. Con caracteres no numéricos (letras o guiones) -> Falla
    r_alphanumeric = client.post("/api/users", json={
        "username": "policia_val2",
        "email": "val2_police@seguridad.gov.co",
        "full_name": "Agente Dos",
        "document_id": "99001123",
        "assigned_site": "Todas las Sedes",
        "role": "Validador",
        "password": "PolicePass123_45!",
        "badge_number": "PL-54321"
    }, headers=admin_headers)
    assert r_alphanumeric.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # 3. Con placa válida exclusivamente numérica -> Éxito (201)
    r_ok = client.post("/api/users", json={
        "username": "policia_val3",
        "email": "val3_police@seguridad.gov.co",
        "full_name": "Agente Tres",
        "document_id": "99001124",
        "assigned_site": "Todas las Sedes",
        "role": "Validador",
        "password": "PolicePass123_45!",
        "badge_number": "887766"
    }, headers=admin_headers)
    assert r_ok.status_code == status.HTTP_201_CREATED
    assert r_ok.json()["badge_number"] == "887766"

    # 4. Intento de crear otro usuario con la misma placa policial -> Falla por duplicidad
    r_dup = client.post("/api/users", json={
        "username": "policia_val4",
        "email": "val4_police@seguridad.gov.co",
        "full_name": "Agente Cuatro",
        "document_id": "99001125",
        "assigned_site": "Todas las Sedes",
        "role": "Validador",
        "password": "PolicePass123_45!",
        "badge_number": "887766"
    }, headers=admin_headers)
    assert r_dup.status_code == status.HTTP_400_BAD_REQUEST
    assert "número de placa policial ya se encuentra registrado" in r_dup.text


def test_validador_web_creation_and_24h_temp_credentials(client, db, admin_user, active_license):
    """
    Verifica la creación web del Validador con número de placa policial y contraseña temporal de 24 horas.
    """
    from app.auth import create_access_token
    token_admin = create_access_token({"sub": admin_user.username})
    client.cookies.set("access_token", f"Bearer {token_admin}")

    # 1. Crear usuario Validador vía POST /users
    r = client.post(
        "/users",
        data={
            "full_name": "Patrullero Juan Perez",
            "document_id": "5544332211",
            "email": "juan.perez@policia.gov.co",
            "role": "Validador",
            "badge_number": "654321"
        },
        follow_redirects=False
    )
    assert r.status_code == status.HTTP_303_SEE_OTHER
    assert "created_user" in r.headers["location"]
    assert "created_badge=654321" in r.headers["location"]

    # 2. Verificar que se persistió en base de datos con 24h de expiración
    new_officer = db.query(User).filter(User.badge_number == "654321").first()
    assert new_officer is not None
    assert new_officer.role == "Validador"
    assert new_officer.must_change_password is True
    assert new_officer.temp_expires_at is not None
    time_diff = new_officer.temp_expires_at - datetime.datetime.utcnow()
    # Debe expirar en aproximadamente 24 horas (al menos 23 horas y 50 minutos)
    assert time_diff.total_seconds() > 23 * 3600

    # 3. Intentar ingresar con el número de placa policial directamente mediante authenticate_user
    from app.auth import authenticate_user
    auth_with_badge = authenticate_user(db, "654321", "incorrect_pass")
    assert auth_with_badge is None


def test_validador_login_strict_email_only(client, db, active_license):
    """
    Verifica que un oficial Validador SÓLO pueda autenticarse con su correo electrónico institucional,
    rechazando cualquier intento de inicio de sesión con su número de placa policial.
    """
    from app.auth import authenticate_user, get_password_hash
    pwd = "PoliceSecret2026*"
    officer = User(
        username="policia_555",
        email="policia555@policia.gov.co",
        full_name="Agente Cinco Cinco",
        document_id="8811223344",
        badge_number="555123",
        assigned_site="Todas las Sedes",
        hashed_password=get_password_hash(pwd),
        role="Validador",
        is_active=True,
        must_change_password=True,
        temp_expires_at=datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    )
    db.add(officer)
    db.commit()

    # 1. Intento de autenticación con número de placa policial: DEBE SER RECHAZADO (None)
    auth_badge = authenticate_user(db, "555123", pwd)
    assert auth_badge is None, "El validador no debe poder iniciar sesión con el número de placa policial"

    # 2. Autenticación exclusiva con su correo electrónico institucional: DEBE SER EXITOSA
    auth_email = authenticate_user(db, "policia555@policia.gov.co", pwd)
    assert auth_email is not None, "El validador debe poder iniciar sesión con su correo electrónico"
    assert auth_email.id == officer.id


def test_validador_temp_password_expiration_after_24h(client, db, active_license):
    """
    Verifica que si transcurren más de 24 horas, las credenciales temporales sean rechazadas en el inicio de sesión.
    """
    from app.auth import get_password_hash
    pwd = "TempPassword123!"
    expired_officer = User(
        username="policia_expirado",
        email="expirado@policia.gov.co",
        full_name="Agente Expirado",
        document_id="7788990011",
        badge_number="998877",
        assigned_site="Todas las Sedes",
        hashed_password=get_password_hash(pwd),
        role="Validador",
        is_active=True,
        must_change_password=True,
        temp_expires_at=datetime.datetime.utcnow() - datetime.timedelta(hours=1)  # Expiró hace 1 hora
    )
    db.add(expired_officer)
    db.commit()

    # Intento de login web con correo institucional pero credenciales expiradas
    r_login = client.post(
        "/login",
        data={
            "site_id": "san-agustin",
            "username": "expirado@policia.gov.co",
            "password": pwd
        },
        follow_redirects=False
    )
    assert r_login.status_code == status.HTTP_401_UNAUTHORIZED
    assert "credenciales temporales han expirado" in r_login.text


def test_initial_interfaces_no_autofill_for_validador(client):
    """
    Verifica que en las interfaces iniciales (landing, login, site_login),
    se hayan eliminado todos los indicios de contraseñas y correos prellenados,
    así como las menciones de ingreso con placa.
    """
    import pathlib

    # 1. Landing page
    r_landing = client.get("/")
    assert r_landing.status_code == status.HTTP_200_OK
    content = r_landing.text
    assert "admin123" not in content
    assert "supervisor123" not in content
    assert "mantenimiento123" not in content
    assert "this.username = '';" in content
    assert "this.password = '';" in content
    assert "placa" not in content.lower()

    # 2. Login page
    r_login = client.get("/login")
    assert r_login.status_code == status.HTTP_200_OK
    login_content = r_login.text
    assert "admin123" not in login_content
    assert "supervisor123" not in login_content
    assert "mantenimiento123" not in login_content
    assert "this.username = '';" in login_content
    assert "this.password = '';" in login_content
    assert "placa" not in login_content.lower()

    # 3. Site login template
    site_login_file = pathlib.Path(__file__).parent.parent / "app" / "templates" / "site_login.html"
    assert site_login_file.exists()
    site_content = site_login_file.read_text(encoding="utf-8")
    assert "admin123" not in site_content
    assert "supervisor123" not in site_content
    assert "mantenimiento123" not in site_content
    assert "document.getElementById('username').value='';" in site_content
    assert "document.getElementById('password').value='';" in site_content
    assert "placa" not in site_content.lower()


def test_incident_completion_transitions_to_pending_validation_and_locks_technician(
    client, db, mantenimiento_headers, validador_headers, active_license, mantenimiento_user, supervisor_user
):
    """
    Cuando el personal técnico finaliza un incidente correctivo:
    1. El estado cambia automáticamente a 'Pendiente de Validación'
    2. El técnico queda bloqueado para editar la orden mientras esté en validación
    """
    incident = Incident(
        ticket_code="TKT-2026-VAL01",
        title="Falla de Enlace Switch Fibra",
        description="Pérdida de enlace óptico en nodo central",
        priority="Alta",
        fault_type="Falla Crítica",
        status="En Proceso",
        location_detail="Nodo Central",
        created_by_id=supervisor_user.id
    )
    db.add(incident)
    db.commit()

    # Técnico finaliza el incidente vía PATCH /api/incidents/{id}
    r_finish = client.patch(
        f"/api/incidents/{incident.id}",
        json={
            "status": "Cerrado",
            "root_cause": "Conector SC/APC fracturado en bandeja de distribución",
            "solution": "Fusión de pigtail monomodo y verificación de potencia -18dBm"
        },
        headers=mantenimiento_headers
    )
    assert r_finish.status_code == status.HTTP_200_OK
    data = r_finish.json()
    assert data["status"] == "Pendiente de Validación"
    assert data["validation_status"] == "Pendiente"
    assert data["closed_by_id"] == mantenimiento_user.id
    assert data["closed_at"] is not None

    # El técnico intenta editar nuevamente -> Debe retornar 403 Forbidden
    r_locked = client.patch(
        f"/api/incidents/{incident.id}",
        json={"solution": "Modificación no autorizada mientras valida policía"},
        headers=mantenimiento_headers
    )
    assert r_locked.status_code == status.HTTP_403_FORBIDDEN
    assert "edición técnica se encuentra bloqueada" in r_locked.json()["detail"]


def test_incident_approval_creates_official_pdf_certificate_and_restricts_technician(
    client, db, validador_headers, admin_headers, supervisor_headers, mantenimiento_headers,
    validador_user, mantenimiento_user, supervisor_user, active_license
):
    """
    Validación Policial de Incidente:
    - El oficial (Validador) aprueba el trabajo -> cambia a 'Validado / Conforme'.
    - Registra fecha/hora y número de placa policial.
    - Se genera el Acta Oficial Ejecutiva en PDF (%PDF-).
    - El Acta PDF SOLO puede ser consultada por Admin, Validador y Supervisor.
    - El técnico (Empresa de Mantenimiento) recibe HTTP 403 Forbidden.
    """
    incident = Incident(
        ticket_code="TKT-2026-VAL02",
        title="Reparación PTZ Domo Perimetral",
        description="Cámara perimetral sin movimiento horizontal",
        priority="Alta",
        fault_type="Falla Crítica",
        status="Pendiente de Validación",
        validation_status="Pendiente",
        root_cause="Correa dentada de rotación desgastada",
        solution="Reemplazo de servomotor y correa, calibración de presets",
        closed_by_id=mantenimiento_user.id,
        closed_at=datetime.datetime.utcnow(),
        created_by_id=supervisor_user.id
    )
    db.add(incident)
    db.commit()

    # Validador aprueba la orden vía API
    r_approve = client.post(
        f"/api/incidents/{incident.id}/validate",
        json={
            "action": "approve",
            "validation_notes": "Pruebas de patrullaje PTZ verificadas satisfactoriamente en tiempo real."
        },
        headers=validador_headers
    )
    assert r_approve.status_code == status.HTTP_200_OK
    data = r_approve.json()
    assert data["status"] == "Validado / Conforme"
    assert data["validation_status"] == "Conforme"
    assert data["validator_id"] == validador_user.id
    assert data["validated_at"] is not None

    # 1. Validador descarga el PDF oficial
    r_pdf_val = client.get(f"/api/incidents/{incident.id}/certificate.pdf", headers=validador_headers)
    assert r_pdf_val.status_code == status.HTTP_200_OK
    assert r_pdf_val.headers["content-type"] == "application/pdf"
    assert r_pdf_val.content.startswith(b"%PDF-")

    # 2. Administrador descarga el PDF oficial
    r_pdf_adm = client.get(f"/api/incidents/{incident.id}/certificate.pdf", headers=admin_headers)
    assert r_pdf_adm.status_code == status.HTTP_200_OK
    assert r_pdf_adm.content.startswith(b"%PDF-")

    # 3. Supervisor descarga el PDF oficial
    r_pdf_sup = client.get(f"/api/incidents/{incident.id}/certificate.pdf", headers=supervisor_headers)
    assert r_pdf_sup.status_code == status.HTTP_200_OK
    assert r_pdf_sup.content.startswith(b"%PDF-")

    # 4. Técnico de Mantenimiento intenta descargar el PDF -> DEBE RETORNAR 403 FORBIDDEN
    r_pdf_tech = client.get(f"/api/incidents/{incident.id}/certificate.pdf", headers=mantenimiento_headers)
    assert r_pdf_tech.status_code == status.HTTP_403_FORBIDDEN
    assert "Solo Administrador, Validador y Supervisor" in r_pdf_tech.json()["detail"]


def test_incident_rejection_resets_ticket_timer_to_zero(
    client, db, validador_headers, validador_user, mantenimiento_user, active_license
):
    """
    Si la Policía (Validador) rechaza el trabajo:
    - Exige observaciones obligatorias (si van vacías retorna 400).
    - Cambia estado a 'Rechazado'.
    - Reinicia el ticket en 'tiempo cero' asignando timer_reset_at = now.
    """
    two_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=2)
    incident = Incident(
        ticket_code="TKT-2026-REJ01",
        title="Ajuste Enfoque Entrada Principal",
        description="Imagen borrosa en acceso",
        priority="Media",
        fault_type="Falla Menor",
        status="Pendiente de Validación",
        validation_status="Pendiente",
        root_cause="Lente descalibrado",
        solution="Enfoque manual",
        created_at=two_days_ago,
        closed_by_id=mantenimiento_user.id,
        closed_at=datetime.datetime.utcnow(),
        created_by_id=mantenimiento_user.id
    )
    db.add(incident)
    db.commit()

    # 1. Rechazo sin observaciones -> Error 400
    r_no_notes = client.post(
        f"/api/incidents/{incident.id}/validate",
        json={"action": "reject", "validation_notes": "   "},
        headers=validador_headers
    )
    assert r_no_notes.status_code == status.HTTP_400_BAD_REQUEST

    # 2. Rechazo con observaciones válidas
    r_rej = client.post(
        f"/api/incidents/{incident.id}/validate",
        json={
            "action": "reject",
            "validation_notes": "El sensor infrarrojo no conmuta en visión nocturna. Corregir configuración de umbral."
        },
        headers=validador_headers
    )
    assert r_rej.status_code == status.HTTP_200_OK
    data = r_rej.json()
    assert data["status"] == "Rechazado"
    assert data["validation_status"] == "Rechazado"
    assert data["timer_reset_at"] is not None

    db.refresh(incident)
    assert incident.timer_reset_at is not None
    # El tiempo transcurrido debe reflejar reinicio (menos de 5 minutos, en vez de 2 días)
    assert "0m" in incident.elapsed_text or "0h" in incident.elapsed_text or "Hace" in incident.elapsed_text


def test_maintenance_rejection_resets_schedule_and_timer_to_zero(
    client, db, validador_headers, validador_user, mantenimiento_user, active_license
):
    """
    Al rechazar un mantenimiento preventivo:
    - timer_reset_at se establece a la hora actual.
    - scheduled_date se reinicia a ahora.
    - completed_date se restablece a None para que el técnico lo vuelva a ejecutar.
    """
    past_date = datetime.datetime.utcnow() - datetime.timedelta(days=3)
    maint = Maintenance(
        type="Preventivo",
        title="Mantenimiento Gabinete Exterior 01",
        description="Limpieza y hermeticidad",
        scheduled_date=past_date,
        status="Pendiente de Validación",
        validation_status="Pendiente",
        actions_taken="Revisión de sellos",
        completed_by_id=mantenimiento_user.id,
        completed_date=datetime.datetime.utcnow(),
        created_by_id=validador_user.id
    )
    db.add(maint)
    db.commit()

    r_reject = client.post(
        f"/api/maintenance/{maint.id}/validate",
        json={
            "action": "reject",
            "validation_notes": "El empaque de goma de la puerta del gabinete sigue roto. Reemplazarlo."
        },
        headers=validador_headers
    )
    assert r_reject.status_code == status.HTTP_200_OK
    db.refresh(maint)
    assert maint.status == "Rechazado"
    assert maint.timer_reset_at is not None
    assert maint.completed_date is None
    # scheduled_date debe ser reciente
    assert (datetime.datetime.utcnow() - maint.scheduled_date).total_seconds() < 60


def test_maintenance_certificate_pdf_access_control(
    client, db, validador_headers, admin_headers, supervisor_headers, mantenimiento_headers,
    validador_user, mantenimiento_user, active_license
):
    """
    Verifica que el Acta Oficial PDF de Mantenimiento Preventivo sólo esté disponible
    para Admin, Validador y Supervisor, bloqueando al contratista.
    """
    maint = Maintenance(
        type="Preventivo",
        title="Mantenimiento Certificado",
        description="Prueba de PDF",
        scheduled_date=datetime.datetime.utcnow(),
        status="Validado / Conforme",
        validation_status="Conforme",
        validator_id=validador_user.id,
        validated_at=datetime.datetime.utcnow(),
        completed_by_id=mantenimiento_user.id,
        completed_date=datetime.datetime.utcnow(),
        created_by_id=validador_user.id
    )
    db.add(maint)
    db.commit()

    # Validador accede
    r_val = client.get(f"/api/maintenance/{maint.id}/certificate.pdf", headers=validador_headers)
    assert r_val.status_code == status.HTTP_200_OK
    assert r_val.content.startswith(b"%PDF-")

    # Contratista intenta acceder -> 403 Forbidden
    r_tech = client.get(f"/api/maintenance/{maint.id}/certificate.pdf", headers=mantenimiento_headers)
    assert r_tech.status_code == status.HTTP_403_FORBIDDEN


def test_validation_panel_web_view_access(
    client, validador_user, mantenimiento_user, supervisor_user, admin_user, active_license
):
    """
    Verifica que la vista web '/validation' sea accesible para Validador, Supervisor y Admin,
    pero inaccesible para la Empresa de Mantenimiento (403).
    """
    from app.auth import create_access_token

    # 1. Validador
    t_val = create_access_token({"sub": validador_user.username})
    client.cookies.set("access_token", f"Bearer {t_val}")
    r_val = client.get("/validation")
    assert r_val.status_code == status.HTTP_200_OK
    assert "Validación Policial y Conformidad Técnica" in r_val.text

    # 2. Admin puede entrar a consultar y descargar
    t_adm = create_access_token({"sub": admin_user.username})
    client.cookies.set("access_token", f"Bearer {t_adm}")
    r_adm = client.get("/validation")
    assert r_adm.status_code == status.HTTP_200_OK
    assert "Modo Auditoría y Consulta" in r_adm.text or "Validación Policial y Conformidad Técnica" in r_adm.text

    # 3. Contratista -> 403 Forbidden
    t_tech = create_access_token({"sub": mantenimiento_user.username})
    client.cookies.set("access_token", f"Bearer {t_tech}")
    r_tech = client.get("/validation")
    assert r_tech.status_code == status.HTTP_403_FORBIDDEN


def test_admin_cannot_submit_validation_web_and_api(
    client, db, admin_user, admin_headers, validador_user, mantenimiento_user, active_license
):
    """
    Verifica que el Administrador NO pueda emitir dictámenes de 'Revisar y Validar':
    - Exclusivo para el rol Validador (Policía Nacional).
    """
    from app.auth import create_access_token

    # 1. Crear Incidente en Pendiente de Validación
    inc = Incident(
        title="Falla de Enlace Fibra",
        description="Pérdida de paquetes en switch",
        fault_type="Falla Crítica",
        priority="Crítica",
        status="Pendiente de Validación",
        validation_status="Pendiente",
        sede="San Agustín",
        created_by_id=admin_user.id
    )
    db.add(inc)

    # 2. Crear Mantenimiento en Pendiente de Validación
    maint = Maintenance(
        type="Preventivo",
        title="Protocolo Preventivo Trimestral",
        description="Mantenimiento de cámaras",
        scheduled_date=datetime.datetime.utcnow(),
        status="Pendiente de Validación",
        validation_status="Pendiente",
        created_by_id=admin_user.id
    )
    db.add(maint)
    db.commit()

    # Intento de validación API por Admin -> 403 Forbidden
    r_api_inc = client.post(
        f"/api/incidents/{inc.id}/validate",
        json={"action": "approve", "validation_notes": "Aprobado por admin"},
        headers=admin_headers
    )
    assert r_api_inc.status_code == status.HTTP_403_FORBIDDEN
    assert "Solo un usuario con rol Validador" in r_api_inc.json()["detail"]

    r_api_maint = client.post(
        f"/api/maintenance/{maint.id}/validate",
        json={"action": "approve", "validation_notes": "Aprobado por admin"},
        headers=admin_headers
    )
    assert r_api_maint.status_code == status.HTTP_403_FORBIDDEN

    # Intento de validación WEB por Admin -> Redirección con error de permiso denegado
    t_adm = create_access_token({"sub": admin_user.username})
    client.cookies.set("access_token", f"Bearer {t_adm}")

    r_web_inc = client.post(
        f"/incidents/{inc.id}/validate",
        data={"action": "approve", "validation_notes": "Intento de validación admin"},
        follow_redirects=False
    )
    assert r_web_inc.status_code == status.HTTP_303_SEE_OTHER
    assert "error=" in r_web_inc.headers["location"]
    assert "Validador" in r_web_inc.headers["location"]

    r_web_maint = client.post(
        f"/maintenance/{maint.id}/validate",
        data={"action": "approve", "validation_notes": "Intento de validación admin"},
        follow_redirects=False
    )
    assert r_web_maint.status_code == status.HTTP_303_SEE_OTHER
    assert "error=" in r_web_maint.headers["location"]
    assert "Validador" in r_web_maint.headers["location"]


def test_only_admin_can_access_users_and_licenses_views(
    client, admin_user, validador_user, supervisor_user, mantenimiento_user, active_license
):
    """
    Verifica que únicamente el Administrador tenga habilitadas las opciones Usuarios y Licencias.
    Cualquier otro rol es redirigido con mensaje de acceso restringido.
    """
    from app.auth import create_access_token

    # 1. Admin accede correctamente
    t_adm = create_access_token({"sub": admin_user.username})
    client.cookies.set("access_token", f"Bearer {t_adm}")

    r_users_adm = client.get("/users")
    assert r_users_adm.status_code == status.HTTP_200_OK

    r_license_adm = client.get("/license")
    assert r_license_adm.status_code == status.HTTP_200_OK

    # 2. Validador, Supervisor y Contratista son redirigidos
    non_admins = [validador_user, supervisor_user, mantenimiento_user]
    for user in non_admins:
        t_user = create_access_token({"sub": user.username})
        client.cookies.set("access_token", f"Bearer {t_user}")

        r_u = client.get("/users", follow_redirects=False)
        assert r_u.status_code == status.HTTP_303_SEE_OTHER
        assert "dashboard" in r_u.headers["location"]
        assert "error=" in r_u.headers["location"]

        r_l = client.get("/license", follow_redirects=False)
        assert r_l.status_code == status.HTTP_303_SEE_OTHER
        assert "dashboard" in r_l.headers["location"]
        assert "error=" in r_l.headers["location"]


def test_supervisor_permissions_and_restrictions_workflow(
    client, db, supervisor_user, admin_user, validador_user, sample_device, active_license
):
    """
    Verificación integral de las 5 acciones del rol Supervisor:
    1. Dashboard: Puede ingresar y crear informes en PDF. No puede cambiar nada.
    2. Incidentes & Mantenimiento: Puede ver contenido (GET 200), pero no puede realizar cambios ni crear.
    3. Validación policial: Puede acceder a la vista y al acta oficial PDF, pero no puede dictaminar.
    4. Equipos CCTV: Puede ingresar a ver el inventario, pero no puede registrar ni modificar.
    5. Estadística e Informes: Total acceso a vistas, filtros, recarga y exportación PDF.
    """
    from app.auth import create_access_token

    t_sup = create_access_token({"sub": supervisor_user.username})
    client.cookies.set("access_token", f"Bearer {t_sup}")

    # 1. Dashboard y PDF
    r_dash = client.get("/dashboard")
    assert r_dash.status_code == status.HTTP_200_OK
    assert "Dashboard Ejecutivo CCTV" in r_dash.text

    # 2. Incidentes: Ver sí, crear/modificar no
    r_inc_view = client.get("/incidents")
    assert r_inc_view.status_code == status.HTTP_200_OK
    assert "Nuevo Ticket Correctivo" in r_inc_view.text
    assert "cursor-not-allowed" in r_inc_view.text  # Botón en gris

    # Intento de crear incidente -> Redirección con error
    r_inc_post = client.post(
        "/incidents",
        data={
            "fault_type": "Falla Menor",
            "priority": "Media",
            "location_detail": "Parque Principal",
            "description": "Intento de creación por supervisor"
        },
        follow_redirects=False
    )
    assert r_inc_post.status_code == status.HTTP_303_SEE_OTHER
    assert "error=" in r_inc_post.headers["location"]

    # Crear incidente como admin para probar modificaciones del supervisor
    inc = Incident(
        ticket_number="TKT-2026-9901",
        title="Incidente Prueba Supervisor",
        description="Desc",
        status="Abierto",
        created_by_id=admin_user.id
    )
    db.add(inc)
    db.commit()

    # Intento de cambiar estado -> Redirección con error
    r_inc_status = client.post(
        f"/incidents/{inc.id}/status",
        data={"status": "En Proceso"},
        follow_redirects=False
    )
    assert r_inc_status.status_code == status.HTTP_303_SEE_OTHER
    assert "error=" in r_inc_status.headers["location"]

    # Intento de cierre -> Redirección con error
    r_inc_close = client.post(
        f"/incidents/{inc.id}/close",
        data={"root_cause": "Causa", "solution": "Solución"},
        follow_redirects=False
    )
    assert r_inc_close.status_code == status.HTTP_303_SEE_OTHER
    assert "error=" in r_inc_close.headers["location"]

    # 3. Mantenimientos: Ver sí, programar/modificar no
    r_maint_view = client.get("/maintenance")
    assert r_maint_view.status_code == status.HTTP_200_OK
    assert "Programar Mantenimiento" in r_maint_view.text
    assert "cursor-not-allowed" in r_maint_view.text  # Botón en gris

    # Intento de programar mantenimiento -> Redirección con error
    r_maint_post = client.post(
        "/maintenance",
        data={
            "type": "Preventivo",
            "maintenance_type": "Preventivo Mensual",
            "priority": "Media",
            "location_detail": "Parque Principal",
            "scheduled_date": datetime.datetime.utcnow().strftime("%d/%m/%Y %H:%M"),
            "description": "Intento mantenimiento supervisor"
        },
        follow_redirects=False
    )
    assert r_maint_post.status_code == status.HTTP_303_SEE_OTHER
    assert "error=" in r_maint_post.headers["location"]

    # Crear mantenimiento como admin para probar mutaciones
    maint = Maintenance(
        type="Preventivo",
        protocol_code="MP-2026-9901",
        title="Protocolo Prueba Supervisor",
        description="Desc",
        scheduled_date=datetime.datetime.utcnow(),
        status="Programado",
        created_by_id=admin_user.id
    )
    db.add(maint)
    db.commit()

    r_maint_status = client.post(
        f"/maintenance/{maint.id}/status",
        data={"status": "En Ejecución"},
        follow_redirects=False
    )
    assert r_maint_status.status_code == status.HTTP_303_SEE_OTHER
    assert "error=" in r_maint_status.headers["location"]

    r_maint_comp = client.post(
        f"/maintenance/{maint.id}/complete",
        data={"actions_taken": "Acciones prueba"},
        follow_redirects=False
    )
    assert r_maint_comp.status_code == status.HTTP_303_SEE_OTHER
    assert "error=" in r_maint_comp.headers["location"]

    # 4. Validación Policial: Ver sí, descargar acta sí, validar no
    r_val_view = client.get("/validation")
    assert r_val_view.status_code == status.HTTP_200_OK
    assert "Revisar y Validar" in r_val_view.text

    # Validar que si está pendiente, el botón está bloqueado y no puede dictaminar
    inc_val = Incident(
        ticket_number="TKT-2026-9902",
        title="Incidente por Validar",
        description="Desc",
        status="Pendiente de Validación",
        validation_status="Pendiente",
        created_by_id=admin_user.id
    )
    db.add(inc_val)
    db.commit()

    r_val_submit = client.post(
        f"/incidents/{inc_val.id}/validate",
        data={"action": "approve", "validation_notes": "Intento supervisor"},
        follow_redirects=False
    )
    assert r_val_submit.status_code == status.HTTP_303_SEE_OTHER
    assert "error=" in r_val_submit.headers["location"]
    assert "Validador" in r_val_submit.headers["location"]

    # Descarga de acta oficial PDF para incidente validado
    inc_validado = Incident(
        ticket_number="TKT-2026-9903",
        title="Incidente Validado",
        description="Desc",
        status="Validado / Conforme",
        validation_status="Conforme",
        validator_id=validador_user.id,
        validated_at=datetime.datetime.utcnow(),
        created_by_id=admin_user.id
    )
    db.add(inc_validado)
    db.commit()

    r_cert = client.get(f"/incidents/{inc_validado.id}/certificate.pdf")
    assert r_cert.status_code == status.HTTP_200_OK
    assert r_cert.headers["content-type"] == "application/pdf"

    # 5. Equipos CCTV: Ver sí, registrar no
    r_dev_view = client.get("/devices")
    assert r_dev_view.status_code == status.HTTP_200_OK
    assert "Registrar Equipo" in r_dev_view.text
    assert "cursor-not-allowed" in r_dev_view.text

    r_dev_post = client.post(
        "/devices",
        data={
            "name": "Cámara Intento Supervisor",
            "device_type": "Cámara PTZ",
            "location_detail": "Punto 1"
        },
        follow_redirects=False
    )
    assert r_dev_post.status_code == status.HTTP_303_SEE_OTHER
    assert "error=" in r_dev_post.headers["location"]

    # 6. Estadística e Informes: Total acceso
    r_rep = client.get("/reports")
    assert r_rep.status_code == status.HTTP_200_OK
    assert "Centro de Estadísticas, Mantenimiento & Auditoría" in r_rep.text

    r_rep_stats = client.get("/api/reports/stats?period=monthly")
    assert r_rep_stats.status_code == status.HTTP_200_OK
    assert "kpis" in r_rep_stats.json()

    r_rep_pdf = client.get("/reports/export/pdf?period=weekly")
    assert r_rep_pdf.status_code == status.HTTP_200_OK
    assert r_rep_pdf.headers["content-type"] == "application/pdf"




