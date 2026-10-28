#!/usr/bin/env python3
"""Kav1 - one-click update installer (standalone, stdlib only, Python 3.8+).

Installs, in this order, into the production system (after a database backup and a full dry run):
  1. backend patch  - permissions fix (the real cause of permissions shrinking at restart), database
                      settings, visitor additions (latest entry first, project, expiry), optional features
  2. frontend patch - the web pages (additions only; design files are not touched) + the new page
  3. database steps - indexes on visitor_logs, ANALYZE, (optional) WAL mode
  4. verification   - every table's row count before == after, integrity check, the server code imports

Nothing is ever deleted. Visitors and their logs are counted before and after.

  python install_update.py             install
  python install_update.py --revert    put the code backups back (the database is never touched)
Output is plain ASCII so it is readable on any Windows console.
"""

import hashlib
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND_PATCH = "patches/backend.patch.json"
FRONTEND_PATCH = "patches/frontend.patch.json"
INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_visitor_logs_visitor_dbid_timestamp ON visitor_logs (visitor_dbid, timestamp)",
    "CREATE INDEX IF NOT EXISTS ix_visitor_logs_timestamp ON visitor_logs (timestamp)",
]


def say(text=""):
    print(text, flush=True)


def clean(text):
    t = text.strip()
    if t.startswith("& "):
        t = t[2:].strip()
    return t.strip('"').strip("'")


def ask(prompt):
    try:
        return input(prompt)
    except EOFError:
        return ""


# ------------------------------------------------------------------ locating things
def verify_package():
    """Every file of this package must match checksums.txt (catches damage during the transfer)."""
    f = HERE / "checksums.txt"
    if not f.is_file():
        say("  (no checksums.txt next to the installer: package integrity not checked)")
        return True
    bad = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        p = HERE / name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            bad.append(name)
    if bad:
        say(
            "  [!!] the package is damaged or incomplete (transfer problem?). Mismatching files:"
        )
        for n in bad[:12]:
            say("       " + n)
        return False
    say("  [ok] package integrity verified")
    return True


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
    ):
        if (cand / "index.html").is_file():
            return cand.resolve()
    return None


def run_patch(patch, folder, *flags):
    cmd = [
        sys.executable,
        str(HERE / "code_patch.py"),
        "--patch",
        str(HERE / patch),
        "--folder",
        str(folder),
        "--plain",
        "--no-pause",
        *flags,
    ]
    res = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return res.returncode, (res.stdout + res.stderr).strip()


# ------------------------------------------------------------------ database helpers (counts only, never names)
def table_counts(conn):
    names = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    return {
        t: conn.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0] for t in names
    }


def db_locked(path):
    try:
        conn = sqlite3.connect(str(path), timeout=0.3)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("ROLLBACK")
            return False
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return True


def backup_db(path):
    dst = path.with_name(
        path.name
        + ".before_update_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
        + ".bak"
    )
    a = sqlite3.connect("file:%s?mode=ro" % path.as_posix(), uri=True)
    b = sqlite3.connect(str(dst))
    try:
        a.backup(b)
        counts_a, counts_b = table_counts(a), table_counts(b)
        ok = b.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        a.close()
        b.close()
    if ok != "ok" or counts_a != counts_b:
        raise RuntimeError("the backup copy did not verify (integrity=%s)" % ok)
    return dst


def import_check(backend):
    """Does the patched server code still import? (no database access, no server start)"""
    res = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=str(backend),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return res.returncode == 0, (res.stdout + res.stderr).strip()


