# routes_locations.py
# ---------------------------------------------------------------------------
# Optional feature "שליטה ומיקומים" (control & locations):
#   * escort + location rows per project, each linked to an escort from the escort pool
#     (name, catalog number, phone) or typed freely,
#   * uploaded site maps (stored inside the database file, so a DB backup
#     covers them and nothing leaves the network),
#   * a point (x, y) per row placed on a map.
# Also holds the admin switches "locations enabled" and "group list by project".
#
# Safety: only NEW tables are created; no existing data is touched. The feature
# is OFF until an administrator turns it on, and while OFF every endpoint except
# the switches answers 404. Turning it off never deletes data.
# ---------------------------------------------------------------------------

import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import models, database, settings_store
from .dependencies import get_current_user, require_any_permission, require_permission

# Two levels (both are in permissions_catalog.py, so they show in the role editor):
#   locations.manage  - panel management: everything, including uploading / renaming / deleting maps
#   locations.operate - operation: place contractors on the map, assign escorts, manage the escort pool
# Either one lets a user open the page.
MANAGE_PERMISSION = "locations.manage"
OPERATE_PERMISSION = "locations.operate"
SETTINGS_PERMISSION = "admin.settings"
ANY_LEVEL = (MANAGE_PERMISSION, OPERATE_PERMISSION)

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


class LocationEscort(models.Base):
    """The escort pool: people who can be assigned as escorts."""

    __tablename__ = "location_escorts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(MAX_TEXT), nullable=False)
    catalog_number = Column(String(50), nullable=True, index=True)
    phone = Column(String(30), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class LocationEntry(models.Base):
    __tablename__ = "location_entries"
    id = Column(Integer, primary_key=True, index=True)
    project = Column(String(MAX_TEXT), nullable=False, index=True)
    escort_name = Column(String(MAX_TEXT), nullable=False, default="")
    escort_id = Column(Integer, ForeignKey("location_escorts.id"), nullable=True)
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


def _escort_dict(p: LocationEscort) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "catalog_number": p.catalog_number or "",
        "phone": p.phone or "",
        "active": bool(p.active),
    }


def _entry_dict(e: LocationEntry, pool: Optional[dict] = None) -> dict:
    p = (pool or {}).get(e.escort_id) if e.escort_id else None
    return {
        "id": e.id,
        "project": e.project,
        # a linked escort always shows the pool's current data
        "escort_id": e.escort_id,
        "escort_name": p.name if p else e.escort_name,
        "escort_phone": (p.phone or "") if p else "",
        "escort_catalog": (p.catalog_number or "") if p else "",
        "location_text": e.location_text,
        "map_id": e.map_id,
        "x": e.x,
        "y": e.y,
    }


_PHONE = re.compile(r"^[0-9+\-\s()*#.]{0,30}$")


def _escort_fields(payload: "EscortIn", db: Session, own_id: Optional[int] = None):
    name = _clean(payload.name, "name", required=True)
    catalog = (payload.catalog_number or "").strip()
    phone = (payload.phone or "").strip()
    if not _PHONE.match(phone):
        raise HTTPException(
            status_code=422, detail="phone may only hold digits and + - ( ) spaces"
        )
    if catalog:
        dup = db.query(LocationEscort).filter(LocationEscort.catalog_number == catalog)
        if own_id is not None:
            dup = dup.filter(LocationEscort.id != own_id)
        if dup.first() is not None:
            raise HTTPException(
                status_code=409,
                detail="an escort with this catalog number already exists",
            )
    return name, catalog or None, phone or None


def _resolve_escort(
    db: Session,
    escort_id: Optional[int],
    escort_name: str,
    current: Optional[int] = None,
):
    """(escort_id, name) to store. A pool escort wins over typed text; an inactive escort can only be
    kept where it is already assigned."""
    if escort_id is None:
        return None, _clean(escort_name, "escort_name")
    p = db.get(LocationEscort, escort_id)
    if p is None:
        raise HTTPException(status_code=422, detail="unknown escort")
    if not p.active and p.id != current:
        raise HTTPException(status_code=422, detail="this escort is inactive")
    return p.id, p.name


def _check_point(map_id, x, y, db: Session) -> None:
    if (x is None) != (y is None):
        raise HTTPException(status_code=422, detail="x and y go together")
    if x is None:
        return
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise HTTPException(status_code=422, detail="point outside the map")
    if map_id is None or db.get(LocationMap, map_id) is None:
        raise HTTPException(status_code=422, detail="unknown map")


def ensure_locations_setup(db: Session) -> None:
    """Idempotent, additive: adds the escort link column to a location_entries table created by an
    earlier version of this feature (create_all never alters existing tables)."""
    cols = {
        r[1] for r in db.execute(text("PRAGMA table_info(location_entries)")).fetchall()
    }
    if cols and "escort_id" not in cols:
        db.execute(
            text(
                "ALTER TABLE location_entries ADD COLUMN escort_id INTEGER REFERENCES location_escorts (id)"
            )
        )
        db.commit()


# ----------------------------------------------------------------- schemas
class FlagsUpdate(BaseModel):
    locations_enabled: Optional[bool] = None
    group_by_project: Optional[bool] = None
    require_infosec: Optional[bool] = None
    expiry_days: Optional[int] = None


class EscortIn(BaseModel):
    name: str = Field(..., max_length=MAX_TEXT)
    catalog_number: str = Field("", max_length=50)
    phone: str = Field("", max_length=30)
    active: bool = True


