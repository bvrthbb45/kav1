"""Step-by-step check of the wired (USB/ADB) tablet connection, for the panel."""

import json
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional

SAMSUNG_VENDOR = "VID_04E8"
_CACHE_SECONDS = 15

_cache_lock = threading.Lock()
_cache: Dict = {"at": 0.0, "devices": None}


def windows_usb_devices() -> Optional[List[Dict]]:
    """Samsung USB devices Windows can see (None when not on Windows)."""
    if sys.platform != "win32":
        return None
    with _cache_lock:
        if time.monotonic() - _cache["at"] < _CACHE_SECONDS:
            return _cache["devices"]
    script = (
        "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'USB\\"
        + SAMSUNG_VENDOR
        + "*' } | Select-Object FriendlyName,Status,Class,InstanceId"
        " | ConvertTo-Json -Compress"
    )
    devices: List[Dict] = []
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=20,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        text = result.stdout.decode("utf-8", errors="replace").strip()
        if text:
            parsed = json.loads(text)
            devices = parsed if isinstance(parsed, list) else [parsed]
    except Exception:  # noqa: BLE001 - diagnostics must never break the panel
        devices = []
    with _cache_lock:
        _cache.update(at=time.monotonic(), devices=devices)
    return devices


def _step(title: str, ok: Optional[bool], detail: str = "") -> Dict:
    return {"title": title, "ok": ok, "detail": detail}


def check(snapshot: Optional[Dict], disabled_reason: str) -> Dict:
    """Build the checklist; the first failing step says what to do next."""
    steps = [_step("שרת הסנכרון פועל", True)]
    if snapshot is None:
        steps.append(_step("סנכרון בכבל פעיל", False, disabled_reason))
        return {"steps": steps, "usb_devices": None}

    adb_ok = snapshot["adb_ok"]
    steps.append(
        _step(
            "שירות ADB פועל",
            adb_ok,
            snapshot["adb_error"] if adb_ok is False else "",
        )
    )

    tablets = snapshot["tablets"]
    usb = windows_usb_devices()
    if usb is not None:
        steps.append(
            _step(
                "Windows מזהה את הטאבלט בחיבור USB",
                bool(usb) or bool(tablets),
                (
                    ""
                    if usb or tablets
                    else "לא נמצא התקן Samsung. בדוק: כבל נתונים תקין (לא רק טעינה), "
                    "ב-VirtualBox בתפריט Devices > USB שהפריט SAMSUNG_Android מסומן, "
                    "ומסנן USB קבוע עם Vendor ID 04E8 בהגדרות המכונה"
                ),
            )
        )
        broken = [d for d in usb if (d.get("Status") or "OK") != "OK"]
        if usb:
            steps.append(
                _step(
                    "דרייבר USB של Samsung תקין",
                    not broken,
                    (
                        ""
                        if not broken
                        else "יש התקן עם בעיית דרייבר: "
                        + ", ".join(d.get("FriendlyName") or "?" for d in broken)
                        + ". התקן את Samsung Android USB Driver בתוך Windows הזה ונתק/חבר את הכבל"
                    ),
                )
            )

    if adb_ok:
        steps.append(
            _step(
                "איתור באגים של USB פעיל בטאבלט",
                bool(tablets),
                (
                    ""
                    if tablets
                    else "ADB לא רואה טאבלט. בטאבלט: הגדרות > אפשרויות מפתחים > "
                    "סמן 'איתור באגים של USB', ואז נתק וחבר את הכבל. "
                    "אם האפשרות מסומנת – בטל וסמן מחדש"
                ),
            )
        )
    if tablets:
        authorized = [t for t in tablets if t["state"] == "device"]
        steps.append(
            _step(
                "החיבור אושר במסך הטאבלט",
                bool(authorized),
                (
                    ""
                    if authorized
                    else "במסך הטאבלט אמורה להופיע ההודעה 'לאפשר איתור באגים של USB?'. "
                    "סמן 'אפשר תמיד ממחשב זה' ולחץ אישור. לא מופיעה? נתק וחבר את הכבל "
                    "או לחץ 'אתחול ADB'"
                ),
            )
        )
        if authorized:
            installed = [t.get("app_installed") for t in authorized]
            if False in installed:
                steps.append(
                    _step(
                        "אפליקציית המחסן מותקנת בטאבלט",
                        False,
                        "התקן את קובץ ה-APK בטאבלט",
                    )
                )
            synced = [t for t in authorized if t.get("last_result")]
            if synced:
                failed = [t for t in synced if t["last_result"] != "ok"]
                steps.append(
                    _step(
                        "הסנכרון האחרון הצליח",
                        not failed,
                        failed[0]["last_message"] if failed else "",
                    )
                )
    return {"steps": steps, "usb_devices": usb}
