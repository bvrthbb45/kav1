#!/usr/bin/env python3
"""Kav1 - database diagnostics (standalone, stdlib only, Python 3.8+).

What it does, in order:
  1. Locates the SQLite DB (see --db / KAV1_DB / auto-discovery below).
  2. BACKS IT UP FIRST (sqlite3 online-backup API) and verifies the backup.
  3. Inspects the DB strictly READ-ONLY: size, row counts, indexes, journal
     mode, fragmentation, integrity, orphans.
  4. Times the exact query patterns the Kav1 backend runs (backend/app/crud.py
     and routes.py) and shows their query plans.
  5. Measures commit latency on a throw-away COPY (never on the real DB).
  6. Prints findings with the fix script that addresses each one, and saves the
     whole report to <db dir>/diagnostics/.

It never modifies the real database. Safe to run repeatedly (idempotent) and
safe to run while the server is up.

Usage:
  python tools/diagnose_db.py                 # auto-discover the DB
  python tools/diagnose_db.py --db C:\\path\\local_database.db
  python tools/diagnose_db.py --no-write-test # skip the commit-latency test
"""

import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

DB_NAME = "local_database.db"
SLOW_MS = 100.0  # a single query slower than this is flagged
REPORT = []


# --------------------------------------------------------------------------
# helpers (duplicated in every tools/*.py on purpose: each script is standalone)
# --------------------------------------------------------------------------
def out(line=""):
    print(line)
    REPORT.append(line)


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


def timed(con, sql, params=(), fetch=True):
    t0 = time.perf_counter()
    cur = con.execute(sql, params)
    rows = cur.fetchall() if fetch else None
    return (time.perf_counter() - t0) * 1000.0, rows


def plan(con, sql, params=()):
    return [r[3] for r in con.execute("EXPLAIN QUERY PLAN " + sql, params)]


# --------------------------------------------------------------------------
# diagnostics
# --------------------------------------------------------------------------
def section(title):
    out()
    out("=" * 72)
    out(title)
    out("=" * 72)


