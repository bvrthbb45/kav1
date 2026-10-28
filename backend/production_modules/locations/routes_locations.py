# routes_locations.py
# ---------------------------------------------------------------------------
# Optional feature "שליטה ומיקומים" (control & locations):
#   * escort + location rows per project,
#   * uploaded site maps (stored inside the database file, so a DB backup
#     covers them and nothing leaves the network),
#   * a point (x, y) per row placed on a map.
# Also holds the admin switches "locations enabled" and "group list by project".
#
# Safety: only NEW tables are created; no existing data is touched. The feature
# is OFF until an administrator turns it on, and while OFF every endpoint except
# the switches answers 404. Turning it off never deletes data.
# ---------------------------------------------------------------------------

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
)
from sqlalchemy.orm import Session

from . import models, database, settings_store
from .dependencies import get_current_user, require_permission

VIEW_PERMISSION = "locations.view"
EDIT_PERMISSION = "locations.edit"
SETTINGS_PERMISSION = "admin.settings"

LOCATION_PERMISSIONS = [
    (VIEW_PERMISSION, "צפייה בשליטה ומיקומים", "שליטה ומיקומים"),
    (EDIT_PERMISSION, "עריכת שליטה ומיקומים ומפות", "שליטה ומיקומים"),
]

FLAG_LOCATIONS = "locations.enabled"
FLAG_GROUPING = "list.group_by_project"
FLAG_REQUIRE_INFOSEC = "visitors.require_infosec"
KEY_EXPIRY_DAYS = "visitors.expiry_warn_days"
DEFAULT_EXPIRY_DAYS = 30
ALLOWED_EXPIRY_DAYS = (7, 14, 30, 60, 90)

MAX_MAP_BYTES = 15 * 1024 * 1024
MAX_TEXT = 200
IMAGE_TYPES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
}


# ----------------------------------------------------------------- tables
class FeatureFlag(models.Base):
    __tablename__ = "kav1_feature_flags"
    key = Column(String(80), primary_key=True)
    value = Column(String(20), nullable=False, default="0")


class LocationMap(models.Base):
    __tablename__ = "location_maps"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(MAX_TEXT), nullable=False)
    content_type = Column(String(40), nullable=False)
    data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class LocationEntry(models.Base):
    __tablename__ = "location_entries"
    id = Column(Integer, primary_key=True, index=True)
    project = Column(String(MAX_TEXT), nullable=False, index=True)
    escort_name = Column(String(MAX_TEXT), nullable=False, default="")
    location_text = Column(String(MAX_TEXT), nullable=False, default="")
    map_id = Column(Integer, ForeignKey("location_maps.id"), nullable=True)
    x = Column(Float, nullable=True)  # 0..1 of the map width
    y = Column(Float, nullable=True)  # 0..1 of the map height
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ----------------------------------------------------------------- helpers
def _flag(db: Session, key: str) -> bool:
    row = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
    return row is not None and row.value == "1"


def _set_flag(db: Session, key: str, on: bool) -> None:
    row = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
    if row is None:
        db.add(FeatureFlag(key=key, value="1" if on else "0"))
    else:
        row.value = "1" if on else "0"


def get_int_setting(db: Session, key: str, default: int) -> int:
    row = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
    try:
        return int(row.value) if row is not None else default
    except (TypeError, ValueError):
        return default


def _set_text(db: Session, key: str, value: str) -> None:
    row = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
    if row is None:
        db.add(FeatureFlag(key=key, value=value))
    else:
        row.value = value


def flag_enabled(db: Session, key: str) -> bool:
    return _flag(db, key)


def _require_enabled(
    _user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
) -> None:
    """404 while the feature is off (after the login check, so nothing leaks to strangers)."""
    if not _flag(db, FLAG_LOCATIONS):
        raise HTTPException(status_code=404, detail="Not found")


def _clean(text: Optional[str], field: str, required: bool = False) -> str:
    value = (text or "").strip()
    if required and not value:
        raise HTTPException(status_code=422, detail="%s is required" % field)
    if len(value) > MAX_TEXT:
        raise HTTPException(status_code=422, detail="%s is too long" % field)
    return value


def _entry_dict(e: LocationEntry) -> dict:
    return {
        "id": e.id,
        "project": e.project,
        "escort_name": e.escort_name,
        "location_text": e.location_text,
        "map_id": e.map_id,
        "x": e.x,
        "y": e.y,
    }


