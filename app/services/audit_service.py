import json
from sqlalchemy.orm import Session
from app.models.audit import AuditLog

def create_audit_log(
    db: Session,
    user_id: int | None,
    username: str | None,
    action: str,
    details: dict | None = None,
    ip_address: str | None = None
) -> AuditLog:
    """
    Creates and persists an audit log entry.
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
    return log_entry
