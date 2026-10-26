import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.site import Site
from app.schemas.site import SiteCreate, SiteUpdate, SiteResponse, SiteListResponse
from app.services.auth_service import RoleChecker, get_current_user
from app.services.audit_service import create_audit_log
from app.utils.timezone import get_local_now

router = APIRouter(prefix="/api/sites", tags=["Gestión de Sedes Territoriales"])

# Requiere rol de Administrador para modificaciones
admin_required = RoleChecker(["Admin"])


@router.get("", response_model=List[SiteResponse])
def get_sites(
    active_only: bool = Query(False, description="Filtrar solo sedes activas"),
    db: Session = Depends(get_db)
):
    """
    Lista las sedes territoriales registradas en el sistema.
    Permite filtrar por estado activo o inactivo.
    """
    query = db.query(Site)
    if active_only:
        query = query.filter(Site.is_active == True)
    return query.order_by(Site.name.asc()).all()


@router.get("/{site_id}", response_model=SiteResponse)
def get_site_by_id(
    site_id: str,
    db: Session = Depends(get_db)
):
    """
    Obtiene los detalles de una sede territorial específica por su identificador único.
    """
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sede territorial con ID '{site_id}' no encontrada."
        )
    return site


@router.post("", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
def create_site(
    site_in: SiteCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required)
):
    """
    Crea una nueva sede territorial dinámica (Solo Administrador).
    """
    clean_id = site_in.id.strip().lower()
    existing = db.query(Site).filter(Site.id == clean_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ya existe una sede territorial con el identificador '{clean_id}'."
        )

    new_site = Site(
        id=clean_id,
        name=site_in.name.strip(),
        full_name=site_in.full_name.strip(),
        region=site_in.region.strip() if site_in.region else "",
        badge=site_in.badge.strip() if site_in.badge else "",
        description=site_in.description.strip() if site_in.description else "",
        icon=site_in.icon or "🏛️",
        cameras_count=site_in.cameras_count or 0,
        status=site_in.status or "Operativo",
        color=site_in.color or "blue",
        default_supervisor=site_in.default_supervisor.strip() if site_in.default_supervisor else "",
        is_active=site_in.is_active if site_in.is_active is not None else True,
        created_at=get_local_now(),
        updated_at=get_local_now()
    )
    db.add(new_site)
    db.commit()
    db.refresh(new_site)

    create_audit_log(
        db,
        user_id=admin.id,
        username=admin.username,
        action="SITE_CREATED",
        details={"site_id": new_site.id, "name": new_site.name, "region": new_site.region}
    )

    return new_site


@router.patch("/{site_id}", response_model=SiteResponse)
def update_site(
    site_id: str,
    site_in: SiteUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required)
):
    """
    Actualiza la información de una sede territorial existente (Solo Administrador).
    """
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sede territorial con ID '{site_id}' no encontrada."
        )

    update_data = site_in.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        if isinstance(val, str):
            val = val.strip()
        setattr(site, field, val)

    site.updated_at = get_local_now()
    db.commit()
    db.refresh(site)

    create_audit_log(
        db,
        user_id=admin.id,
        username=admin.username,
        action="SITE_UPDATED",
        details={"site_id": site.id, "updated_fields": list(update_data.keys())}
    )

    return site


@router.delete("/{site_id}", status_code=status.HTTP_200_OK)
def deactivate_site(
    site_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required)
):
    """
    Desactiva una sede territorial (Soft delete / Desactivación operativa) (Solo Administrador).
    """
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sede territorial con ID '{site_id}' no encontrada."
        )

    site.is_active = False
    site.status = "Inactivo"
    site.updated_at = get_local_now()
    db.commit()
    db.refresh(site)

    create_audit_log(
        db,
        user_id=admin.id,
        username=admin.username,
        action="SITE_DEACTIVATED",
        details={"site_id": site.id, "name": site.name}
    )

    return {"message": f"Sede '{site.name}' ({site.id}) desactivada exitosamente.", "is_active": False}


@router.post("/{site_id}/activate", response_model=SiteResponse)
def activate_site(
    site_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_required)
):
    """
    Reactiva una sede territorial desactivada previamente (Solo Administrador).
    """
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sede territorial con ID '{site_id}' no encontrada."
        )

    site.is_active = True
    site.status = "Operativo"
    site.updated_at = get_local_now()
    db.commit()
    db.refresh(site)

    create_audit_log(
        db,
        user_id=admin.id,
        username=admin.username,
        action="SITE_ACTIVATED",
        details={"site_id": site.id, "name": site.name}
    )

    return site