def main():
    revert = "--revert" in sys.argv
    say("=" * 70)
    say("Kav1 update installer  -  " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    say("=" * 70)
    if sys.version_info < (3, 8):
        say("Python 3.8+ is required.")
        return 1
    if not verify_package():
        say("Nothing was changed. Copy the package again and re-run.")
        return 1
    say("")
    say("Step 1. Drag the server's APP folder (backend\\app - the one with main.py and")
    say("        seed.py) into this window, then press Enter.")
    app = find_app_folder(ask("> "))
    if app is None:
        say("main.py and seed.py were not found there. Nothing was changed.")
        return 1
    backend = app.parent
    web = find_web_folder(app)
    say("  Server code : %s" % app)
    say("  Web pages   : %s" % (web or "NOT FOUND"))
    if web is None:
        say(
            "  The web folder (frontend\\web, with index.html) was not found next to the server code."
        )
        say("  Drag it here, or press Enter to stop.")
        typed = clean(ask("> "))
        web = (
            Path(typed).resolve()
            if typed and (Path(typed) / "index.html").is_file()
            else None
        )
        if web is None:
            say("Stopped. Nothing was changed.")
            return 1

    if revert:
        for title, patch, folder in (
            ("web pages", FRONTEND_PATCH, web),
            ("server code", BACKEND_PATCH, app),
        ):
            code, out = run_patch(patch, folder, "--revert")
            say("  [%s] %s" % ("ok" if code == 0 else "!!", title))
            say("      " + out.replace("\n", "\n      "))
        say(
            "Code files were restored from their backups. The database was NOT touched."
        )
        say("Restart the server.")
        return 0

    db = backend / "local_database.db"
    say("")
    say("Step 2. Database: %s" % (db if db.is_file() else "NOT FOUND here"))
    say("        Press Enter to use it, or drag another local_database.db here.")
    typed = clean(ask("> "))
    if typed:
        db = Path(typed).resolve()
    if not db.is_file():
        say(
            "  No database file: only the code will be updated (the server creates a new empty one itself)."
        )
        db = None

    # ---------------- dry run: nothing is written in this block
    say("")
    say("Step 3. Dry run - nothing is written yet ...")
    before = None
    if db is not None:
        if db_locked(db):
            say(
                "  The database is in use. STOP the Kav1 server first, then run this again."
            )
            return 1
        conn = sqlite3.connect("file:%s?mode=ro" % db.as_posix(), uri=True)
        try:
            ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
            before = table_counts(conn)
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        if ok != "ok":
            say(
                "  The database fails its integrity check (%s). Nothing was changed - send me this screen."
                % ok
            )
            return 1
        say(
            "  database ok - visitors: %s, log rows: %s, journal mode: %s"
            % (before.get("visitors", "-"), before.get("visitor_logs", "-"), journal)
        )
    bad = False
    for title, patch, folder in (
        ("server code", BACKEND_PATCH, app),
        ("web pages", FRONTEND_PATCH, web),
    ):
        code, out = run_patch(patch, folder, "--check")
        say("  [%s] %s" % ("ok" if code == 0 else "!!", title))
        if code != 0:
            bad = True
            say("      " + out.replace("\n", "\n      "))
    if bad:
        say("")
        say(
            "Nothing was changed: your files differ from the ones this update was built for."
        )
        say("Photograph this screen and send it.")
        return 1

    want_wal = False
    if db is not None and journal.lower() != "wal":
        say("")
        say(
            "  Optional: WAL mode lets readers and writers work at the same time (fewer 'locked' waits)."
        )
        say(
            "  Trade-off: the database then has side files (-wal, -shm); copy the .db only with"
        )
        say(
            "  db_portability.py or the admin backup button, or after a clean shutdown."
        )
        want_wal = (
            ask("  Switch to WAL mode? Type Y for yes, Enter for no: ").strip().lower()
            == "y"
        )

    if (
        ask("\nInstall now?  The server must be stopped.  Type Y to continue: ")
        .strip()
        .lower()
        != "y"
    ):
        say("Cancelled - nothing was changed.")
        return 0

    # ---------------- install
    say("")
    if db is not None:
        try:
            bak = backup_db(db)
        except Exception as exc:  # noqa
            say("Database backup FAILED (%s). Nothing was changed." % exc)
            return 1
        say("  [ok] database backup: %s (verified)" % bak.name)
    for title, patch, folder in (
        ("server code", BACKEND_PATCH, app),
        ("web pages", FRONTEND_PATCH, web),
    ):
        code, out = run_patch(patch, folder, "--yes")
        say("  [%s] %s" % ("ok" if code == 0 else "!!", title))
        if code != 0:
            say("      " + out.replace("\n", "\n      "))
            say(
                "Stopped. Files already changed have backups (.bak_*); run with --revert. The database is intact."
            )
            return 1
    ok_import, out = import_check(backend)
    if (
        not ok_import
        and "ModuleNotFoundError" in out
        and "No module named 'app" not in out
    ):
        say(
            "  [..] import check skipped: this Python does not have the server's libraries (%s)"
            % out.strip().splitlines()[-1]
        )
        ok_import = True
    elif ok_import:
        say("  [ok] the patched server code imports cleanly")
    if not ok_import:
        say("  [!!] the patched server code does not import:")
        say("      " + out[-1500:].replace("\n", "\n      "))
        for _t, patch, folder in (
            ("web pages", FRONTEND_PATCH, web),
            ("server code", BACKEND_PATCH, app),
        ):
            run_patch(patch, folder, "--revert")
        say(
            "  The code was put back automatically. The database is intact. Send me this screen."
        )
        return 1

    if db is not None:
        conn = sqlite3.connect(str(db))
        try:
            has_logs = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='visitor_logs'"
            ).fetchone()
            if has_logs:
                for sql in INDEXES:
                    conn.execute(sql)
                say("  [ok] indexes on visitor_logs in place")
            conn.execute("ANALYZE")
            say("  [ok] statistics refreshed (ANALYZE)")
            if want_wal:
                mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                say(
                    "  [%s] journal mode: %s"
                    % ("ok" if mode.lower() == "wal" else "!!", mode)
                )
            conn.commit()
            after = table_counts(conn)
            ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        diff = [t for t in before if after.get(t) != before[t]]
        if diff or ok != "ok":
            say(
                "  [!!] VERIFICATION FAILED: integrity=%s, changed tables: %s"
                % (ok, ", ".join(diff) or "-")
            )
            say("       Restore the .before_update_ backup and send me this screen.")
            return 1
        say(
            "  [ok] verified: every table has the same number of rows as before (visitors %d, log rows %d), integrity ok"
            % (after.get("visitors", 0), after.get("visitor_logs", 0))
        )

    say("")
    say("-" * 70)
    say(
        "DONE. Start the server (run_server.bat). The first start adds the new tables and"
    )
    say("permissions by itself. Then, as admin: Settings > 'Optional features'.")
    say("To undo the code changes: UNDO.bat. Your data is never modified or deleted.")
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
