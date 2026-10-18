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
WIDTH = 100
SEARCH_BUDGET_S = 25


def interactive():
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def say(line=""):
    print(line)
    sys.stdout.flush()


def clear_screen():
    if interactive():
        os.system("cls" if os.name == "nt" else "clear")


def ask(prompt, default=""):
    if not interactive():
        return default
    try:
        answer = input(prompt).strip().strip('"').strip("'")
    except EOFError:
        return default
    return answer or default


def short_path(p, limit=WIDTH - 8):
    p = str(p)
    if len(p) <= limit:
        return p
    keep = (limit - 5) // 2
    return p[:keep] + " ... " + p[-keep:]


SKIP_DIR_NAMES = {
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "$recycle.bin",
    "system volume information",
    "node_modules",
    ".git",
    "site-packages",
    ".venv",
    "venv",
    "__pycache__",
    "backups",
    "diagnostics",
    "wheels",
    "dist",
    "build",
    "recovery",
    "perflogs",
    "$windows.~bt",
}
DB_SUFFIXES = (".db", ".sqlite", ".sqlite3")


def looks_like_kav1(path, timeout=3, error=None):
    """(is_kav1, visitors_count_or_None). Opens read-only; never raises.
    If `error` is a list, the reason for a failure is appended to it."""
    try:
        con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=timeout)
        try:
            names = {
                r[0]
                for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "visitors" not in names:
                if error is not None:
                    error.append("no 'visitors' table")
                return False, None
            return True, con.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
        finally:
            con.close()
    except Exception as e:
        if error is not None:
            error.append(str(e))
        return False, None


def quick_candidates(script_dir):
    cwd = Path.cwd()
    cands = [
        script_dir.parent / "backend" / DB_NAME,
        script_dir.parent / DB_NAME,
        script_dir / DB_NAME,
        cwd / DB_NAME,
        cwd / "backend" / DB_NAME,
        cwd.parent / DB_NAME,
        cwd.parent / "backend" / DB_NAME,
    ]
    for var in ("APPDATA", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base:
            cands += [
                Path(base) / "Kav1" / "server" / DB_NAME,
                Path(base) / "Kav1" / DB_NAME,
            ]
    return cands


def search_roots(script_dir):
    roots = [script_dir, script_dir.parent, script_dir.parent.parent, Path.cwd()]
    home = Path.home()
    roots.append(home)
    if os.name == "nt":
        for letter in "CDEFGH":
            drive = Path(letter + ":\\")
            if drive.exists():
                roots.append(drive)
    else:
        roots.append(Path("/"))
    seen, out = set(), []
    for r in roots:
        try:
            r = r.resolve()
        except OSError:
            continue
        if r not in seen and r.is_dir():
            seen.add(r)
            out.append(r)
    return out


def bounded_walk(root, max_depth, deadline):
    root_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(str(root), onerror=lambda e: None):
        if time.time() > deadline:
            return
        depth = len(Path(dirpath).parts) - root_depth
        dirnames[:] = (
            [
                d
                for d in dirnames
                if d.lower() not in SKIP_DIR_NAMES and not d.startswith("$")
            ]
            if depth < max_depth
            else []
        )
        for name in filenames:
            if name.lower().endswith(DB_SUFFIXES):
                yield Path(dirpath) / name


def search_databases(script_dir):
    """Every Kav1 database we can find (quick spots first, then a bounded search)."""
    found, seen = [], set()

    def consider(p):
        try:
            r = p.resolve()
        except OSError:
            return
        if r in seen or not r.is_file() or r.stat().st_size == 0:
            return
        seen.add(r)
        if ".pre-" in r.name or r.parent.name.lower() == "backups":
            return
        ok, n = looks_like_kav1(r)
        if ok:
            found.append((r, n))

    for c in quick_candidates(script_dir):
        consider(c)
    if found:
        return found
    say("Searching for the database (up to %d seconds) ..." % SEARCH_BUDGET_S)
    deadline = time.time() + SEARCH_BUDGET_S
    for root in search_roots(script_dir):
        for p in bounded_walk(root, 5, deadline):
            consider(p)
            if time.time() > deadline:
                break
        if found or time.time() > deadline:
            break
    return found


def clean_dropped(text):
    """Path text produced by dragging a file into a console window.

    cmd/Windows Terminal paste "C:\\a b\\x.db" (quoted when it has spaces);
    PowerShell may paste & 'C:\\a b\\x.db'. Returns the bare path text."""
    text = text.strip()
    if text.startswith("&"):
        text = text[1:].strip()
    if text[:1] in ("'", '"'):
        quote = text[0]
        end = text.find(quote, 1)
        text = text[1:end] if end > 0 else text[1:]
    return text.strip().strip("'\"").strip()


def databases_in_folder(folder):
    """Kav1 databases inside a folder that was dragged in (depth <= 4)."""
    found, deadline = [], time.time() + SEARCH_BUDGET_S
    for p in bounded_walk(folder, 4, deadline):
        if ".pre-" in p.name:
            continue
        ok, n = looks_like_kav1(p)
        if ok:
            found.append((p.resolve(), n))
    return found


def ask_for_dropped_db():
    """Ask the operator to drag the database into the window.

    Returns a list of (path, visitors) - empty means: search automatically."""
    say("")
    say("Drag the database file (local_database.db) into THIS window and press Enter.")
    say("(Or just press Enter to let the tool search for it by itself.)")
    while True:
        typed = ask("> ")
        if not typed:
            return []
        p = Path(clean_dropped(typed)).expanduser()
        if p.is_dir():
            found = databases_in_folder(p)
            if found:
                return found
            say(
                "No Kav1 database inside that folder. Drag the file itself, or try again."
            )
            continue
        if not p.is_file():
            say("File not found: %s" % p)
            say("Drag the file again, or press Enter to search automatically.")
            continue
        why = []
        ok, n = looks_like_kav1(p, timeout=20, error=why)
        if ok:
            return [(p.resolve(), n)]
        say("That file is not a usable Kav1 database (%s)." % (why[0] if why else "?"))
        say("Drag the right file, or press Enter to search automatically.")


def find_db(arg):
    if arg:
        p = Path(clean_dropped(arg)).expanduser()
        if not p.is_file():
            sys.exit("ERROR: --db file not found: %s" % p)
        return p.resolve()
    env = os.environ.get("KAV1_DB")
    if env:
        p = Path(env).expanduser()
        if not p.is_file():
            sys.exit("ERROR: KAV1_DB points to a missing file: %s" % p)
        return p.resolve()
    found = ask_for_dropped_db() if interactive() else []
    if not found:
        found = search_databases(Path(__file__).resolve().parent)
    while not found:
        if not interactive():
            sys.exit("ERROR: no Kav1 database found. Re-run with --db <path>.")
        say("\nNo Kav1 database was found automatically.")
        found = ask_for_dropped_db()
        if not found:
            sys.exit("Stopped: no database selected.")
    if len(found) == 1:
        return found[0][0]
    found.sort(key=lambda t: t[0].stat().st_mtime, reverse=True)
    say("\nMore than one Kav1 database found:")
    for i, (p, n) in enumerate(found, 1):
        st = p.stat()
        say("  %d) %s" % (i, short_path(p, WIDTH - 8)))
        say(
            "     %.2f MB, %s visitors, modified %s"
            % (
                st.st_size / 1e6,
                n,
                datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
            )
        )
    if not interactive():
        sys.exit("ERROR: several databases found - re-run with --db <path>.")
    choice = ask(
        "Which one is the LIVE database? number [1 = most recently modified]: ", "1"
    )
    try:
        return found[int(choice) - 1][0]
    except (ValueError, IndexError):
        sys.exit("Invalid choice.")


def confirm_target(db, assume_yes):
    """Show exactly which file is about to be changed and ask (interactive only)."""
    st = db.stat()
    print("Target database: %s" % db)
    print(
        "  %.2f MB, last modified %s"
        % (
            st.st_size / 1e6,
            datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
        )
    )
    if assume_yes or not interactive():
        return
    if (
        ask(
            "Change THIS database (a verified backup is made first)? Type Y to continue: "
        ).lower()
        != "y"
    ):
        sys.exit("Cancelled - nothing was changed.")


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
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = ap.parse_args()
    db = find_db(args.db)
    confirm_target(db, args.yes)

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
