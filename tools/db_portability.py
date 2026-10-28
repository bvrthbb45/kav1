#!/usr/bin/env python3
"""Kav1 - move the database between folders / machines safely (standalone, stdlib only, Python 3.8+).

  python db_portability.py check  <local_database.db>
  python db_portability.py export <local_database.db> [--out FOLDER]
  python db_portability.py import <portable folder or .db file> --target <local_database.db> [--force]

Run without arguments for a small menu (drag files into the window).

What it guarantees
  * export: makes a consistent copy with SQLite's online-backup API (correct even while the server runs and
    even for a WAL-mode database), writes manifest.json (row counts, SHA-256) and verifies the copy.
  * import: stops if the server still holds the target; backs up the existing target first; REFUSES to
    replace a target that holds visitors the incoming file does not have (that would delete visitors) unless
    --force; writes through a temporary file and swaps it in at the end; removes stale -wal/-shm side files;
    afterwards re-counts every table and compares with the manifest.
  * the source file is never modified or deleted. Nothing is printed about people: only counts.
"""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

TOOL_VERSION = "1.0"
CORE_TABLES = ("visitors", "visitor_logs")
MANIFEST = "manifest.json"
DB_NAME = "local_database.db"


def say(text=""):
    print(text, flush=True)


def clean(text):
    t = text.strip()
    if t.startswith("& "):
        t = t[2:].strip()
    return t.strip('"').strip("'")


def connect_ro(path):
    return sqlite3.connect(
        "file:%s?mode=ro" % Path(path).resolve().as_posix(), uri=True
    )


