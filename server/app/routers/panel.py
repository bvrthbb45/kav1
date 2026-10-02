"""Control panel for the server PC: live sync status, tablets, inventory."""

import os
import platform
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import diagnostics, events, messages, models, services, usb_sync
from ..config import DATABASE_URL, PORT
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


@router.get("/panel")
def panel_page():
    return FileResponse(STATIC_DIR / "panel.html", media_type="text/html")


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
    by_status = dict(
        db.execute(
            select(models.Item.current_status, func.count()).group_by(
                models.Item.current_status
            )
        ).all()
    )
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
        },
        "usb": {
            "enabled": agent is not None,
            "disabled_reason": usb_sync.disabled_reason,
            "snapshot": snapshot,
            "check": diagnostics.check(snapshot, usb_sync.disabled_reason),
        },
        "counts": {
            "items": sum(by_status.values()),
            "available": by_status.get(models.STATUS_AVAILABLE, 0),
            "borrowed": by_status.get(models.STATUS_BORROWED, 0),
            "issued": by_status.get(models.STATUS_ISSUED, 0),
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
    recent = db.scalars(
        select(models.Transaction)
        .order_by(models.Transaction.timestamp.desc())
        .limit(300)
    ).all()
    return {
        "items": [
            {
                **i.model_dump(),
                "holder_name": names.get(i.holder_user_id, i.holder_user_id or ""),
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
