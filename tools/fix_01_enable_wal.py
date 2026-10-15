#!/usr/bin/env python3
"""Kav1 fix 1/3 - switch the database to WAL journal mode.

Why: in the default rollback-journal mode every commit rewrites a journal and
fsyncs twice, and a writer blocks every reader. WAL makes commits much cheaper
and lets readers and the writer work at the same time. WAL is persistent: it is
stored in the database file, so this only has to be done ONCE.

Safety:
  * Backs up the DB first (verified), only if a change is actually needed.
  * Changes only the journal mode. No rows are touched or deleted.
  * Idempotent: if the DB is already in WAL mode it does nothing.
  * Verifies integrity and row counts afterwards.

IMPORTANT: stop the Kav1 server first (switching needs exclusive access). If it
is still running the script says so and leaves everything unchanged.
WAL needs a local disk (not a network share).

Usage:  python tools/fix_01_enable_wal.py [--db PATH]
"""

import argparse
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

DB_NAME = "local_database.db"


# --- shared helpers (duplicated in every tools/*.py on purpose: standalone) ---
def candidate_paths(script_dir):
    cwd = Path.cwd()
    cands = [
        script_dir.parent / "backend" / DB_NAME,
        script_dir.parent / DB_NAME,
        script_dir / DB_NAME,
        cwd / DB_NAME,
        cwd / "backend" / DB_NAME,
    ]
    for var in ("APPDATA", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base:
            cands.append(Path(base) / "Kav1" / "server" / DB_NAME)
    return cands


def find_db(arg):
    if arg:
        p = Path(arg).expanduser()
        if not p.is_file():
            sys.exit("ERROR: --db file not found: %s" % p)
        return p.resolve()
    env = os.environ.get("KAV1_DB")
    if env:
        p = Path(env).expanduser()
        if not p.is_file():
            sys.exit("ERROR: KAV1_DB points to a missing file: %s" % p)
        return p.resolve()
    script_dir = Path(__file__).resolve().parent
    found, seen = [], set()
    for c in candidate_paths(script_dir):
        try:
            r = c.resolve()
        except OSError:
            continue
        if r not in seen and r.is_file():
            seen.add(r)
            found.append(r)
    if not found:
        sys.exit(
            "ERROR: %s not found. Pass --db <path> or set KAV1_DB.\nSearched:\n  %s"
            % (DB_NAME, "\n  ".join(str(c) for c in candidate_paths(script_dir)))
        )
    if len(found) > 1:
        lines = [
            "  %s  (%.1f MB, modified %s)"
            % (
                f,
                f.stat().st_size / 1e6,
                datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            )
            for f in found
        ]
        sys.exit(
            "ERROR: more than one database found - refusing to guess.\n%s\n"
            "Re-run with --db <path>." % "\n".join(lines)
        )
    return found[0]


def connect(db, readonly=True, timeout=30):
    uri = db.as_uri() + ("?mode=ro" if readonly else "")
    return sqlite3.connect(uri, uri=True, timeout=timeout)


def user_tables(con):
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def row_counts(con):
    return {
        t: con.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
        for t in user_tables(con)
    }


def make_backup(db, label):
    """Online backup next to the DB + verification. Returns backup path."""
    bdir = db.parent / "backups"
    bdir.mkdir(exist_ok=True)
    free = shutil.disk_usage(str(bdir)).free
    if free < db.stat().st_size * 3:
        sys.exit("ERROR: not enough free disk space for a safe backup.")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = bdir / ("%s.%s.%s.db" % (db.stem, label, ts))
    src = connect(db, readonly=True)
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
        dst.commit()
        counts_src = row_counts(src)
    finally:
        dst.close()
        src.close()
    chk = sqlite3.connect(str(dest))
    try:
        ok = chk.execute("PRAGMA integrity_check").fetchone()[0]
        counts_dst = row_counts(chk)
    finally:
        chk.close()
    if ok != "ok" or counts_src != counts_dst:
        sys.exit("ERROR: backup verification failed (%s) - aborting." % dest)
    return dest


def pragma(con, name):
    r = con.execute("PRAGMA %s" % name).fetchone()
    return r[0] if r else None


def fmt_mb(n):
    return "%.2f MB" % (n / 1e6)


def verify_same_data(db, before_counts):
    """Row counts unchanged + integrity ok, else exit non-zero (backup is kept)."""
    con = connect(db, readonly=True)
    try:
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        after = row_counts(con)
    finally:
        con.close()
    if ok != "ok" or after != before_counts:
        sys.exit(
            "ERROR: post-check failed (integrity=%s, counts before=%s after=%s).\n"
            "Restore the backup shown above." % (ok, before_counts, after)
        )
    print("OK  integrity_check=ok, row counts unchanged: %s" % after)


def main():
    ap = argparse.ArgumentParser(description="Enable WAL journal mode.")
    ap.add_argument("--db", help="path to local_database.db")
    args = ap.parse_args()
    db = find_db(args.db)
    print("Database: %s" % db)
    if str(db).startswith("\\\\"):
        sys.exit("ERROR: WAL does not work on network shares. Use a local disk.")

    con = connect(db, readonly=True)
    try:
        mode = str(pragma(con, "journal_mode")).lower()
        before = row_counts(con)
    finally:
        con.close()
    if mode == "wal":
        print(
            "Already in WAL mode - nothing to do (no backup needed, nothing changed)."
        )
        return

    backup = make_backup(db, "pre-wal")
    print("OK  verified backup: %s" % backup)

    con = sqlite3.connect(str(db), timeout=10)
    try:
        new = str(con.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
    except sqlite3.OperationalError as e:
        sys.exit(
            "ERROR: %s\nStop the Kav1 server and run this again. Nothing was changed."
            % e
        )
    finally:
        con.close()
    if new != "wal":
        sys.exit(
            "ERROR: could not switch (journal_mode is still '%s'). Another process "
            "has the DB open - stop the Kav1 server and run again. Nothing was "
            "changed; backup kept at %s" % (new, backup)
        )
    print("OK  journal_mode: %s -> wal" % mode)
    verify_same_data(db, before)
    print("Done. Note: you will now see local_database.db-wal / -shm next to the DB;")
    print("that is normal. Never copy only the .db file while the server runs - use")
    print("the backups this tool makes (they are taken with SQLite's backup API).")


if __name__ == "__main__":
    main()
