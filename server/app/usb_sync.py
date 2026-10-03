"""Wired sync with tablets over USB, using ADB.

For tablets that cannot reach the server over a network (e.g. Wi-Fi-only
models without USB tethering). A background thread watches `adb devices`;
for every connected tablet it:

1. asks the app to export its pending work (broadcast USB_EXPORT),
2. pulls outbox.json and applies it to the database like /api/sync/push,
3. pushes inbox.json (the push results plus the full state from
   /api/sync/pull) and tells the app to import it (broadcast USB_IMPORT).

On every poll it also touches agent.alive on the tablet (so the app can show
that the server sees it) and picks up sync.request (written by the app's
manual sync button) to sync right away.

The file format must match UsbOutboxDto / UsbInboxDto in the Android app.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from . import events, schemas, services
from .config import BASE_DIR

log = logging.getLogger(__name__)

PACKAGE = "com.kav1.warehouse"
RECEIVER = f"{PACKAGE}/.domain.sync.UsbSyncReceiver"
ACTION_EXPORT = f"{PACKAGE}.USB_EXPORT"
ACTION_IMPORT = f"{PACKAGE}.USB_IMPORT"
REMOTE_DIR = f"/sdcard/Android/data/{PACKAGE}/files/usb-sync"
SYNC_REQUESTED = "SYNC_REQUESTED"

POLL_SECONDS = 3
RESYNC_SECONDS = 60
STEP_TIMEOUT_SECONDS = 30
# am broadcast flag: also deliver to apps that were never opened.
FLAG_INCLUDE_STOPPED_PACKAGES = "32"

SOURCE = "usb"

STATE_HINTS = {
    "device": "מחובר ומאושר",
    "unauthorized": "ממתין לאישור: במסך הטאבלט סמן 'אפשר תמיד ממחשב זה' ולחץ אישור",
    "offline": "לא מגיב: נתק וחבר את הכבל, או לחץ 'אתחול ADB' בפאנל",
    "no permissions": "אין הרשאה להתקן (בעיית דרייבר)",
}


def process_outbox(db: Session, outbox: dict) -> dict:
    """Apply a tablet's outbox to the database and build its inbox."""
    users = [schemas.UserIn(**u) for u in outbox.get("users") or []]
    items = [schemas.ItemIn(**i) for i in outbox.get("items") or []]
    transactions = [
        schemas.PendingTransaction(**t) for t in outbox.get("transactions") or []
    ]
    # New users/items first: transactions may reference them.
    if users:
        services.upsert_users(db, users)
    if items:
        services.upsert_items(db, items)
    push = services.push_transactions(db, transactions)
    state = services.pull_state(db)
    return {
        "request_id": outbox["request_id"],
        "push": push.model_dump(),
        "items_uploaded": [i.model_dump() for i in items],
        "users_uploaded": [u.model_dump() for u in users],
        "state": state.model_dump(),
    }


def find_adb() -> Optional[str]:
    """adb bundled next to the server, from WAREHOUSE_ADB, or on PATH."""
    configured = os.getenv("WAREHOUSE_ADB")
    if configured:
        return configured if Path(configured).exists() else None
    for name in ("adb.exe", "adb"):
        bundled = BASE_DIR / "adb" / name
        if bundled.exists():
            return str(bundled)
    return shutil.which("adb")


def parse_devices(output: str) -> Dict[str, Dict[str, str]]:
    """Parse `adb devices -l` into {serial: {"state": ..., "model": ...}}."""
    found = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2 or line.startswith(("List of devices", "*", "adb ")):
            continue
        serial = parts[0]
        # "no permissions" is two words.
        state = "no permissions" if parts[1] == "no" else parts[1]
        model = ""
        for token in parts[2:]:
            if token.startswith("model:"):
                model = token[len("model:") :]
        found[serial] = {"state": state, "model": model}
    return found


class UsbSyncError(Exception):
    pass


