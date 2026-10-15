#!/usr/bin/env python3
"""Kav1 fix 2/3 - add the missing indexes on visitor_logs, then ANALYZE.

Why: visitor_logs has no index on visitor_dbid or timestamp, so
  * GET /visitors/inside (one 'latest log' query per inside visitor),
  * GET /logs (ORDER BY timestamp DESC LIMIT n),
  * GET /logs/<visitor> and visitor deletes (ORM cascade)
all scan the whole table. The composite index (visitor_dbid, timestamp) turns
the per-visitor 'latest log' query into a single b-tree seek.

Safety:
  * Backs up the DB first (verified), only if an index is actually missing.
  * Only ADDS indexes (CREATE INDEX IF NOT EXISTS) + ANALYZE statistics.
    No rows are changed or deleted; no existing index is dropped.
  * Idempotent: an index that already exists (under any name, same leading
    columns) is skipped.
  * Safe to run while the server is up (takes a short write lock), but
    stopping it first is cleaner.

Usage:  python tools/fix_02_add_indexes.py [--db PATH]
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


WANTED = [
    # (index name, table, columns)
    (
        "ix_visitor_logs_visitor_dbid_timestamp",
        "visitor_logs",
        ["visitor_dbid", "timestamp"],
    ),
    ("ix_visitor_logs_timestamp", "visitor_logs", ["timestamp"]),
]
BENCH = (
    "SELECT * FROM visitor_logs WHERE visitor_dbid = ? "
    "ORDER BY timestamp DESC LIMIT 1"
)


def existing_index_cols(con, table):
    res = []
    for row in con.execute("PRAGMA index_list('%s')" % table):
        res.append([c[2] for c in con.execute("PRAGMA index_info('%s')" % row[1])])
    return res


def bench_inside(con):
    ids = [r[0] for r in con.execute("SELECT dbid FROM visitors WHERE inside")]
    t0 = time.perf_counter()
    for v in ids:
        con.execute(BENCH, (v,)).fetchall()
    return len(ids), (time.perf_counter() - t0) * 1000.0


def main():
    ap = argparse.ArgumentParser(description="Add missing indexes + ANALYZE.")
    ap.add_argument("--db", help="path to local_database.db")
    args = ap.parse_args()
    db = find_db(args.db)
    print("Database: %s" % db)

    con = connect(db, readonly=True)
    try:
        tables = user_tables(con)
        if "visitor_logs" not in tables:
            sys.exit("ERROR: table visitor_logs not found - is this a Kav1 database?")
        before = row_counts(con)
        todo = []
        for name, table, cols in WANTED:
            have = existing_index_cols(con, table)
            if any(ix[: len(cols)] == cols for ix in have):
                print("skip  %s (an equivalent index already exists)" % name)
            else:
                todo.append((name, table, cols))
        has_stat = bool(
            con.execute(
                "SELECT 1 FROM sqlite_master WHERE name='sqlite_stat1'"
            ).fetchone()
        )
        n_in, t_before = bench_inside(con)
    finally:
        con.close()

    if not todo and has_stat:
        print(
            "All indexes present and statistics exist - nothing to do "
            "(no backup needed, nothing changed)."
        )
        return

    backup = make_backup(db, "pre-indexes")
    print("OK  verified backup: %s" % backup)

    con = sqlite3.connect(str(db), timeout=30)
    try:
        for name, table, cols in todo:
            t0 = time.perf_counter()
            con.execute(
                'CREATE INDEX IF NOT EXISTS "%s" ON "%s" (%s)'
                % (name, table, ", ".join('"%s"' % c for c in cols))
            )
            con.commit()
            print(
                "OK  created %s on %s%s in %.0f ms"
                % (name, table, cols, (time.perf_counter() - t0) * 1000)
            )
        con.execute("ANALYZE")
        con.commit()
        print("OK  ANALYZE done")
    except sqlite3.OperationalError as e:
        sys.exit(
            "ERROR: %s\nNothing destructive happened; backup kept at %s" % (e, backup)
        )
    finally:
        con.close()

    verify_same_data(db, before)
    con = connect(db, readonly=True)
    try:
        _, t_after = bench_inside(con)
        plan = [r[3] for r in con.execute("EXPLAIN QUERY PLAN " + BENCH, (1,))]
    finally:
        con.close()
    print("Query plan for 'latest log per visitor': %s" % "; ".join(plan))
    print(
        "Simulated GET /visitors/inside DB time (%d inside visitors): "
        "%.0f ms -> %.0f ms" % (n_in, t_before, t_after)
    )


if __name__ == "__main__":
    main()
