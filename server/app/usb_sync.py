"""Wired sync with tablets over USB, using ADB.

For tablets that cannot reach the server over a network (e.g. Wi-Fi-only
models without USB tethering). A background thread watches `adb devices`;
for every connected tablet it:

1. asks the app to export its pending work (broadcast USB_EXPORT),
2. pulls outbox.json and applies it to the database like /api/sync/push,
3. pushes inbox.json (the push results plus the full state from
   /api/sync/pull) and tells the app to import it (broadcast USB_IMPORT).

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

from . import schemas, services
from .config import BASE_DIR

log = logging.getLogger(__name__)

PACKAGE = "com.kav1.warehouse"
RECEIVER = f"{PACKAGE}/.domain.sync.UsbSyncReceiver"
ACTION_EXPORT = f"{PACKAGE}.USB_EXPORT"
ACTION_IMPORT = f"{PACKAGE}.USB_IMPORT"
REMOTE_DIR = f"/sdcard/Android/data/{PACKAGE}/files/usb-sync"

POLL_SECONDS = 3
RESYNC_SECONDS = 60
STEP_TIMEOUT_SECONDS = 30
# am broadcast flag: also deliver to apps that were never opened.
FLAG_INCLUDE_STOPPED_PACKAGES = "32"


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


class UsbSyncError(Exception):
    pass


class UsbSyncAgent(threading.Thread):
    def __init__(self, adb: str, session_factory):
        super().__init__(name="usb-sync", daemon=True)
        self.adb = adb
        self.session_factory = session_factory
        self._stop_event = threading.Event()
        self._last_sync: Dict[str, float] = {}
        self._warned: Dict[str, str] = {}

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        log.info("USB sync agent started (adb: %s)", self.adb)
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001 - never let the thread die
                log.exception("USB sync loop error")
            self._stop_event.wait(POLL_SECONDS)

    def poll_once(self) -> None:
        devices = self.devices()
        for serial in list(self._last_sync):
            if serial not in devices:
                log.info("tablet %s disconnected", serial)
                del self._last_sync[serial]
                self._warned.pop(serial, None)
        for serial, state in devices.items():
            if state == "unauthorized":
                self._warn_once(
                    serial,
                    "unauthorized",
                    "tablet %s: approve 'Allow USB debugging' on the tablet screen",
                )
            elif state == "device":
                due = time.monotonic() - self._last_sync.get(serial, -1e9)
                if due >= RESYNC_SECONDS:
                    self._last_sync[serial] = time.monotonic()
                    try:
                        self.sync(serial)
                        self._warned.pop(serial, None)
                    except UsbSyncError as e:
                        self._warn_once(serial, str(e), "tablet %s: " + str(e))
                    except Exception:  # noqa: BLE001
                        log.exception("tablet %s: USB sync failed", serial)

    def _warn_once(self, serial: str, key: str, message: str) -> None:
        if self._warned.get(serial) != key:
            self._warned[serial] = key
            log.warning(message, serial)

    # --- adb helpers ---

    def _run(self, *args: str, timeout: int = STEP_TIMEOUT_SECONDS) -> str:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        result = subprocess.run(
            [self.adb, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **kwargs,
        )
        if result.returncode != 0:
            raise UsbSyncError(
                f"adb {' '.join(args[:3])} failed: {result.stderr.strip()}"
            )
        return result.stdout

    def devices(self) -> Dict[str, str]:
        out = self._run("devices")
        found = {}
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                found[parts[0]] = parts[1]
        return found

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
        raise UsbSyncError(f"no answer from the app ({name}); is it installed?")

    # --- the exchange ---

    def sync(self, serial: str) -> Tuple[str, str]:
        if "package:" not in self._shell(serial, "pm", "path", PACKAGE):
            raise UsbSyncError("warehouse app is not installed")
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
                raise UsbSyncError("stale outbox from the app")
            with self.session_factory() as db:
                inbox = process_outbox(db, outbox)
            inbox_path.write_text(
                json.dumps(inbox, ensure_ascii=False), encoding="utf-8"
            )
            self._run("-s", serial, "push", str(inbox_path), f"{REMOTE_DIR}/inbox.json")

        self._broadcast(serial, ACTION_IMPORT, request_id)
        marker = self._wait_for_marker(serial, "import.done", request_id)
        _, status, message = (marker.split("|", 2) + ["", ""])[:3]
        log.info(
            "tablet %s (%s): sent %d actions, %d item edits, %d user edits -> %s: %s",
            serial,
            outbox.get("device_id"),
            len(outbox.get("transactions") or []),
            len(outbox.get("items") or []),
            len(outbox.get("users") or []),
            status,
            message,
        )
        return status, message


def start_background(session_factory) -> Optional[UsbSyncAgent]:
    if os.getenv("WAREHOUSE_USB_SYNC", "1") != "1":
        return None
    adb = find_adb()
    if adb is None:
        log.info("adb not found; wired USB sync disabled")
        return None
    agent = UsbSyncAgent(adb, session_factory)
    agent.start()
    return agent