class UsbSyncAgent(threading.Thread):
    def __init__(self, adb: str, session_factory):
        super().__init__(name="usb-sync", daemon=True)
        self.adb = adb
        self.session_factory = session_factory
        self._stop_event = threading.Event()
        self._force_sync = threading.Event()
        self._restart_adb = threading.Event()
        self._lock = threading.Lock()
        self._last_sync: Dict[str, float] = {}
        self._tablets: Dict[str, Dict] = {}
        self.adb_ok: Optional[bool] = None
        self.adb_error = ""
        self.devices_raw = ""
        self.last_poll_at: Optional[float] = None

    # --- control (called from the panel, any thread) ---

    def stop(self) -> None:
        self._stop_event.set()

    def request_sync(self) -> None:
        self._force_sync.set()

    def request_adb_restart(self) -> None:
        self._restart_adb.set()

    def snapshot(self) -> Dict:
        with self._lock:
            return {
                "adb_path": self.adb,
                "adb_ok": self.adb_ok,
                "adb_error": self.adb_error,
                "devices_raw": self.devices_raw,
                "last_poll_at": self.last_poll_at,
                "tablets": [dict(t) for t in self._tablets.values()],
            }

    # --- loop ---

    def run(self) -> None:
        log.info("USB sync agent started (adb: %s)", self.adb)
        self._start_adb_server()
        while not self._stop_event.is_set():
            try:
                if self._restart_adb.is_set():
                    self._restart_adb.clear()
                    self._do_restart_adb()
                self.poll_once()
            except Exception:  # noqa: BLE001 - never let the thread die
                log.exception("USB sync loop error")
            self._stop_event.wait(POLL_SECONDS)

    def _start_adb_server(self) -> None:
        try:
            self._run("start-server", timeout=60)
            events.add(events.INFO, "שירות ADB הופעל, ממתין לטאבלטים בכבל", SOURCE)
        except (UsbSyncError, OSError, subprocess.TimeoutExpired) as e:
            self._set_adb_failed(f"לא ניתן להפעיל את ADB: {e}")

    def _do_restart_adb(self) -> None:
        events.add(events.INFO, "מאתחל את שירות ADB…", SOURCE)
        try:
            self._run("kill-server", timeout=20)
        except (UsbSyncError, OSError, subprocess.TimeoutExpired):
            pass
        with self._lock:
            self._tablets.clear()
        self._last_sync.clear()
        self._start_adb_server()

    def _set_adb_failed(self, message: str) -> None:
        with self._lock:
            changed = self.adb_error != message
            self.adb_ok = False
            self.adb_error = message
        if changed:
            events.add(events.ERROR, message, SOURCE)

    def poll_once(self) -> None:
        try:
            raw = self._run("devices", "-l")
        except (UsbSyncError, OSError, subprocess.TimeoutExpired) as e:
            self._set_adb_failed(f"ADB לא עונה: {e}")
            return
        found = parse_devices(raw)
        force = self._force_sync.is_set()
        self._force_sync.clear()
        now = time.time()
        with self._lock:
            self.adb_ok = True
            self.adb_error = ""
            self.devices_raw = raw.strip()
            self.last_poll_at = now
            gone = [s for s in self._tablets if s not in found]
            for serial in gone:
                del self._tablets[serial]
        for serial in gone:
            self._last_sync.pop(serial, None)
            events.add(events.INFO, f"הטאבלט {serial} נותק", SOURCE)

        for serial, info in found.items():
            self._update_tablet(serial, info, now)
            if info["state"] != "device":
                continue
            requested = self._heartbeat(serial)
            due = time.monotonic() - self._last_sync.get(serial, -1e9)
            if force or requested or due >= RESYNC_SECONDS:
                if requested:
                    events.add(
                        events.INFO, f"הטאבלט {serial} ביקש סנכרון (כפתור ידני)", SOURCE
                    )
                self._last_sync[serial] = time.monotonic()
                self._sync_and_record(serial)

    def _update_tablet(self, serial: str, info: Dict[str, str], now: float) -> None:
        with self._lock:
            tablet = self._tablets.get(serial)
            is_new = tablet is None
            if is_new:
                tablet = self._tablets[serial] = {
                    "serial": serial,
                    "first_seen": now,
                    "app_installed": None,
                    "last_sync_at": None,
                    "last_result": None,
                    "last_message": "",
                    "syncing": False,
                }
            old_state = tablet.get("state")
            tablet.update(
                state=info["state"],
                model=info["model"] or tablet.get("model", ""),
                last_seen=now,
                hint=STATE_HINTS.get(info["state"], info["state"]),
            )
        if is_new or old_state != info["state"]:
            name = f"{serial} ({info['model']})" if info["model"] else serial
            level = events.SUCCESS if info["state"] == "device" else events.WARNING
            prefix = "זוהה טאבלט בכבל" if is_new else "מצב הטאבלט השתנה"
            events.add(
                level,
                f"{prefix}: {name} – {STATE_HINTS.get(info['state'], info['state'])}",
                SOURCE,
            )

    def _set_tablet(self, serial: str, **fields) -> None:
        with self._lock:
            if serial in self._tablets:
                self._tablets[serial].update(fields)

    def _heartbeat(self, serial: str) -> bool:
        """Mark the server as present on the tablet; True if the app asked to sync."""
        d = REMOTE_DIR
        command = (
            f"mkdir -p {d} 2>/dev/null; echo {int(time.time())} > {d}/agent.alive"
            f" 2>/dev/null; if [ -f {d}/sync.request ]; then rm -f {d}/sync.request;"
            f" echo {SYNC_REQUESTED}; fi"
        )
        try:
            return SYNC_REQUESTED in self._shell(serial, command)
        except (UsbSyncError, OSError, subprocess.TimeoutExpired):
            return False

    def _sync_and_record(self, serial: str) -> None:
        self._set_tablet(serial, syncing=True)
        events.add(events.INFO, f"מתחיל סנכרון בכבל עם {serial}…", SOURCE)
        try:
            status, message, counts = self._sync(serial)
            ok = status == "ok"
            self._set_tablet(
                serial,
                app_installed=True,
                last_sync_at=time.time(),
                last_result="ok" if ok else "error",
                last_message=message,
                last_counts=counts,
            )
            events.add(
                events.SUCCESS if ok else events.WARNING,
                f"סנכרון בכבל עם {serial}: נשלחו {counts['transactions']} פעולות,"
                f" {counts['items']} עדכוני פריטים, {counts['users']} עדכוני משתמשים."
                f" תשובת הטאבלט: {message}",
                SOURCE,
            )
        except UsbSyncError as e:
            self._set_tablet(serial, last_result="error", last_message=str(e))
            events.add(events.ERROR, f"סנכרון בכבל עם {serial} נכשל: {e}", SOURCE)
        except Exception as e:  # noqa: BLE001
            log.exception("tablet %s: USB sync failed", serial)
            self._set_tablet(serial, last_result="error", last_message=str(e))
            events.add(events.ERROR, f"סנכרון בכבל עם {serial} נכשל: {e}", SOURCE)
        finally:
            self._set_tablet(serial, syncing=False)

    # --- adb helpers ---

    def _run(self, *args: str, timeout: int = STEP_TIMEOUT_SECONDS) -> str:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        # Output goes to temp files, not pipes: when adb starts its background
        # server it can inherit the pipes and keep them open, which makes a
        # pipe-based subprocess.run() hang forever on Windows.
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            result = subprocess.run(
                [self.adb, *args],
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                timeout=timeout,
                **kwargs,
            )
            out.seek(0)
            err.seek(0)
            stdout = out.read().decode("utf-8", errors="replace")
            stderr = err.read().decode("utf-8", errors="replace")
        if result.returncode != 0:
            raise UsbSyncError(
                f"adb {' '.join(args[:3])} failed: {(stderr or stdout).strip()}"
            )
        return stdout

    def devices(self) -> Dict[str, str]:
        return {s: i["state"] for s, i in parse_devices(self._run("devices")).items()}

    def _shell(self, serial: str, *args: str) -> str:
        return self._run("-s", serial, "shell", *args)

    def _broadcast(self, serial: str, action: str, request_id: str) -> None:
        self._shell(
            serial,
            "am",
            "broadcast",
            "-f",
            FLAG_INCLUDE_STOPPED_PACKAGES,
            "-a",
            action,
            "-n",
            RECEIVER,
            "--es",
            "request_id",
            request_id,
        )

    def _wait_for_marker(self, serial: str, name: str, request_id: str) -> str:
        deadline = time.monotonic() + STEP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            content = self._shell(serial, "cat", f"{REMOTE_DIR}/{name}").strip()
            if content.startswith(request_id):
                return content
            time.sleep(0.5)
        raise UsbSyncError(
            "אפליקציית המחסן בטאבלט לא ענתה. פתח את האפליקציה בטאבלט פעם אחת ונסה שוב"
        )

    # --- the exchange ---

    def sync(self, serial: str) -> Tuple[str, str]:
        status, message, _ = self._sync(serial)
        return status, message

    def _sync(self, serial: str) -> Tuple[str, str, Dict[str, int]]:
        try:
            installed = "package:" in self._shell(serial, "pm", "path", PACKAGE)
        except subprocess.TimeoutExpired as e:
            raise UsbSyncError("הטאבלט לא מגיב (תם הזמן)") from e
        self._set_tablet(serial, app_installed=installed)
        if not installed:
            raise UsbSyncError("אפליקציית המחסן לא מותקנת בטאבלט")
        try:
            return self._exchange(serial)
        except subprocess.TimeoutExpired as e:
            raise UsbSyncError("הטאבלט לא מגיב (תם הזמן)") from e

    def _exchange(self, serial: str) -> Tuple[str, str, Dict[str, int]]:
        request_id = uuid.uuid4().hex
        self._shell(serial, "mkdir", "-p", REMOTE_DIR)
        self._shell(
            serial, "rm", "-f", f"{REMOTE_DIR}/export.done", f"{REMOTE_DIR}/import.done"
        )

        self._broadcast(serial, ACTION_EXPORT, request_id)
        self._wait_for_marker(serial, "export.done", request_id)

        with tempfile.TemporaryDirectory() as tmp:
            outbox_path = Path(tmp) / "outbox.json"
            inbox_path = Path(tmp) / "inbox.json"
            self._run(
                "-s", serial, "pull", f"{REMOTE_DIR}/outbox.json", str(outbox_path)
            )
            outbox = json.loads(outbox_path.read_text(encoding="utf-8"))
            if outbox.get("request_id") != request_id:
                raise UsbSyncError("התקבל קובץ ישן מהטאבלט, ינסה שוב בסבב הבא")
            with self.session_factory() as db:
                inbox = process_outbox(db, outbox)
            inbox_path.write_text(
                json.dumps(inbox, ensure_ascii=False), encoding="utf-8"
            )
            self._run("-s", serial, "push", str(inbox_path), f"{REMOTE_DIR}/inbox.json")

        self._broadcast(serial, ACTION_IMPORT, request_id)
        marker = self._wait_for_marker(serial, "import.done", request_id)
        _, status, message = (marker.split("|", 2) + ["", ""])[:3]
        counts = {
            "transactions": len(outbox.get("transactions") or []),
            "items": len(outbox.get("items") or []),
            "users": len(outbox.get("users") or []),
        }
        log.info(
            "tablet %s (%s): %s -> %s: %s",
            serial,
            outbox.get("device_id"),
            counts,
            status,
            message,
        )
        return status, message, counts


# The running agent, for the control panel (None when wired sync is off).
current_agent: Optional[UsbSyncAgent] = None
disabled_reason = ""


def start_background(session_factory) -> Optional[UsbSyncAgent]:
    global current_agent, disabled_reason
    if os.getenv("WAREHOUSE_USB_SYNC", "1") != "1":
        disabled_reason = "סנכרון בכבל כבוי בהגדרות (WAREHOUSE_USB_SYNC=0)"
        return None
    adb = find_adb()
    if adb is None:
        disabled_reason = "הקובץ adb.exe לא נמצא בתיקיית השרת (adb\\adb.exe)"
        events.add(events.ERROR, disabled_reason, SOURCE)
        return None
    disabled_reason = ""
    current_agent = UsbSyncAgent(adb, session_factory)
    current_agent.start()
    return current_agent


def stop_background() -> None:
    global current_agent
    if current_agent is not None:
        current_agent.stop()
        current_agent = None
