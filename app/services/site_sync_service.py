"""
Servicio de Sincronización y Garantía de Homogeneidad Multi-Sede.
Garantiza que la lógica, estructura de inventario, protocolos de mantenimiento e incidentes
registrados en San Agustín se encuentren siempre reflejados y disponibles de manera idéntica
y contextualizada en las cuatro sedes territoriales:
1. San Agustín (Huila)
2. San José del Guaviare (Guaviare)
3. El Retorno (Guaviare)
4. Calamar (Guaviare)
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.device import Device


# Configuración canónica de las 4 Sedes Territoriales
TARGET_SITES: List[Dict[str, Any]] = [
    {
        "id": "san-agustin",
        "name": "San Agustín",
        "full_name": "San Agustín (Huila)",
        "code_prefix": "SA"
    },
    {
        "id": "san-jose-guaviare",
        "name": "San José del Guaviare",
        "full_name": "San José del Guaviare (Guaviare)",
        "code_prefix": "SJG"
    },
    {
        "id": "el-retorno",
        "name": "El Retorno",
        "full_name": "El Retorno (Guaviare)",
        "code_prefix": "RET"
    },
    {
        "id": "calamar",
        "name": "Calamar",
        "full_name": "Calamar (Guaviare)",
        "code_prefix": "CAL"
    }
]


def get_canonical_site_filter(model_cls, current_site: Dict[str, Any]):
    """
    Construye condiciones OR exhaustivas para filtrar registros por la sede/municipio activo
    garantizando aislamiento y coincidencia insensible a tildes o variaciones de nombre.
    """
    site_id = current_site.get("id", "")
    site_name = current_site.get("name", "")
    site_full = current_site.get("full_name", "")

    keywords = set()
    if site_name:
        keywords.add(site_name)
    if site_full:
        keywords.add(site_full)

    # Variaciones específicas por municipio para garantizar match al 100%
    if "san-agustin" in site_id or "agustin" in site_name.lower() or "agustín" in site_name.lower():
        keywords.update(["San Agustín", "San Agustin", "San Agustín (Huila)", "San Agustin (Huila)"])
    elif "guaviare" in site_id or "josé" in site_name.lower() or "jose" in site_name.lower():
        keywords.update([
            "San José del Guaviare", "San Jose del Guaviare",
            "San José del Guaviare (Guaviare)", "San Jose del Guaviare (Guaviare)",
            "San José", "San Jose"
        ])
    elif "retorno" in site_id or "retorno" in site_name.lower():
        keywords.update(["El Retorno", "El Retorno (Guaviare)", "Retorno"])
    elif "calamar" in site_id or "calamar" in site_name.lower():
        keywords.update(["Calamar", "Calamar (Guaviare)"])
    elif "prueba" in site_id or "demo" in site_id or "prueba" in site_name.lower():
        keywords.update(["Sitio de Prueba", "Sitio de Prueba (Entorno Demo)", "Entorno Demo", "Demo", "sitio-prueba"])

    conds = []
    for kw in keywords:
        conds.append(model_cls.sede == kw)
        conds.append(model_cls.sede.ilike(f"%{kw}%"))

    return or_(*conds)


def find_matching_device_in_site(
    db: Session,
    ref_device: Optional[Device],
    target_site_full_name: str,
    location_detail: Optional[str] = None
) -> Optional[Device]:
    """
    Localiza en la sede destino el equipo equivalente al de referencia
    (por nombre, tipo de equipo o ubicación física en ese municipio).
    """
    if ref_device:
        # 1. Búsqueda exacta por nombre y sede destino
        match = db.query(Device).filter(
            Device.sede == target_site_full_name,
            Device.name == ref_device.name
        ).first()
        if match:
            return match

        # 2. Búsqueda por ubicación y tipo
        match = db.query(Device).filter(
            Device.sede == target_site_full_name,
            Device.location_detail == ref_device.location_detail,
            Device.device_type == ref_device.device_type
        ).first()
        if match:
            return match

        # 3. Búsqueda por tipo de equipo en la sede
        match = db.query(Device).filter(
            Device.sede == target_site_full_name,
            Device.device_type == ref_device.device_type
        ).first()
        if match:
            return match

    if location_detail:
        match = db.query(Device).filter(
            Device.sede == target_site_full_name,
            Device.location_detail.ilike(f"%{location_detail}%"),
            Device.device_type.ilike("%cámara%")
        ).first()
        if match:
            return match
        match = db.query(Device).filter(
            Device.sede == target_site_full_name,
            Device.location_detail.ilike(f"%{location_detail}%")
        ).first()
        if match:
            return match

    # 4. Fallback al primer equipo disponible de esa sede
    return db.query(Device).filter(Device.sede == target_site_full_name).first()


def ensure_all_sites_synchronized(db: Session) -> Dict[str, Any]:
    """
    Sincronización multi-sede en pausa temporal:
    Por directriz operativa, los cambios se realizan exclusivamente para la sede San Agustín.
    Las demás tres sedes y el entorno demo se mantienen en pausa y vacíos hasta nueva orden.
    """
    return {
        "status": "paused",
        "devices_synced": 0,
        "incidents_synced": 0,
        "maintenances_synced": 0
    }