def _check_point(map_id, x, y, db: Session) -> None:
    if (x is None) != (y is None):
        raise HTTPException(status_code=422, detail="x and y go together")
    if x is None:
        return
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise HTTPException(status_code=422, detail="point outside the map")
    if map_id is None or db.get(LocationMap, map_id) is None:
        raise HTTPException(status_code=422, detail="unknown map")


def ensure_locations_permissions(db: Session) -> None:
    """Idempotent: register the two permissions and give them to the admin role only."""
    from .seed import ADMIN_ROLE_NAME

    existing = {p.key for p in db.query(models.Permission).all()}
    for key, label, group in LOCATION_PERMISSIONS:
        if key not in existing:
            db.add(models.Permission(key=key, label=label, group=group))
    db.commit()
    role = db.query(models.Role).filter(models.Role.name == ADMIN_ROLE_NAME).first()
    if role is None:
        return
    have = {
        rp.permission_key
        for rp in db.query(models.RolePermission).filter(
            models.RolePermission.role_id == role.id
        )
    }
    for key, _label, _group in LOCATION_PERMISSIONS:
        if key not in have:
            db.add(models.RolePermission(role_id=role.id, permission_key=key))
    db.commit()


# ----------------------------------------------------------------- schemas
class FlagsUpdate(BaseModel):
    locations_enabled: Optional[bool] = None
    group_by_project: Optional[bool] = None
    require_infosec: Optional[bool] = None
    expiry_days: Optional[int] = None


class EntryIn(BaseModel):
    project: str = Field(..., max_length=MAX_TEXT)
    escort_name: str = Field("", max_length=MAX_TEXT)
    location_text: str = Field("", max_length=MAX_TEXT)
    map_id: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None


class MapRename(BaseModel):
    name: str = Field(..., max_length=MAX_TEXT)


router = APIRouter(prefix="/locations", tags=["locations"])


# ----------------------------------------------------------------- switches
@router.get("/flags")
def get_flags(
    _user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db),
):
    return {
        "locations_enabled": _flag(db, FLAG_LOCATIONS),
        "group_by_project": _flag(db, FLAG_GROUPING),
        "require_infosec": _flag(db, FLAG_REQUIRE_INFOSEC),
        "expiry_days": get_int_setting(db, KEY_EXPIRY_DAYS, DEFAULT_EXPIRY_DAYS),
    }


@router.put("/flags")
def put_flags(
    payload: FlagsUpdate,
    _user: models.User = Depends(require_permission(SETTINGS_PERMISSION)),
    db: Session = Depends(database.get_db),
):
    changes = []

    def _on_off(label, value):
        changes.append("%s: %s" % (label, "הופעל" if value else "כובה"))

    if payload.locations_enabled is not None:
        _set_flag(db, FLAG_LOCATIONS, payload.locations_enabled)
        _on_off("שליטה ומיקומים", payload.locations_enabled)
    if payload.group_by_project is not None:
        _set_flag(db, FLAG_GROUPING, payload.group_by_project)
        _on_off("קיבוץ לפי פרויקט", payload.group_by_project)
    if payload.require_infosec is not None:
        _set_flag(db, FLAG_REQUIRE_INFOSEC, payload.require_infosec)
        _on_off("חובה לבחור אבטחת מידע", payload.require_infosec)
    if payload.expiry_days is not None:
        if payload.expiry_days not in ALLOWED_EXPIRY_DAYS:
            raise HTTPException(
                status_code=422,
                detail="expiry_days must be one of %s" % (ALLOWED_EXPIRY_DAYS,),
            )
        _set_text(db, KEY_EXPIRY_DAYS, str(payload.expiry_days))
        changes.append("ימי התראת תוקף: %d" % payload.expiry_days)
    db.commit()
    if changes:
        settings_store.audit(db, _user, "features.update", "; ".join(changes))
    return get_flags(_user, db)


# ----------------------------------------------------------------- maps
@router.get("/maps", dependencies=[Depends(_require_enabled)])
def list_maps(
    _user: models.User = Depends(require_permission(VIEW_PERMISSION)),
    db: Session = Depends(database.get_db),
):
    rows = (
        db.query(LocationMap.id, LocationMap.name, LocationMap.created_at)
        .order_by(LocationMap.id)
        .all()
    )
    return [{"id": r.id, "name": r.name, "created_at": r.created_at} for r in rows]


