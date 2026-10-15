#!/usr/bin/env python3
"""Kav1 fix 3/3 - checkpoint the WAL, VACUUM (defragment), ANALYZE.

Why: after many deletes/updates the file contains free pages and rows are
scattered; VACUUM rewrites the database compactly and in order, and ANALYZE
refreshes the planner statistics. In WAL mode it also truncates a large -wal
file.

Safety:
  * Backs up the DB first (verified), only if there is something to reclaim
    (free pages >= 5%, or --force).
  * VACUUM rebuilds the file but preserves every row; integrity and row counts
    are verified afterwards and the script exits non-zero otherwise.
  * Idempotent: a compact database is left alone (use --force to run anyway).
  * VACUUM needs exclusive access: STOP THE KAV1 SERVER FIRST. If it is still
    running the script reports it and changes nothing.

Usage:  python tools/fix_03_vacuum_analyze.py [--db PATH] [--force]
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
    ap = argparse.ArgumentParser(description="VACUUM + ANALYZE.")
    ap.add_argument("--db", help="path to local_database.db")
    ap.add_argument("--force", action="store_true", help="run even if not fragmented")
    args = ap.parse_args()
    db = find_db(args.db)
    print("Database: %s" % db)

    con = connect(db, readonly=True)
    try:
        page_count = pragma(con, "page_count")
        freelist = pragma(con, "freelist_count")
        mode = str(pragma(con, "journal_mode")).lower()
        before = row_counts(con)
        has_stat = bool(
            con.execute(
                "SELECT 1 FROM sqlite_master WHERE name='sqlite_stat1'"
            ).fetchone()
        )
    finally:
        con.close()
    pct = 100.0 * freelist / page_count if page_count else 0.0
    size_before = db.stat().st_size
    print(
        "size %s, free pages %d of %d (%.1f%%), journal_mode=%s"
        % (fmt_mb(size_before), freelist, page_count, pct, mode)
    )

    if pct < 5.0 and has_stat and not args.force:
        print(
            "Not fragmented and statistics exist - nothing to do "
            "(no backup needed, nothing changed). Use --force to run anyway."
        )
        return

    backup = make_backup(db, "pre-vacuum")
    print("OK  verified backup: %s" % backup)

    con = sqlite3.connect(str(db), timeout=10, isolation_level=None)
    try:
        if mode == "wal":
            r = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if r[0] != 0:
                sys.exit(
                    "ERROR: the database is in use (checkpoint busy). Stop the "
                    "Kav1 server and run again. Nothing was changed."
                )
            print("OK  WAL checkpointed and truncated")
        if pct >= 5.0 or args.force:
            t0 = time.perf_counter()
            con.execute("VACUUM")
            print("OK  VACUUM in %.1f s" % (time.perf_counter() - t0))
        con.execute("ANALYZE")
        con.execute("PRAGMA optimize")
        print("OK  ANALYZE + optimize done")
    except sqlite3.OperationalError as e:
        sys.exit(
            "ERROR: %s\nStop the Kav1 server and run again. Nothing was lost; "
            "backup kept at %s" % (e, backup)
        )
    finally:
        con.close()

    verify_same_data(db, before)
    print("Size: %s -> %s" % (fmt_mb(size_before), fmt_mb(db.stat().st_size)))


if __name__ == "__main__":
    main()