class EntryIn(BaseModel):
    project: str = Field(..., max_length=MAX_TEXT)
    escort_id: Optional[int] = None
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
    _user: models.User = Depends(require_any_permission(*ANY_LEVEL)),
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
    _user: models.User = Depends(require_permission(MANAGE_PERMISSION)),
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
    _user: models.User = Depends(require_any_permission(*ANY_LEVEL)),
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
    _user: models.User = Depends(require_permission(MANAGE_PERMISSION)),
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
    _user: models.User = Depends(require_permission(MANAGE_PERMISSION)),
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
# ----------------------------------------------------------------- escort pool
@router.get("/escorts", dependencies=[Depends(_require_enabled)])
def list_escorts(
    include_inactive: bool = False,
    _user: models.User = Depends(require_any_permission(*ANY_LEVEL)),
    db: Session = Depends(database.get_db),
):
    q = db.query(LocationEscort)
    if not include_inactive:
        q = q.filter(LocationEscort.active.is_(True))
    return [_escort_dict(p) for p in q.order_by(LocationEscort.name, LocationEscort.id)]


@router.post(
    "/escorts",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_enabled)],
)
def create_escort(
    payload: EscortIn,
    _user: models.User = Depends(require_any_permission(*ANY_LEVEL)),
    db: Session = Depends(database.get_db),
):
    name, catalog, phone = _escort_fields(payload, db)
    p = LocationEscort(name=name, catalog_number=catalog, phone=phone, active=True)
    db.add(p)
    db.commit()
    settings_store.audit(db, _user, "escort.create", "נוסף מלווה לפול: %s" % name)
    return _escort_dict(p)


@router.put("/escorts/{escort_id}", dependencies=[Depends(_require_enabled)])
def update_escort(
    escort_id: int,
    payload: EscortIn,
    _user: models.User = Depends(require_any_permission(*ANY_LEVEL)),
    db: Session = Depends(database.get_db),
):
    p = db.get(LocationEscort, escort_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Not found")
    p.name, p.catalog_number, p.phone = _escort_fields(payload, db, own_id=escort_id)
    p.active = bool(payload.active)
    db.commit()
    settings_store.audit(db, _user, "escort.update", "עודכן מלווה בפול: %s" % p.name)
    return _escort_dict(p)


@router.delete("/escorts/{escort_id}", dependencies=[Depends(_require_enabled)])
def delete_escort(
    escort_id: int,
    _user: models.User = Depends(require_any_permission(*ANY_LEVEL)),
    db: Session = Depends(database.get_db),
):
    """An escort that is assigned somewhere is only deactivated (the assignments keep their data);
    one that is not is removed."""
    p = db.get(LocationEscort, escort_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Not found")
    in_use = (
        db.query(LocationEntry).filter(LocationEntry.escort_id == escort_id).count()
    )
    name = p.name
    if in_use:
        p.active = False
        db.commit()
        settings_store.audit(
            db, _user, "escort.deactivate", "הושבת מלווה בפול (משויך): %s" % name
        )
        return {"detail": "deactivated", "assigned": in_use}
    db.delete(p)
    db.commit()
    settings_store.audit(db, _user, "escort.delete", "נמחק מלווה מהפול: %s" % name)
    return {"detail": "deleted"}


# ----------------------------------------------------------------- entries
@router.get("/entries", dependencies=[Depends(_require_enabled)])
def list_entries(
    project: Optional[str] = None,
    _user: models.User = Depends(require_any_permission(*ANY_LEVEL)),
    db: Session = Depends(database.get_db),
):
    q = db.query(LocationEntry)
    if project:
        q = q.filter(LocationEntry.project == project)
    pool = {p.id: p for p in db.query(LocationEscort).all()}
    return [
        _entry_dict(e, pool)
        for e in q.order_by(LocationEntry.project, LocationEntry.id)
    ]


@router.post(
    "/entries",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_enabled)],
)
def create_entry(
    payload: EntryIn,
    _user: models.User = Depends(require_any_permission(*ANY_LEVEL)),
    db: Session = Depends(database.get_db),
):
    _check_point(payload.map_id, payload.x, payload.y, db)
    escort_id, escort_name = _resolve_escort(db, payload.escort_id, payload.escort_name)
    e = LocationEntry(
        project=_clean(payload.project, "project", required=True),
        escort_id=escort_id,
        escort_name=escort_name,
        location_text=_clean(payload.location_text, "location_text"),
        map_id=payload.map_id if payload.x is not None else None,
        x=payload.x,
        y=payload.y,
    )
    db.add(e)
    db.commit()
    pool = {p.id: p for p in db.query(LocationEscort).all()}
    return _entry_dict(e, pool)


@router.put("/entries/{entry_id}", dependencies=[Depends(_require_enabled)])
def update_entry(
    entry_id: int,
    payload: EntryIn,
    _user: models.User = Depends(require_any_permission(*ANY_LEVEL)),
    db: Session = Depends(database.get_db),
):
    e = db.get(LocationEntry, entry_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Not found")
    _check_point(payload.map_id, payload.x, payload.y, db)
    escort_id, escort_name = _resolve_escort(
        db, payload.escort_id, payload.escort_name, current=e.escort_id
    )
    e.project = _clean(payload.project, "project", required=True)
    e.escort_id = escort_id
    e.escort_name = escort_name
    e.location_text = _clean(payload.location_text, "location_text")
    e.map_id = payload.map_id if payload.x is not None else None
    e.x = payload.x
    e.y = payload.y
    db.commit()
    pool = {p.id: p for p in db.query(LocationEscort).all()}
    return _entry_dict(e, pool)


@router.delete("/entries/{entry_id}", dependencies=[Depends(_require_enabled)])
def delete_entry(
    entry_id: int,
    _user: models.User = Depends(require_any_permission(*ANY_LEVEL)),
    db: Session = Depends(database.get_db),
):
    e = db.get(LocationEntry, entry_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(e)
    db.commit()
    return {"detail": "deleted"}