@router.post(
    "/maps",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_enabled)],
)
async def upload_map(
    request: Request,
    name: str,
    _user: models.User = Depends(require_permission(EDIT_PERMISSION)),
    db: Session = Depends(database.get_db),
):
    """Raw image bytes in the request body (PNG or JPEG); the name is a query parameter."""
    name = _clean(name, "name", required=True)
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_MAP_BYTES:
        raise HTTPException(status_code=413, detail="Map file is too large")
    body = await request.body()
    if len(body) > MAX_MAP_BYTES:
        raise HTTPException(status_code=413, detail="Map file is too large")
    content_type = next(
        (ct for magic, ct in IMAGE_TYPES.items() if body.startswith(magic)), None
    )
    if content_type is None:
        raise HTTPException(
            status_code=415, detail="Only PNG or JPEG maps are supported"
        )
    row = LocationMap(name=name, content_type=content_type, data=body)
    db.add(row)
    db.commit()
    settings_store.audit(db, _user, "map.upload", "הועלתה מפה: %s" % name)
    return {"id": row.id, "name": row.name}


@router.get("/maps/{map_id}/image", dependencies=[Depends(_require_enabled)])
def map_image(
    map_id: int,
    _user: models.User = Depends(require_permission(VIEW_PERMISSION)),
    db: Session = Depends(database.get_db),
):
    row = db.get(LocationMap, map_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(
        content=row.data,
        media_type=row.content_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.put("/maps/{map_id}", dependencies=[Depends(_require_enabled)])
def rename_map(
    map_id: int,
    payload: MapRename,
    _user: models.User = Depends(require_permission(EDIT_PERMISSION)),
    db: Session = Depends(database.get_db),
):
    row = db.get(LocationMap, map_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    old_name = row.name
    row.name = _clean(payload.name, "name", required=True)
    db.commit()
    settings_store.audit(db, _user, "map.rename", "%s ← %s" % (old_name, row.name))
    return {"id": row.id, "name": row.name}


@router.delete("/maps/{map_id}", dependencies=[Depends(_require_enabled)])
def delete_map(
    map_id: int,
    _user: models.User = Depends(require_permission(EDIT_PERMISSION)),
    db: Session = Depends(database.get_db),
):
    """Removes only the map picture; the rows that used it keep their text and lose the point."""
    row = db.get(LocationMap, map_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    for e in db.query(LocationEntry).filter(LocationEntry.map_id == map_id):
        e.map_id = None
        e.x = None
        e.y = None
    map_name = row.name
    db.delete(row)
    db.commit()
    settings_store.audit(db, _user, "map.delete", "נמחקה מפה: %s" % map_name)
    return {"detail": "deleted"}


# ----------------------------------------------------------------- entries
@router.get("/entries", dependencies=[Depends(_require_enabled)])
def list_entries(
    project: Optional[str] = None,
    _user: models.User = Depends(require_permission(VIEW_PERMISSION)),
    db: Session = Depends(database.get_db),
):
    q = db.query(LocationEntry)
    if project:
        q = q.filter(LocationEntry.project == project)
    return [_entry_dict(e) for e in q.order_by(LocationEntry.project, LocationEntry.id)]


@router.post(
    "/entries",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_enabled)],
)
def create_entry(
    payload: EntryIn,
    _user: models.User = Depends(require_permission(EDIT_PERMISSION)),
    db: Session = Depends(database.get_db),
):
    _check_point(payload.map_id, payload.x, payload.y, db)
    e = LocationEntry(
        project=_clean(payload.project, "project", required=True),
        escort_name=_clean(payload.escort_name, "escort_name"),
        location_text=_clean(payload.location_text, "location_text"),
        map_id=payload.map_id if payload.x is not None else None,
        x=payload.x,
        y=payload.y,
    )
    db.add(e)
    db.commit()
    return _entry_dict(e)


@router.put("/entries/{entry_id}", dependencies=[Depends(_require_enabled)])
def update_entry(
    entry_id: int,
    payload: EntryIn,
    _user: models.User = Depends(require_permission(EDIT_PERMISSION)),
    db: Session = Depends(database.get_db),
):
    e = db.get(LocationEntry, entry_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Not found")
    _check_point(payload.map_id, payload.x, payload.y, db)
    e.project = _clean(payload.project, "project", required=True)
    e.escort_name = _clean(payload.escort_name, "escort_name")
    e.location_text = _clean(payload.location_text, "location_text")
    e.map_id = payload.map_id if payload.x is not None else None
    e.x = payload.x
    e.y = payload.y
    db.commit()
    return _entry_dict(e)


@router.delete("/entries/{entry_id}", dependencies=[Depends(_require_enabled)])
def delete_entry(
    entry_id: int,
    _user: models.User = Depends(require_permission(EDIT_PERMISSION)),
    db: Session = Depends(database.get_db),
):
    e = db.get(LocationEntry, entry_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(e)
    db.commit()
    return {"detail": "deleted"}
