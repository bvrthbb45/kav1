"""Entry point: python main.py  (serves on 0.0.0.0:8000 by default)."""

import logging
import os
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from app.config import HOST, PORT
from app.main import app

PANEL_URL = f"http://127.0.0.1:{PORT}/panel"


def disable_console_quick_edit() -> None:
    """A click inside a Windows console window pauses the program until a key
    is pressed ("Select" mode), which looks like the server is stuck."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ENABLE_QUICK_EDIT_MODE = 0x0040
            ENABLE_EXTENDED_FLAGS = 0x0080
            kernel32.SetConsoleMode(
                handle, (mode.value & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS
            )
    except Exception:  # noqa: BLE001 - cosmetic only
        pass


def port_in_use() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def open_panel_later() -> None:
    def run():
        time.sleep(2)
        webbrowser.open(PANEL_URL)

    threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    disable_console_quick_edit()
    open_panel = os.getenv("WAREHOUSE_OPEN_PANEL") == "1"
    if port_in_use():
        print(
            f"The server is ALREADY RUNNING on port {PORT} (probably started at boot)."
        )
        print(f"Control panel: {PANEL_URL}")
        if open_panel:
            webbrowser.open(PANEL_URL)
        sys.exit(0)
    print("=" * 64)
    print(f" Olympus sync server - port {PORT}")
    print(f" Control panel: {PANEL_URL}")
    print(" Keep this window open. Close it (or Ctrl+C) to stop the server.")
    print("=" * 64)
    if open_panel:
        open_panel_later()
    uvicorn.run(app, host=HOST, port=PORT)
