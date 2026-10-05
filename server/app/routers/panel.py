"""Control panel for the server PC: live sync status, tablets, inventory."""

import os
import platform
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from typing import Literal, Optional
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import (
    catalog,
    diagnostics,
    events,
    excel,
    labels,
    messages,
    models,
    schemas,
    services,
    stock,
    usb_sync,
)
from ..config import BASE_DIR, DATABASE_URL, PORT
from ..database import get_db

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
STARTED_AT = time.time()


def local_only(request: Request) -> None:
    """The panel can control the server, so by default only this PC may open it."""
    if os.getenv("WAREHOUSE_PANEL_REMOTE") == "1":
        return
    host = request.client.host if request.client else ""
    if host not in LOCAL_HOSTS:
        raise HTTPException(status_code=403, detail=messages.PANEL_LOCAL_ONLY)


router = APIRouter(dependencies=[Depends(local_only)], include_in_schema=False)


# Never cached: after an update the browser must load the new panel.
NO_CACHE = {"Cache-Control": "no-store, max-age=0"}


@router.get("/panel")
def panel_page():
    return FileResponse(
        STATIC_DIR / "panel.html", media_type="text/html", headers=NO_CACHE
    )


def _version() -> str:
    """The installed version (VERSION.txt from the package), or ""."""
    try:
        text = (BASE_DIR / "VERSION.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return text.split(":", 1)[-1].strip()


@router.get("/panel/logo.png")
def panel_logo():
    return FileResponse(STATIC_DIR / "logo.png", media_type="image/png")


def _local_addresses():
    addresses = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(info[4][0])
    except OSError:
        pass
    return sorted(a for a in addresses if not a.startswith("127."))


def _epoch_ms(value: datetime) -> int:
    return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)


@router.get("/api/panel/status")
def status(after: int = 0, db: Session = Depends(get_db)):
    agent = usb_sync.current_agent
    snapshot = agent.snapshot() if agent is not None else None
    states = stock.item_states(db).values()
    day_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    return {
        "server": {
            "started_at": STARTED_AT,
            "now": time.time(),
            "hostname": socket.gethostname(),
            "addresses": _local_addresses(),
            "port": PORT,
            "database": DATABASE_URL.replace("sqlite:///", ""),
            "python": platform.python_version(),
            "version": _version(),
        },
        "usb": {
            "enabled": agent is not None,
            "disabled_reason": usb_sync.disabled_reason,
            "snapshot": snapshot,
            "check": diagnostics.check(snapshot, usb_sync.disabled_reason),
        },
        "counts": {
            # Units, not item rows: one QR can stock many.
            "items": sum(st.quantity for st in states),
            "available": sum(st.available for st in states),
            "borrowed": sum(st.borrowed for st in states),
            "issued": sum(st.issued for st in states),
            "users": db.scalar(select(func.count()).select_from(models.User)),
            "transactions": db.scalar(
                select(func.count()).select_from(models.Transaction)
            ),
            "transactions_24h": db.scalar(
                select(func.count())
                .select_from(models.Transaction)
                .where(models.Transaction.timestamp >= day_ago)
            ),
        },
        "events": events.since(after),
    }


@router.get("/api/panel/data")
def data(db: Session = Depends(get_db)):
    state = services.pull_state(db)
    names = {u.user_id: u.full_name for u in state.users}
    item_names = {i.qr_id: i.name for i in state.items}
    holders = {}
    for h in state.holdings:
        name = names.get(h.user_id, h.user_id)
        count = h.borrowed + h.issued
        holders.setdefault(h.qr_id, []).append(
            f"{name} ×{count}" if count > 1 else name
        )
    recent = db.scalars(
        select(models.Transaction)
        .order_by(models.Transaction.timestamp.desc())
        .limit(300)
    ).all()
    return {
        "categories": catalog.category_summary(db),
        "departments": catalog.department_summary(db),
        "items": [
            {
                **i.model_dump(),
                "holder_name": ", ".join(holders.get(i.qr_id, [])),
            }
            for i in state.items
        ],
        "users": [u.model_dump() for u in state.users],
        "transactions": [
            {
                "tx_id": t.tx_id,
                "qr_id": t.qr_id,
                "item_name": item_names.get(t.qr_id, t.qr_id),
                "user_id": t.user_id,
                "user_name": names.get(t.user_id, t.user_id),
                "action_type": t.action_type,
                "timestamp": _epoch_ms(t.timestamp),
                "quantity": t.quantity or 1,
                "note": t.note or "",
            }
            for t in recent
        ],
    }


@router.post("/api/panel/sync-now")
def sync_now():
    agent = usb_sync.current_agent
    if agent is None:
        return {"success": False, "message": usb_sync.disabled_reason}
    agent.request_sync()
    events.add(events.INFO, "התבקש סנכרון מיידי מהפאנל", "panel")
    return {"success": True, "message": messages.PANEL_SYNC_REQUESTED}


@router.post("/api/panel/restart-adb")
def restart_adb():
    agent = usb_sync.current_agent
    if agent is None:
        return {"success": False, "message": usb_sync.disabled_reason}
    agent.request_adb_restart()
    return {"success": True, "message": messages.PANEL_ADB_RESTARTING}


# --- Management ----------------------------------------------------------------


class ItemForm(BaseModel):
    qr_id: str = Field(min_length=1, max_length=128)
    name: str = Field(default="", max_length=200)
    category: str = Field(default="", max_length=200)
    quantity: int = Field(default=1, ge=0, le=1_000_000)
    kind: Literal["LOAN", "CONSUMABLE"] = "LOAN"
    # The serial before editing; differs from qr_id when the serial changed.
    old_qr_id: Optional[str] = Field(default=None, max_length=128)
    location: str = Field(default="", max_length=200)
    department: str = Field(default="", max_length=200)