def tables_of(conn):
    return [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def counts_of(conn):
    return {
        t: conn.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
        for t in tables_of(conn)
    }


def visitor_ids(conn):
    return {r[0] for r in conn.execute("SELECT visitorid FROM visitors")}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def integrity(conn):
    return conn.execute("PRAGMA integrity_check").fetchone()[0]


def is_kav1(conn):
    return set(CORE_TABLES).issubset(tables_of(conn))


def locked(path):
    """True when another process holds the database (the server is running)."""
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


def online_copy(src, dst):
    a = connect_ro(src)
    b = sqlite3.connect(str(dst))
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()


# ---------------------------------------------------------------- check
def cmd_check(db):
    p = Path(clean(db)).expanduser()
    if not p.is_file():
        sys.exit("File not found: %s" % p)
    conn = connect_ro(p)
    try:
        say("Database : %s  (%d KB)" % (p, p.stat().st_size // 1024))
        say(
            "Kav1 DB  : %s"
            % (
                "yes"
                if is_kav1(conn)
                else "NO - visitors/visitor_logs tables are missing"
            )
        )
        say("Integrity: %s" % integrity(conn))
        say("Journal  : %s" % conn.execute("PRAGMA journal_mode").fetchone()[0])
        for t, n in counts_of(conn).items():
            say("  %-22s %8d rows" % (t, n))
    finally:
        conn.close()
    wal = Path(str(p) + "-wal")
    if wal.is_file() and wal.stat().st_size > 0:
        say("")
        say("WARNING: a non-empty %s exists next to the database." % wal.name)
        say(
            "  Recent changes may still be in it. Copying ONLY the .db file would lose them."
        )
        say("  Stop the server cleanly first, or use 'export' (it is always complete).")
    return 0


# ---------------------------------------------------------------- export
def cmd_export(db, out):
    src = Path(clean(db)).expanduser().resolve()
    if not src.is_file():
        sys.exit("File not found: %s" % src)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = (
        Path(clean(out)).expanduser().resolve()
        if out
        else src.parent / ("kav1_portable_" + stamp)
    )
    folder.mkdir(parents=True, exist_ok=False)
    dst = folder / DB_NAME
    say("Copying with the online-backup API ...")
    online_copy(src, dst)
    conn = connect_ro(dst)
    try:
        if not is_kav1(conn):
            sys.exit(
                "This is not a Kav1 database (visitors / visitor_logs missing). Nothing exported."
            )
        ok = integrity(conn)
        counts = counts_of(conn)
    finally:
        conn.close()
    if ok != "ok":
        sys.exit(
            "The copy failed its integrity check (%s). The source was not changed." % ok
        )
    src_conn = connect_ro(src)
    try:
        src_counts = counts_of(src_conn)
    finally:
        src_conn.close()
    if src_counts != counts:
        say(
            "NOTE: the source changed while it was copied (the server is running); the copy is a consistent snapshot."
        )
    manifest = {
        "tool": "db_portability %s" % TOOL_VERSION,
        "created": datetime.now().isoformat(timespec="seconds"),
        "source_name": src.name,
        "sha256": sha256(dst),
        "size": dst.stat().st_size,
        "counts": counts,
    }
    (folder / MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    say("")
    say("Exported to: %s" % folder)
    for t in CORE_TABLES:
        say("  %-14s %8d rows" % (t, counts[t]))
    say("  integrity: ok    sha256: %s..." % manifest["sha256"][:16])
    say(
        "Move the whole folder. On the other side run:  import <that folder> --target <local_database.db>"
    )
    return 0


# ---------------------------------------------------------------- import
def cmd_import(source, target, force):
    s = Path(clean(source)).expanduser().resolve()
    manifest = None
    if s.is_dir():
        mf = s / MANIFEST
        if mf.is_file():
            manifest = json.loads(mf.read_text(encoding="utf-8"))
        s = s / DB_NAME
    elif (s.parent / MANIFEST).is_file():
        manifest = json.loads((s.parent / MANIFEST).read_text(encoding="utf-8"))
    if not s.is_file():
        sys.exit("Source database not found: %s" % s)
    t = Path(clean(target)).expanduser().resolve()

    say("1/6 Checking the incoming file ...")
    if manifest and sha256(s) != manifest["sha256"]:
        sys.exit(
            "The file does not match its manifest (damaged during the move?). Nothing was changed."
        )
    conn = connect_ro(s)
    try:
        if not is_kav1(conn):
            sys.exit("The incoming file is not a Kav1 database. Nothing was changed.")
        if integrity(conn) != "ok":
            sys.exit(
                "The incoming file failed its integrity check. Nothing was changed."
            )
        incoming = counts_of(conn)
        incoming_ids = visitor_ids(conn)
    finally:
        conn.close()
    say(
        "    incoming: %d visitors, %d log rows"
        % (incoming["visitors"], incoming["visitor_logs"])
    )

    if t.is_file():
        say("2/6 Checking the target ...")
        if locked(t):
            sys.exit(
                "The target database is in use. Stop the Kav1 server first. Nothing was changed."
            )
        tc = connect_ro(t)
        try:
            existing = counts_of(tc) if is_kav1(tc) else {}
            target_ids = visitor_ids(tc) if is_kav1(tc) else set()
        finally:
            tc.close()
        only_target = target_ids - incoming_ids
        say(
            "    target  : %d visitors, %d log rows"
            % (existing.get("visitors", 0), existing.get("visitor_logs", 0))
        )
        if only_target and not force:
            say("")
            say(
                "STOPPED to protect your data: the target holds %d visitor(s) that the incoming file does not have."
                % len(only_target)
            )
            say("Importing would delete them. Nothing was changed. Options:")
            say("  - export the target first and keep both files,")
            say(
                "  - or repeat with --force if you are sure the incoming file is the one to keep"
            )
            say("    (the target is backed up first either way).")
            return 2
        say("3/6 Backing up the target ...")
        bak = t.with_name(
            t.name
            + ".before_import_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + ".bak"
        )
        online_copy(t, bak)
        say("    backup: %s" % bak.name)
    else:
        say("2/6 Target does not exist yet - it will be created.")
        say("3/6 (no backup needed)")

    say("4/6 Writing through a temporary file ...")
    t.parent.mkdir(parents=True, exist_ok=True)
    tmp = t.with_name(t.name + ".importing")
    if tmp.exists():
        tmp.unlink()
    online_copy(s, tmp)
    say("5/6 Swapping it in ...")
    for suffix in (
        "-wal",
        "-shm",
    ):  # side files of the OLD database must never be replayed onto the new one
        side = Path(str(t) + suffix)
        if side.exists():
            side.unlink()
    os.replace(str(tmp), str(t))

    say("6/6 Verifying ...")
    vc = connect_ro(t)
    try:
        after = counts_of(vc)
        ok = integrity(vc)
    finally:
        vc.close()
    expected = (manifest or {}).get("counts") or incoming
    bad = [k for k, v in expected.items() if after.get(k) != v]
    say("")
    if ok != "ok" or bad:
        say(
            "PROBLEM: integrity=%s, tables with different row counts: %s"
            % (ok, ", ".join(bad) or "-")
        )
        say("The previous target is in the .before_import_*.bak file next to it.")
        return 1
    say(
        "DONE. %d visitors, %d log rows, integrity ok, every table count matches."
        % (after["visitors"], after["visitor_logs"])
    )
    say(
        "Start the server: it adds anything new (tables, permissions) by itself and never deletes visitors."
    )
    return 0


# ---------------------------------------------------------------- menu
def menu():
    say("Kav1 database portability v%s" % TOOL_VERSION)
    say("  1) check    - read-only report of a database file")
    say("  2) export   - make a portable folder (consistent copy + manifest)")
    say(
        "  3) import   - put a portable folder / .db file in place (with backup and safety checks)"
    )
    choice = input("Choose 1-3: ").strip()
    say("Drag the database file (or folder) into this window, then Enter.")
    if choice == "1":
        return cmd_check(input("> "))
    if choice == "2":
        return cmd_export(input("> "), None)
    if choice == "3":
        src = input("Incoming folder or .db > ")
        say("Now drag the TARGET local_database.db (where it should end up) here:")
        return cmd_import(src, input("> "), False)
    sys.exit("Nothing chosen.")


def main():
    ap = argparse.ArgumentParser(description="Move the Kav1 database safely.")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check")
    c.add_argument("db")
    e = sub.add_parser("export")
    e.add_argument("db")
    e.add_argument("--out")
    i = sub.add_parser("import")
    i.add_argument("source")
    i.add_argument("--target", required=True)
    i.add_argument("--force", action="store_true")
    no_pause = "--no-pause" in sys.argv
    args = ap.parse_args([a for a in sys.argv[1:] if a != "--no-pause"])
    code = 1
    try:
        if args.cmd == "check":
            code = cmd_check(args.db)
        elif args.cmd == "export":
            code = cmd_export(args.db, args.out)
        elif args.cmd == "import":
            code = cmd_import(args.source, args.target, args.force)
        else:
            code = menu()
    except SystemExit as exc:
        if exc.code not in (0, None):
            say(str(exc.code))
        code = 1
    except Exception as exc:  # noqa
        import traceback

        say("UNEXPECTED ERROR - photograph this screen:")
        say(traceback.format_exc())
        code = 1
    if sys.stdin.isatty() and not no_pause:
        input("\nPress Enter to close ...")
    sys.exit(code)


if __name__ == "__main__":
    main()
