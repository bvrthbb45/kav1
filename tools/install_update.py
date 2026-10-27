#!/usr/bin/env python3
"""Kav1 - one-click update installer (standalone, stdlib only, Python 3.8+).

Installs, in this order, into the production server:
  1. seed.py patch      - role permissions no longer disappear after a restart
  2. locations feature  - new file routes_locations.py + 3 lines in main.py
  3. locations.html     - copied into the web folder
Before touching anything it (a) optionally backs up the database, (b) checks that EVERY patch
applies cleanly, and only then (c) asks for confirmation. Each changed file gets a .bak_<time> copy.

  python install_update.py             install
  python install_update.py --revert    put the backups back (code only; data is never touched)
Output is plain ASCII so it is readable on any Windows console.
"""

import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATCHES = [
    (
        "seed.py - keep permissions at startup",
        "patches/seed_keep_permissions.patch.json",
    ),
    ("control & locations feature", "patches/locations_feature.patch.json"),
]
HTML = HERE / "files" / "locations.html"


def say(text=""):
    print(text, flush=True)


def clean(text):
    return text.strip().strip('"').strip("'").strip("& ").strip().strip('"').strip("'")


def ask(prompt):
    try:
        return input(prompt)
    except EOFError:
        return ""


def find_app_folder(raw):
    p = Path(clean(raw)).expanduser()
    for cand in (p, p / "app", p / "backend" / "app"):
        if (cand / "main.py").is_file() and (cand / "seed.py").is_file():
            return cand.resolve()
    return None


def find_web_folder(app):
    for cand in (
        app.parent.parent / "frontend" / "web",
        app.parent / "frontend" / "web",
        app / "frontend" / "web",
        Path.cwd() / "frontend" / "web",
        Path.cwd() / "kav1" / "frontend" / "web",
    ):
        if cand.is_dir():
            return cand.resolve()
    return None


def run_patch(patch, app, *flags):
    cmd = [
        sys.executable,
        str(HERE / "code_patch.py"),
        "--patch",
        str(HERE / patch),
        "--folder",
        str(app),
        "--plain",
        "--no-pause",
        *flags,
    ]
    res = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return res.returncode, (res.stdout + res.stderr).strip()


def backup_db(raw):
    src = Path(clean(raw)).expanduser()
    if not src.is_file():
        say("  Not a file - database backup SKIPPED.")
        return False
    dst = src.with_name(
        src.name + ".before_update_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".bak"
    )
    a = sqlite3.connect("file:%s?mode=ro" % src.as_posix(), uri=True)
    b = sqlite3.connect(str(dst))
    try:
        a.backup(b)
        ok = b.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        a.close()
        b.close()
    say("  Database backup: %s  (check: %s)" % (dst.name, ok))
    return ok == "ok"


def main():
    revert = "--revert" in sys.argv
    say("=" * 70)
    say("Kav1 update installer  -  " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    say("=" * 70)
    if sys.version_info < (3, 8):
        say("Python 3.8+ is required.")
        return 1
    say("")
    say("Step 1. Drag the server's APP folder (backend\\app - the one with main.py and")
    say("        seed.py) into this window, then press Enter.")
    app = find_app_folder(ask("> "))
    if app is None:
        say("main.py and seed.py were not found there. Nothing was changed.")
        return 1
    say("  Using: %s" % app)

    if revert:
        for title, patch in reversed(PATCHES):
            code, out = run_patch(patch, app, "--revert")
            say("  [%s] %s" % ("ok" if code == 0 else "!!", title))
            say("      " + out.replace("\n", "\n      "))
        say(
            "Reverted code files. routes_locations.py / locations.html may stay; data is untouched."
        )
        say("Restart the server.")
        return 0

    say("")
    say(
        "Step 2. (recommended) Drag the database file local_database.db here to back it up"
    )
    say("        first, or just press Enter to skip.")
    raw = ask("> ")
    if clean(raw):
        try:
            if not backup_db(raw):
                say(
                    "  The backup check did not return ok - stopping so nothing is changed."
                )
                return 1
        except Exception as e:  # noqa
            say("  Database backup FAILED (%s). Stopping so nothing is changed." % e)
            return 1

    say("")
    say(
        "Step 3. Checking that every patch fits your files (nothing is written yet) ..."
    )
    bad = False
    for title, patch in PATCHES:
        code, out = run_patch(patch, app, "--check")
        say("  [%s] %s" % ("ok" if code == 0 else "!!", title))
        if code != 0:
            bad = True
            say("      " + out.replace("\n", "\n      "))
    web = find_web_folder(app)
    if web is None:
        say("  The web folder was not found automatically.")
        say(
            "  Drag the folder that contains index.html (the one printed at server startup as"
        )
        say(
            "  'Serving web frontend from') here, or press Enter to copy locations.html yourself."
        )
        typed = clean(ask("> "))
        web = Path(typed).resolve() if typed and Path(typed).is_dir() else None
    say("  Web folder: %s" % (web or "(you will copy locations.html by hand)"))
    if bad:
        say("")
        say("Nothing was changed. Photograph this screen and send it.")
        return 1

    if (
        ask("\nInstall now?  Stop the server first.  Type Y to continue: ")
        .strip()
        .lower()
        != "y"
    ):
        say("Cancelled - nothing was changed.")
        return 0

    say("")
    for title, patch in PATCHES:
        code, out = run_patch(patch, app, "--yes")
        say("  [%s] %s" % ("ok" if code == 0 else "!!", title))
        if code != 0:
            say("      " + out.replace("\n", "\n      "))
            say(
                "Stopped. Files that were already changed have backups (.bak_*); run with --revert."
            )
            return 1
    if web is not None:
        target = web / "locations.html"
        if target.is_file():
            shutil.copy2(
                str(target),
                str(target) + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
            )
        shutil.copy2(str(HTML), str(target))
        say("  [ok] locations.html copied to %s" % web)
    else:
        say("  [..] copy files\\locations.html into the web folder by hand")

    say("")
    say("-" * 70)
    say(
        "DONE. Now: start the server, log in as admin, open  /locations.html  and tick 'Enable'."
    )
    say("The role permissions fix is active from the first restart.")
    say("-" * 70)
    return 0


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    except Exception:
        import traceback

        say("\nUNEXPECTED ERROR - photograph this screen:")
        say(traceback.format_exc())
    ask("\nPress Enter to close ...")
    sys.exit(code)