class UserForm(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    full_name: str = Field(min_length=1, max_length=200)
    unit: str = Field(default="", max_length=200)
    old_user_id: Optional[str] = Field(default=None, max_length=64)


class CategoryForm(schemas.CategoryIn):
    old_name: Optional[str] = None


def _ok(message: str, **extra):
    return {"success": True, "message": message, **extra}


@router.post("/api/panel/items")
def save_item(form: ItemForm, db: Session = Depends(get_db)):
    name = form.name.strip() or form.category.strip()
    if not name:
        raise catalog.CatalogError("יש להזין שם פריט או סוג פריט")
    created = catalog.save_item(
        db,
        form.qr_id,
        name,
        form.category,
        form.quantity,
        form.kind,
        form.old_qr_id,
        form.location,
        form.department,
    )
    verb = "נוסף פריט" if created else "עודכן פריט"
    events.add(events.INFO, f"{verb}: {name} ({form.qr_id.strip()})", "panel")
    old = (form.old_qr_id or "").strip()
    if old and old != form.qr_id.strip():
        events.add(
            events.INFO,
            messages.ITEM_RENAMED.format(old=old, new=form.qr_id.strip()),
            "panel",
        )
    return _ok(messages.ITEM_SAVED.format(qr_id=form.qr_id.strip()))


@router.delete("/api/panel/items")
def delete_item(qr_id: str, db: Session = Depends(get_db)):
    catalog.delete_item(db, qr_id)
    events.add(events.INFO, f"נמחק פריט {qr_id}", "panel")
    return _ok(messages.ITEM_DELETED.format(qr_id=qr_id))


@router.get("/api/panel/items/card")
def item_card(qr_id: str, db: Session = Depends(get_db)):
    return catalog.item_card(db, qr_id)


@router.post("/api/panel/users")
def save_user(form: UserForm, db: Session = Depends(get_db)):
    catalog.save_user(db, form.user_id, form.full_name, form.unit, form.old_user_id)
    events.add(events.INFO, f"נשמר חייל: {form.full_name} ({form.user_id})", "panel")
    old = (form.old_user_id or "").strip()
    if old and old != form.user_id.strip():
        events.add(
            events.INFO,
            messages.USER_RENAMED.format(old=old, new=form.user_id.strip()),
            "panel",
        )
    return _ok(messages.USER_SAVED.format(user_id=form.user_id.strip()))


@router.delete("/api/panel/users")
def delete_user(user_id: str, db: Session = Depends(get_db)):
    catalog.delete_user(db, user_id)
    events.add(events.INFO, f"נמחק חייל {user_id}", "panel")
    return _ok(messages.USER_DELETED.format(user_id=user_id))


@router.get("/api/panel/users/card")
def user_card(user_id: str, db: Session = Depends(get_db)):
    return catalog.user_card(db, user_id)


@router.post("/api/panel/categories")
def save_category(form: CategoryForm, db: Session = Depends(get_db)):
    catalog.save_category(db, form.name, form.target_qty, form.old_name)
    return _ok(messages.CATEGORY_SAVED.format(name=form.name.strip()))


@router.delete("/api/panel/categories")
def delete_category(name: str, db: Session = Depends(get_db)):
    catalog.delete_category(db, name)
    return _ok(messages.CATEGORY_DELETED.format(name=name))


# --- Excel ---------------------------------------------------------------------

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(data: bytes, filename: str) -> Response:
    # RFC 5987 so Hebrew file names survive.
    disposition = (
        f"attachment; filename=report.xlsx; filename*=UTF-8''{quote(filename)}"
    )
    return Response(data, media_type=XLSX, headers={"Content-Disposition": disposition})


@router.post("/api/panel/import")
async def import_excel(request: Request, db: Session = Depends(get_db)):
    data = await request.body()
    filename = unquote(request.headers.get("x-filename", ""))
    result = excel.import_file(db, data, filename)
    events.add(
        events.SUCCESS if not result["errors"] else events.WARNING,
        f"ייבוא מקובץ {filename}: {result['message']}",
        "panel",
    )
    return _ok(result["message"], errors=result["errors"])


@router.get("/api/panel/template")
def import_template():
    return _xlsx(excel.template(), "תבנית ייבוא.xlsx")


@router.get("/api/panel/export/{report}")
def export(
    report: str,
    start: Optional[int] = Query(default=None, description="epoch ms"),
    end: Optional[int] = Query(default=None, description="epoch ms"),
    db: Session = Depends(get_db),
):
    if report not in excel.REPORTS:
        raise HTTPException(status_code=404)
    data = excel.export_report(db, report, start, end)
    stamp = datetime.now().strftime("%Y-%m-%d")
    return _xlsx(data, f"{excel.REPORTS[report]} {stamp}.xlsx")


@router.get("/api/panel/users/export")
def export_user_card(user_id: str, db: Session = Depends(get_db)):
    data = excel.export_user_card(db, user_id)
    user = db.get(models.User, user_id)
    return _xlsx(data, f"כרטיס חייל {user.full_name if user else user_id}.xlsx")


# --- QR labels -----------------------------------------------------------------


@router.get("/panel/labels", response_class=HTMLResponse)
def print_labels(
    ids: str = "", category: Optional[str] = None, db: Session = Depends(get_db)
):
    query = select(models.Item).order_by(models.Item.category, models.Item.qr_id)
    wanted = [i for i in ids.split(",") if i]
    if wanted:
        query = query.where(models.Item.qr_id.in_(wanted))
    elif category is not None:
        query = query.where(models.Item.category == category)
    return labels.render(list(db.scalars(query)))
