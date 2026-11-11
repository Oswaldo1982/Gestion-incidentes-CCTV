import json
from sqlalchemy.orm import Session
from app.models.audit import AuditLog
from app.services.realtime_service import realtime_manager

def create_audit_log(
    db: Session,
    user_id: int | None,
    username: str | None,
    action: str,
    details: dict | None = None,
    ip_address: str | None = None
) -> AuditLog:
    """
    Creates and persists an audit log entry, and broadcasts a real-time event
    for operational changes.
    """
    details_str = None
    if details:
        try:
            details_str = json.dumps(details)
        except (TypeError, ValueError):
            details_str = str(details)
            
    log_entry = AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        details=details_str,
        ip_address=ip_address
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)

    if action and not action.startswith(("WEB_LOGIN", "DEMO_ROLE_SWITCH", "PASSWORD_RESET", "PDF_REPORT_GENERATED")):
        realtime_manager.notify(
            event_type=action,
            payload={"action": action, "username": username, "details": details or {}}
        )

    return log_entry
