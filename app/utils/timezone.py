import datetime
from typing import Optional

# Zona horaria oficial para las sedes del sistema en Colombia (UTC-5)
COLOMBIA_TZ = datetime.timezone(datetime.timedelta(hours=-5), name="America/Bogota")

def get_local_now() -> datetime.datetime:
    """
    Retorna la fecha y hora actual exacta en la zona horaria de Colombia (UTC-5).
    Se retorna como un datetime 'naive' (sin tzinfo explícito) para garantizar
    plena compatibilidad y coherencia con SQLite, SQLAlchemy y cálculos de deltas.
    """
    return datetime.datetime.now(COLOMBIA_TZ).replace(tzinfo=None)

def get_local_today() -> datetime.date:
    """Retorna la fecha local de hoy en Colombia."""
    return get_local_now().date()

def format_local_datetime(dt: Optional[datetime.datetime], fmt: str = "%d/%m/%Y %H:%M") -> str:
    """Formatea de manera segura un datetime local."""
    if not dt:
        return ""
    return dt.strftime(fmt)
