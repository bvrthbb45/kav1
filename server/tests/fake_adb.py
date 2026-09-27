#!/usr/bin/env python3
"""Stand-in for adb in tests: simulates one tablet running the warehouse app.

The tablet's filesystem lives under $FAKE_ADB_ROOT. The app's side of the
protocol (UsbSyncReceiver) is emulated on `am broadcast`.
"""

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(os.environ["FAKE_ADB_ROOT"])
SERIAL = "FAKE123"


def local(remote: str) -> Path:
    return ROOT / remote.lstrip("/")


def main(argv):
    if argv == ["devices"]:
        print(f"List of devices attached\n{SERIAL}\tdevice\n")
        return 0
    assert argv[:2] == ["-s", SERIAL], argv
    cmd, rest = argv[2], argv[3:]
    if cmd == "pull":
        shutil.copy(local(rest[0]), rest[1])
    elif cmd == "push":
        local(rest[1]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(rest[0], local(rest[1]))
    elif cmd == "shell":
        return shell(rest)
    return 0


def shell(args):
    if args[:2] == ["pm", "path"]:
        print("package:/data/app/com.kav1.warehouse-1.apk")
    elif args[:2] == ["mkdir", "-p"]:
        local(args[2]).mkdir(parents=True, exist_ok=True)
    elif args[:2] == ["rm", "-f"]:
        for f in args[2:]:
            local(f).unlink(missing_ok=True)
    elif args[0] == "cat":
        path = local(args[1])
        print(path.read_text() if path.exists() else f"{args[1]}: No such file")
    elif args[:2] == ["am", "broadcast"]:
        action = args[args.index("-a") + 1]
        request_id = args[args.index("--es") + 2]
        emulate_app(action, request_id)
    return 0


def emulate_app(action, request_id):
    sync_dir = local("/sdcard/Android/data/com.kav1.warehouse/files/usb-sync")
    sync_dir.mkdir(parents=True, exist_ok=True)
    if action.endswith("USB_EXPORT"):
        outbox = json.loads((ROOT / "tablet_outbox.json").read_text())
        outbox["request_id"] = request_id
        (sync_dir / "outbox.json").write_text(json.dumps(outbox))
        (sync_dir / "export.done").write_text(request_id)
    elif action.endswith("USB_IMPORT"):
        inbox = (sync_dir / "inbox.json").read_text(encoding="utf-8")
        (ROOT / "received_inbox.json").write_text(inbox, encoding="utf-8")
        (sync_dir / "import.done").write_text(f"{request_id}|ok|done")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