def main():
    ap = argparse.ArgumentParser(description="Kav1 DB diagnostics (read-only).")
    ap.add_argument("--db", help="path to local_database.db")
    ap.add_argument(
        "--no-write-test", action="store_true", help="skip the commit-latency test"
    )
    args = ap.parse_args()

    db = find_db(args.db)
    findings = []  # (severity, text, fix)

    out("Kav1 database diagnostics - %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    out("Python %s | SQLite %s" % (sys.version.split()[0], sqlite3.sqlite_version))
    out("Database: %s" % db)

    section("1. Backup (taken before anything else)")
    backup = make_backup(db, "pre-diagnose")
    out("OK  verified backup: %s" % backup)

    con = connect(db, readonly=True)
    try:
        tables = user_tables(con)

        section("2. Files and pragmas")
        wal = Path(str(db) + "-wal")
        shm = Path(str(db) + "-shm")
        size = db.stat().st_size
        out("DB file         : %s" % fmt_mb(size))
        out(
            "-wal file       : %s"
            % (fmt_mb(wal.stat().st_size) if wal.exists() else "none")
        )
        out("-shm file       : %s" % ("present" if shm.exists() else "none"))
        page_size = pragma(con, "page_size")
        page_count = pragma(con, "page_count")
        freelist = pragma(con, "freelist_count")
        jm = pragma(con, "journal_mode")
        out(
            "page_size       : %s | page_count: %s | freelist_count: %s"
            % (page_size, page_count, freelist)
        )
        out("journal_mode    : %s" % jm)
        out(
            "synchronous     : %s (persisted default is per-connection; app uses SQLite default FULL=2)"
            % pragma(con, "synchronous")
        )
        out("auto_vacuum     : %s (0=none)" % pragma(con, "auto_vacuum"))
        out(
            "foreign_keys    : %s (per-connection; SQLite default OFF -> ON DELETE CASCADE not enforced by the engine)"
            % pragma(con, "foreign_keys")
        )
        out("user_version    : %s" % pragma(con, "user_version"))
        free_pct = 100.0 * freelist / page_count if page_count else 0
        out(
            "fragmentation   : %.1f%% of pages are free (reclaimable by VACUUM)"
            % free_pct
        )

        if str(jm).lower() != "wal":
            findings.append(
                (
                    "HIGH",
                    "journal_mode is '%s', not WAL. Every commit rewrites a rollback "
                    "journal and fsyncs twice, and a writer blocks all readers (and "
                    "vice-versa) -> requests queue up / 'database is locked'." % jm,
                    "tools/fix_01_enable_wal.py",
                )
            )
        if free_pct >= 5:
            findings.append(
                (
                    "LOW",
                    "%.1f%% of the file is free pages (fragmentation)." % free_pct,
                    "tools/fix_03_vacuum_analyze.py",
                )
            )
        if wal.exists() and wal.stat().st_size > 50 * 1024 * 1024:
            findings.append(
                (
                    "MEDIUM",
                    "-wal file is %s: checkpoints are not keeping up."
                    % fmt_mb(wal.stat().st_size),
                    "tools/fix_03_vacuum_analyze.py (checkpoints with TRUNCATE)",
                )
            )

        section("3. Integrity")
        qc = pragma(con, "quick_check")
        out("quick_check     : %s" % qc)
        if qc != "ok":
            findings.append(
                (
                    "CRITICAL",
                    "quick_check reports corruption: %s" % qc,
                    "restore from backup; do NOT run fixes",
                )
            )
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        out("foreign_key_check: %d violation(s)" % len(fk))
        if fk:
            findings.append(
                (
                    "MEDIUM",
                    "%d rows violate foreign keys (orphan logs)." % len(fk),
                    "review manually; fixes never delete data",
                )
            )

        section("4. Tables, row counts, size")
        counts = row_counts(con)
        for t in tables:
            out("%-20s %10d rows" % (t, counts[t]))
        try:
            rows = con.execute(
                "SELECT name, SUM(pgsize) FROM dbstat GROUP BY name ORDER BY 2 DESC"
            ).fetchall()
            out()
            out("Space by object (dbstat):")
            for name, nbytes in rows[:12]:
                out("  %-40s %s" % (name, fmt_mb(nbytes)))
        except sqlite3.Error:
            out(
                "(dbstat not available in this SQLite build - skipping per-object sizes)"
            )

        if "visitors" in tables:
            n, inside, avgp, maxp = con.execute(
                "SELECT COUNT(*), SUM(inside), AVG(LENGTH(properties)), "
                "MAX(LENGTH(properties)) FROM visitors"
            ).fetchone()
            out()
            out("visitors: %d total, %d currently inside" % (n, inside or 0))
            out("properties JSON size: avg %.0f B, max %s B" % (avgp or 0, maxp))
        if "visitor_logs" in tables:
            n, lo, hi, nv = con.execute(
                "SELECT COUNT(*), MIN(timestamp), MAX(timestamp), "
                "COUNT(DISTINCT visitor_dbid) FROM visitor_logs"
            ).fetchone()
            out("visitor_logs: %d rows for %d visitors, %s .. %s" % (n, nv, lo, hi))
            out("  avg %.1f log rows per visitor" % (n / nv if nv else 0))

        section("5. Indexes")
        idx_cols = {}
        for t in tables:
            for row in con.execute("PRAGMA index_list('%s')" % t):
                iname, uniq = row[1], row[2]
                cols = [c[2] for c in con.execute("PRAGMA index_info('%s')" % iname)]
                idx_cols.setdefault(t, []).append(cols)
                out("%-14s %-42s %s%s" % (t, iname, cols, " UNIQUE" if uniq else ""))
        has_stat = bool(
            con.execute(
                "SELECT 1 FROM sqlite_master WHERE name='sqlite_stat1'"
            ).fetchone()
        )
        out(
            "sqlite_stat1 (ANALYZE statistics): %s"
            % ("present" if has_stat else "MISSING")
        )

        def covered(table, cols):
            """True if some index on `table` starts with `cols` (or PK rowid)."""
            return any(ix[: len(cols)] == cols for ix in idx_cols.get(table, []))

        if "visitor_logs" in tables:
            if not covered("visitor_logs", ["visitor_dbid"]):
                findings.append(
                    (
                        "CRITICAL",
                        "visitor_logs has NO index on visitor_dbid. Every "
                        "'latest log for visitor X' (called once PER INSIDE VISITOR by "
                        "GET /visitors/inside), every visitor-log lookup and every "
                        "visitor delete (ORM cascade) full-scans visitor_logs.",
                        "tools/fix_02_add_indexes.py",
                    )
                )
            if not covered("visitor_logs", ["timestamp"]):
                findings.append(
                    (
                        "HIGH",
                        "visitor_logs has NO index on timestamp. GET /logs does "
                        "ORDER BY timestamp DESC LIMIT n -> full scan + temp sort of "
                        "the whole table on every call.",
                        "tools/fix_02_add_indexes.py",
                    )
                )
        if not has_stat:
            findings.append(
                (
                    "LOW",
                    "No ANALYZE statistics: planner works blind.",
                    "tools/fix_02_add_indexes.py or fix_03",
                )
            )

        section("6. Query timings (the exact patterns used by the backend)")
        out("Each query is run 3x, best time shown. Flag threshold: %.0f ms." % SLOW_MS)
        out()

        def bench(label, sql, params=(), note=""):
            best, rows = None, None
            for _ in range(3):
                ms, rows = timed(con, sql, params)
                best = ms if best is None else min(best, ms)
            flag = "  <-- SLOW" if best > SLOW_MS else ""
            out("%-44s %9.2f ms  rows=%-6d%s" % (label, best, len(rows), flag))
            for p in plan(con, sql, params):
                bad = "SCAN visitor_logs" in p or "TEMP B-TREE" in p
                out("      plan: %s%s" % (p, "   (!)" if bad else ""))
            if note:
                out("      " + note)
            return best

        if "visitors" in tables:
            bench("GET /visitors (all rows)", "SELECT * FROM visitors")
            bench(
                "lookup by visitorid",
                "SELECT * FROM visitors WHERE visitorid = ?",
                ("__none__",),
            )
            bench(
                "search by name (ilike %q%)",
                "SELECT * FROM visitors WHERE lower(name) LIKE lower(?)",
                ("%a%",),
                "leading wildcard can never use an index; fine at this table size",
            )
            bench(
                "search by JSON property",
                "SELECT * FROM visitors WHERE json_extract(properties, '$.x') IS NOT NULL",
            )
        if "visitor_logs" in tables:
            bench(
                "GET /logs?limit=50",
                "SELECT * FROM visitor_logs ORDER BY timestamp DESC LIMIT 50",
            )
            bench(
                "GET /logs?limit=1000",
                "SELECT * FROM visitor_logs ORDER BY timestamp DESC LIMIT 1000",
            )
            one = con.execute(
                "SELECT visitor_dbid FROM visitor_logs "
                "GROUP BY visitor_dbid ORDER BY COUNT(*) DESC LIMIT 1"
            ).fetchone()
            vid = one[0] if one else -1
            bench(
                "latest log for ONE visitor",
                "SELECT * FROM visitor_logs WHERE visitor_dbid = ? "
                "ORDER BY timestamp DESC LIMIT 1",
                (vid,),
            )

        if "visitors" in tables and "visitor_logs" in tables:
            ids = [r[0] for r in con.execute("SELECT dbid FROM visitors WHERE inside")]
            out()
            out(
                "Simulating GET /visitors/inside: %d inside visitors -> 1 + %d queries (N+1)"
                % (len(ids), len(ids))
            )
            t0 = time.perf_counter()
            done = 0
            for vid in ids:
                con.execute(
                    "SELECT * FROM visitor_logs WHERE visitor_dbid = ? "
                    "ORDER BY timestamp DESC LIMIT 1",
                    (vid,),
                ).fetchall()
                done += 1
                if time.perf_counter() - t0 > 60:
                    break
            total = (time.perf_counter() - t0) * 1000.0
            if done < len(ids):
                total = total / done * len(ids)
                out("  (stopped after 60 s; extrapolated)")
            out(
                "  whole endpoint (DB time only): %.0f ms%s"
                % (total, "  <-- SLOW" if total > 500 else "")
            )
            if total > 500:
                findings.append(
                    (
                        "CRITICAL",
                        "GET /visitors/inside costs ~%.0f ms of pure DB time per call "
                        "(%d inside visitors x N+1 queries). Every ENTRY/EXIT/edit "
                        "broadcasts 'sync' and EVERY connected client re-issues this "
                        "call, so one click = (#clients x this cost)."
                        % (total, len(ids)),
                        "tools/fix_02_add_indexes.py (+ code fix: single JOIN query)",
                    )
                )
            elif total > 100:
                findings.append(
                    (
                        "MEDIUM",
                        "GET /visitors/inside costs ~%.0f ms per call and multiplies by "
                        "the number of clients on every 'sync'." % total,
                        "tools/fix_02_add_indexes.py",
                    )
                )
    finally:
        con.close()

    if not args.no_write_test:
        section("7. Commit latency (on a temporary COPY - real DB untouched)")
        tmpd = tempfile.mkdtemp(prefix="kav1diag_", dir=str(db.parent))
        try:
            for mode in ("DELETE", "WAL"):
                cp = Path(tmpd) / ("copy_%s.db" % mode)
                shutil.copyfile(str(backup), str(cp))
                c = sqlite3.connect(str(cp), timeout=30)
                try:
                    c.execute("PRAGMA journal_mode=%s" % mode)
                    c.execute("CREATE TABLE IF NOT EXISTS _probe(x)")
                    c.commit()
                    t0 = time.perf_counter()
                    for i in range(30):
                        c.execute("INSERT INTO _probe VALUES (?)", (i,))
                        c.commit()
                    per = (time.perf_counter() - t0) / 30 * 1000
                    out(
                        "journal_mode=%-6s synchronous=FULL : %7.2f ms per commit "
                        "(the app does 2 commits per entry/exit)" % (mode, per)
                    )
                    if mode == "DELETE":
                        delete_ms = per
                    else:
                        wal_ms = per
                finally:
                    c.close()
            if delete_ms > 15:
                findings.append(
                    (
                        "HIGH",
                        "Each commit takes %.1f ms on this disk in rollback-journal mode "
                        "(WAL: %.1f ms). The app does a synchronous commit inside "
                        "'async def' routes, which freezes the entire event loop "
                        "(all HTTP + WebSocket traffic) for that long, twice per "
                        "entry/exit." % (delete_ms, wal_ms),
                        "tools/fix_01_enable_wal.py",
                    )
                )
        finally:
            shutil.rmtree(tmpd, ignore_errors=True)

    section("8. Findings")
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    if not findings:
        out("No problems detected.")
    for sev, text, fix in sorted(findings, key=lambda f: order[f[0]]):
        out("[%s] %s" % (sev, text))
        out("        fix: %s" % fix)
        out()
    out("Code-level causes that no DB script can remove (see docs/DB_DIAGNOSIS.md):")
    out("  * N+1 query in GET /visitors/inside (routes.py)")
    out("  * blocking DB + file I/O inside 'async def' routes (event-loop stalls)")
    out("  * no busy_timeout / WAL / pragmas set per connection (database.py)")
    out("  * 'sync' broadcast makes every client reload everything")

    rdir = db.parent / "diagnostics"
    rdir.mkdir(exist_ok=True)
    rpath = rdir / ("diagnose_%s.txt" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    rpath.write_text("\n".join(REPORT), encoding="utf-8")
    print("\nReport saved to %s" % rpath)


if __name__ == "__main__":
    main()
