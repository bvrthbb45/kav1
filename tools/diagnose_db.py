#!/usr/bin/env python3
"""Kav1 - database diagnostics v2 (standalone, stdlib only, Python 3.8+).

Designed for an air-gapped machine: the result is shown as a few SCREENS (pages)
that each fit one console window, so you can photograph every page and send the
photos. A full text report is also saved next to the database.

What it does, in order:
  1. Finds the database (auto-search; asks you if there is more than one or none).
  2. BACKS IT UP FIRST (SQLite online-backup API) and verifies the backup.
  3. Inspects the DB strictly READ-ONLY: size, rows, indexes, WAL, fragmentation,
     integrity, where it lives (OneDrive / network drive), disk speed.
  4. Times the exact queries the Kav1 backend runs and shows their query plans.
  5. Measures commit latency on a throw-away COPY (never on the real DB).
  6. Profiles the contractor properties (project / infosec / expiry fields).
  7. Prints a verdict, ranked findings and the exact fix to run for each.

It never changes the real database, never prints visitor names or IDs, and is safe
to run repeatedly and while the server is up. One failing check never stops the
others; an unexpected error is shown and saved instead of a bare traceback.

Usage:
  python diagnose_db.py                 # find the DB automatically
  python diagnose_db.py --db C:\\path\\local_database.db
  python diagnose_db.py --no-write-test # skip the commit-latency test
  python diagnose_db.py --plain         # no screen clearing / no pauses
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import textwrap
import time
import traceback
from datetime import date, datetime
from pathlib import Path

TOOL_VERSION = "2.1"
DB_NAME = "local_database.db"
SLOW_MS = 100.0
SEARCH_BUDGET_S = 25
WIDTH = 100  # characters per line on every page (narrowed to the console in main())

# --- contractor property keys (mirror of backend/app/fields.py) -----------------
PROJECT_ALIASES = ("פרויקט", "פרויקטים", "project", "projects")
INFOSEC_KEY = "אבטחת מידע"
INFOSEC_EXPIRY_KEY = "תוקף אבטחת מידע"
CLASSIFICATION_EXPIRY_KEY = "תוקף סיווג"
EXPIRY_KEYS = (CLASSIFICATION_EXPIRY_KEY, INFOSEC_EXPIRY_KEY)
INFOSEC_OPTIONS = ("מאושר", "מאושר חריג על ידי מפקד היחידה", "לא מאושר")
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%y")

REPORT = []  # full text report (written to a file)


# =============================================================================
# console helpers
# =============================================================================
def setup_console():
    if os.name == "nt":
        try:
            os.system("chcp 65001 >nul 2>nul")
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


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


def fmt_mb(n):
    return "%.2f MB" % (n / 1e6)


# Hebrew cannot be shown reliably in a Windows console (code pages differ), so any
# non-ASCII text is printed as a reversible Latin transliteration, e.g. H:prwyq9
HEB = {
    "א": "a",
    "ב": "b",
    "ג": "g",
    "ד": "d",
    "ה": "h",
    "ו": "w",
    "ז": "z",
    "ח": "x",
    "ט": "9",
    "י": "y",
    "כ": "k",
    "ך": "K",
    "ל": "l",
    "מ": "m",
    "ם": "M",
    "נ": "n",
    "ן": "N",
    "ס": "s",
    "ע": "e",
    "פ": "p",
    "ף": "P",
    "צ": "c",
    "ץ": "C",
    "ק": "q",
    "ר": "r",
    "ש": "$",
    "ת": "t",
    "״": '"',
    "׳": "'",
    "־": "-",
}
HEB_LEGEND = "Hebrew letters are shown in Latin as H:... (a b g d h w z x 9 y k l m n s e p c q r $ t)"


def disp(text):
    """ASCII-safe display form of any text (Hebrew -> H:transliteration)."""
    text = str(text)
    if all(ord(ch) < 128 for ch in text):
        return text
    out = []
    for ch in text:
        if ord(ch) < 128:
            out.append(ch)
        else:
            out.append(HEB.get(ch, "\\u%04x" % ord(ch)))
    return "H:" + "".join(out)


def short_path(p, limit=WIDTH - 8):
    p = str(p)
    if len(p) <= limit:
        return p
    keep = (limit - 5) // 2
    return p[:keep] + " ... " + p[-keep:]


# =============================================================================
# locating the database
# =============================================================================
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


# =============================================================================
# sqlite helpers
# =============================================================================
def connect(db, readonly=True, timeout=30):
    uri = db.as_uri() + ("?mode=ro" if readonly else "")
    return sqlite3.connect(uri, uri=True, timeout=timeout)


def user_tables(con):
    return [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def row_counts(con):
    return {
        t: con.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
        for t in user_tables(con)
    }


def pragma(con, name):
    r = con.execute("PRAGMA %s" % name).fetchone()
    return r[0] if r else None


def make_backup(db):
    """Verified online backup next to the DB. Returns its path."""
    bdir = db.parent / "backups"
    bdir.mkdir(exist_ok=True)
    free = shutil.disk_usage(str(bdir)).free
    if free < db.stat().st_size * 3:
        raise RuntimeError(
            "not enough free disk space for a safe backup (%s free)" % fmt_mb(free)
        )
    dest = bdir / (
        "%s.pre-diagnose.%s.db" % (db.stem, datetime.now().strftime("%Y%m%d_%H%M%S"))
    )
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
        raise RuntimeError("backup verification failed (%s)" % dest)
    return dest


def timed(con, sql, params=()):
    t0 = time.perf_counter()
    rows = con.execute(sql, params).fetchall()
    return (time.perf_counter() - t0) * 1000.0, rows


def plan(con, sql, params=()):
    return [r[3] for r in con.execute("EXPLAIN QUERY PLAN " + sql, params)]


def parse_date(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


# =============================================================================
# the checks (each returns plain data; failures are caught by safe())
# =============================================================================
class Result(dict):
    pass


def safe(R, label, fn, default=None):
    try:
        return fn()
    except Exception as e:  # one broken check must not stop the others
        R.setdefault("errors", []).append("%s: %s" % (label, e))
        return default


def check_location(db):
    """Where does the file live? Sync folders and network drives are slow/locky."""
    notes = []
    p = str(db)
    low = p.lower()
    if p.startswith("\\\\"):
        notes.append("network share (UNC path)")
    for marker in (
        "onedrive",
        "dropbox",
        "google drive",
        "googledrive",
        "icloud",
        "box sync",
    ):
        if marker in low:
            notes.append("inside a cloud-sync folder (%s)" % marker)
            break
    if os.name == "nt" and len(p) > 1 and p[1] == ":":
        try:
            import ctypes

            kind = ctypes.windll.kernel32.GetDriveTypeW(p[:3])
            if kind == 4:
                notes.append("on a mapped NETWORK drive (%s)" % p[:2])
            elif kind == 2:
                notes.append("on a REMOVABLE drive (%s)" % p[:2])
        except Exception:
            pass
    return notes


def check_fsync(directory, n=20):
    """Average write+fsync latency (ms) of the disk holding the DB."""
    fd, name = tempfile.mkstemp(prefix="kav1fsync_", dir=str(directory))
    try:
        buf = b"x" * 4096
        t0 = time.perf_counter()
        for _ in range(n):
            os.write(fd, buf)
            os.fsync(fd)
        return (time.perf_counter() - t0) / n * 1000.0
    finally:
        os.close(fd)
        try:
            os.remove(name)
        except OSError:
            pass


def check_basics(R, con, db):
    wal, shm = Path(str(db) + "-wal"), Path(str(db) + "-shm")
    R["size"] = db.stat().st_size
    R["wal_size"] = wal.stat().st_size if wal.exists() else None
    R["shm"] = shm.exists()
    R["page_size"] = pragma(con, "page_size")
    R["page_count"] = pragma(con, "page_count")
    R["freelist"] = pragma(con, "freelist_count")
    R["journal"] = str(pragma(con, "journal_mode"))
    R["auto_vacuum"] = pragma(con, "auto_vacuum")
    pc = R["page_count"] or 0
    R["free_pct"] = 100.0 * R["freelist"] / pc if pc else 0.0
    R["tables"] = user_tables(con)
    R["counts"] = row_counts(con)
    R["has_stat"] = bool(
        con.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_stat1'").fetchone()
    )


def check_integrity(R, con):
    R["quick_check"] = pragma(con, "quick_check")
    R["fk_violations"] = len(con.execute("PRAGMA foreign_key_check").fetchall())


def check_schema(R, con):
    cols = {}
    for t in R["tables"]:
        cols[t] = [r[1] for r in con.execute("PRAGMA table_info('%s')" % t)]
    R["columns"] = cols
    idx = {}
    for t in R["tables"]:
        for row in con.execute("PRAGMA index_list('%s')" % t):
            name, uniq = row[1], row[2]
            idx.setdefault(t, []).append(
                (
                    name,
                    [c[2] for c in con.execute("PRAGMA index_info('%s')" % name)],
                    bool(uniq),
                )
            )
    R["indexes"] = idx
    try:
        R["space"] = con.execute(
            "SELECT name, SUM(pgsize) FROM dbstat GROUP BY name ORDER BY 2 DESC"
        ).fetchall()[:8]
    except sqlite3.Error:
        R["space"] = None


def has_index(R, table, cols):
    return any(
        c[: len(cols)] == cols for _, c, _ in R.get("indexes", {}).get(table, [])
    )


def check_data(R, con):
    if "visitors" in R["tables"]:
        n, inside, avgp, maxp = con.execute(
            "SELECT COUNT(*), SUM(inside), AVG(LENGTH(properties)), MAX(LENGTH(properties)) "
            "FROM visitors"
        ).fetchone()
        R["visitors"], R["inside"] = n, inside or 0
        R["avg_props"], R["max_props"] = avgp or 0, maxp or 0
    if "visitor_logs" in R["tables"]:
        n, lo, hi, nv = con.execute(
            "SELECT COUNT(*), MIN(timestamp), MAX(timestamp), COUNT(DISTINCT visitor_dbid) "
            "FROM visitor_logs"
        ).fetchone()
        R["logs"], R["log_first"], R["log_last"], R["log_visitors"] = n, lo, hi, nv


Q_LATEST = (
    "SELECT * FROM visitor_logs WHERE visitor_dbid = ? "
    "ORDER BY timestamp DESC, id DESC LIMIT 1"
)
Q_JOIN = (
    "SELECT v.dbid, v.name, v.visitorid, v.properties, l.action, l.timestamp "
    "FROM visitors v LEFT JOIN visitor_logs l ON l.id = ("
    "SELECT id FROM visitor_logs WHERE visitor_dbid = v.dbid "
    "ORDER BY timestamp DESC, id DESC LIMIT 1) WHERE v.inside"
)


def check_queries(R, con):
    out = []

    def bench(label, sql, params=()):
        best, rows = None, []
        for _ in range(3):
            ms, rows = timed(con, sql, params)
            best = ms if best is None else min(best, ms)
        p = plan(con, sql, params)
        bad = any("SCAN visitor_logs" in x or "TEMP B-TREE" in x for x in p)
        out.append(
            {"label": label, "ms": best, "rows": len(rows), "plan": p, "bad": bad}
        )

    t = R["tables"]
    if "visitors" in t:
        bench("all visitors (GET /visitors)", "SELECT * FROM visitors")
        bench(
            "lookup by visitor id", "SELECT * FROM visitors WHERE visitorid = ?", ("-",)
        )
        bench(
            "search by name (%text%)",
            "SELECT * FROM visitors WHERE lower(name) LIKE lower(?)",
            ("%a%",),
        )
    if "visitor_logs" in t:
        bench(
            "latest 50 logs (GET /logs)",
            "SELECT * FROM visitor_logs ORDER BY timestamp DESC LIMIT 50",
        )
        bench(
            "latest 1000 logs",
            "SELECT * FROM visitor_logs ORDER BY timestamp DESC LIMIT 1000",
        )
        one = con.execute(
            "SELECT visitor_dbid FROM visitor_logs GROUP BY visitor_dbid "
            "ORDER BY COUNT(*) DESC LIMIT 1"
        ).fetchone()
        bench("latest log of ONE visitor", Q_LATEST, (one[0] if one else -1,))
    R["queries"] = out

    if "visitors" in t and "visitor_logs" in t:
        ids = [r[0] for r in con.execute("SELECT dbid FROM visitors WHERE inside")]
        t0, done = time.perf_counter(), 0
        for vid in ids:
            con.execute(Q_LATEST, (vid,)).fetchall()
            done += 1
            if time.perf_counter() - t0 > 20:
                break
        total = (time.perf_counter() - t0) * 1000.0
        if done and done < len(ids):
            total = total / done * len(ids)
        R["n1_ms"], R["n1_rows"] = total, len(ids)
        best = min(timed(con, Q_JOIN)[0] for _ in range(3))
        R["join_ms"] = best


def check_predicted(R, db, backup):
    """What the numbers would be AFTER the fixes - measured on a temporary copy."""
    tmpd = tempfile.mkdtemp(prefix="kav1pred_", dir=str(db.parent))
    try:
        cp = Path(tmpd) / "copy.db"
        shutil.copyfile(str(backup), str(cp))
        c = sqlite3.connect(str(cp), timeout=30)
        try:
            if "visitor_logs" in R["tables"]:
                c.execute(
                    "CREATE INDEX IF NOT EXISTS p1 ON visitor_logs(visitor_dbid, timestamp)"
                )
                c.execute("CREATE INDEX IF NOT EXISTS p2 ON visitor_logs(timestamp)")
            c.execute("ANALYZE")
            c.commit()
            if "visitors" in R["tables"] and "visitor_logs" in R["tables"]:
                R["pred_join_ms"] = min(timed(c, Q_JOIN)[0] for _ in range(3))
                R["pred_logs_ms"] = min(
                    timed(
                        c, "SELECT * FROM visitor_logs ORDER BY timestamp DESC LIMIT 50"
                    )[0]
                    for _ in range(3)
                )
        finally:
            c.close()
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def check_commit_latency(R, db, backup):
    try:
        tmpd = tempfile.mkdtemp(prefix="kav1diag_", dir=str(db.parent))
    except OSError:
        tmpd = tempfile.mkdtemp(prefix="kav1diag_")
        R["notes"] = R.get("notes", []) + ["latency test ran in the system temp folder"]
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
                R["commit_" + mode.lower()] = (time.perf_counter() - t0) / 30 * 1000
            finally:
                c.close()
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def check_properties(R, con):
    """Profile visitors.properties for every key: fill rate, distinct values,
    date-like fields (min/max/expired) and the values of small categorical fields.

    No visitor names / IDs are collected; values are kept only for fields with a
    handful of distinct values (categories) and for project / infosec fields."""
    stats, bad_json, total = {}, 0, 0
    today = date.today()
    for (raw,) in con.execute("SELECT properties FROM visitors"):
        total += 1
        if raw in (None, ""):
            continue
        try:
            props = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            bad_json += 1
            continue
        if not isinstance(props, dict):
            bad_json += 1
            continue
        for k, v in props.items():
            text = "" if v is None else str(v).strip()
            if not text:
                continue
            st = stats.setdefault(
                str(k),
                {
                    "n": 0,
                    "vals": {},
                    "dates": 0,
                    "dmin": None,
                    "dmax": None,
                    "expired": 0,
                    "soon": 0,
                    "later": 0,
                    "numeric": 0,
                },
            )
            st["n"] += 1
            if text in st["vals"] or len(st["vals"]) < 300:
                st["vals"][text] = st["vals"].get(text, 0) + 1
            parsed = parse_date(text)
            if parsed is not None and len(text) >= 6:
                st["dates"] += 1
                st["dmin"] = parsed if st["dmin"] is None else min(st["dmin"], parsed)
                st["dmax"] = parsed if st["dmax"] is None else max(st["dmax"], parsed)
                left = (parsed - today).days
                if left < 0:
                    st["expired"] += 1
                elif left <= 30:
                    st["soon"] += 1
                else:
                    st["later"] += 1
            try:
                float(text.replace(",", ""))
                st["numeric"] += 1
            except ValueError:
                pass
    keys = []
    for k, st in stats.items():
        distinct = len(st["vals"]) if len(st["vals"]) < 300 else 300
        if st["dates"] >= 0.6 * st["n"]:
            kind = "DATE"
        elif st["numeric"] >= 0.9 * st["n"]:
            kind = "NUM"
        elif distinct <= 8:
            kind = "CATEG"
        else:
            kind = "TEXT"
        keys.append(
            {"key": k, "n": st["n"], "distinct": distinct, "kind": kind, "st": st}
        )
    keys.sort(key=lambda e: -e["n"])
    alias = {a.lower() for a in PROJECT_ALIASES}
    R["props"] = {
        "total": total,
        "bad_json": bad_json,
        "keys": keys,
        "project_keys": [e for e in keys if e["key"].strip().lower() in alias],
        "infosec": next((e for e in keys if e["key"].strip() == INFOSEC_KEY), None),
        "legacy_expiry_keys": [e for e in keys if e["kind"] == "DATE"],
    }


# =============================================================================
# findings
# =============================================================================
FIX_WAL = "2_fix_enable_wal.bat"
FIX_IDX = "3_fix_add_indexes.bat"
FIX_VAC = "4_fix_vacuum_analyze.bat"


def build_findings(R):
    f = []

    def add(sev, text, fix):
        f.append((sev, text, fix))

    if R.get("quick_check") not in (None, "ok"):
        add(
            "CRITICAL",
            "Integrity check reports corruption: %s" % R["quick_check"],
            "DO NOT run fixes. Restore from backups\\ and tell the developer.",
        )
    if R.get("fk_violations"):
        add(
            "MEDIUM",
            "%d log rows point to deleted visitors (orphans)." % R["fk_violations"],
            "Harmless for speed; nothing is deleted automatically.",
        )
    for note in R.get("location", []):
        add(
            "HIGH",
            "The database file is %s. Sync clients and network drives lock or "
            "rewrite the file and make every commit slow." % note,
            "Move the whole server folder to a local non-synced folder, e.g. C:\\Kav1\\ "
            "(stop the server first, copy the folder, start the server from the new place).",
        )
    if R.get("tables") is not None:
        if "visitor_logs" in R["tables"]:
            if not has_index(R, "visitor_logs", ["visitor_dbid"]):
                add(
                    "CRITICAL",
                    "visitor_logs has NO index on visitor_dbid: every 'latest log of "
                    "visitor' lookup (one per inside visitor, per refresh) scans the whole log table.",
                    FIX_IDX,
                )
            if not has_index(R, "visitor_logs", ["timestamp"]):
                add(
                    "HIGH",
                    "visitor_logs has NO index on timestamp: the logs screen and the "
                    "ordering by arrival sort the entire table every time.",
                    FIX_IDX,
                )
        if str(R.get("journal", "")).lower() != "wal":
            add(
                "HIGH",
                "Journal mode is '%s' (not WAL): every commit waits for the disk twice "
                "and writers block readers - the server stalls while anyone saves."
                % R.get("journal"),
                FIX_WAL + " (server stopped)",
            )
        if not R.get("has_stat"):
            add(
                "LOW",
                "No ANALYZE statistics: SQLite's query planner is guessing.",
                FIX_IDX,
            )
        if R.get("free_pct", 0) >= 5:
            add(
                "LOW",
                "%.1f%% of the file is free pages (fragmentation)." % R["free_pct"],
                FIX_VAC,
            )
        if R.get("wal_size") and R["wal_size"] > 50e6:
            add(
                "MEDIUM",
                "-wal file is %s: checkpoints are not keeping up."
                % fmt_mb(R["wal_size"]),
                FIX_VAC + " (server stopped)",
            )
    if R.get("n1_ms") is not None and R["n1_ms"] > 500:
        add(
            "CRITICAL",
            "Loading the 'inside' list costs ~%.0f ms of pure database time (%d "
            "inside visitors, old per-visitor queries). Every client repeats it on each change."
            % (R["n1_ms"], R["n1_rows"]),
            FIX_IDX + " + run the NEW server version (single-query list)",
        )
    elif R.get("n1_ms") is not None and R["n1_ms"] > 100:
        add(
            "MEDIUM",
            "Loading the 'inside' list costs ~%.0f ms of database time." % R["n1_ms"],
            FIX_IDX,
        )
    d, w = R.get("commit_delete"), R.get("commit_wal")
    if d is not None and d > 15:
        add(
            "HIGH",
            "One commit takes %.1f ms on this disk (WAL: %.1f ms). Old server versions "
            "froze all traffic for this long, twice per entry/exit." % (d, w or 0),
            FIX_WAL + " + run the NEW server version",
        )
    if R.get("fsync_ms") is not None and R["fsync_ms"] > 20:
        add(
            "HIGH",
            "Raw disk write+flush takes %.1f ms (healthy SSD: under 5 ms). Slow disk or "
            "antivirus scanning the database folder." % R["fsync_ms"],
            "Ask IT to exclude the Kav1 server folder from real-time antivirus scanning.",
        )
    if R.get("logs", 0) > 500000:
        add(
            "MEDIUM",
            "visitor_logs is very large (%d rows)." % R["logs"],
            "Tell the developer: archiving old logs may be needed.",
        )
    if R.get("disk_free") is not None and R["disk_free"] < 500e6:
        add(
            "MEDIUM",
            "Only %s free on the database disk." % fmt_mb(R["disk_free"]),
            "Free disk space.",
        )
    pr = R.get("props")
    if pr and pr["bad_json"]:
        add(
            "MEDIUM",
            "%d visitors have unreadable properties data." % pr["bad_json"],
            "Tell the developer.",
        )
    for err in R.get("errors", []):
        add("LOW", "A check could not run: %s" % err, "Send this to the developer.")
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    f.sort(key=lambda x: order[x[0]])
    return f


def verdict(findings):
    c = sum(1 for s, _, _ in findings if s == "CRITICAL")
    h = sum(1 for s, _, _ in findings if s == "HIGH")
    m = sum(1 for s, _, _ in findings if s == "MEDIUM")
    if c:
        return "PROBLEMS FOUND - %d critical, %d high" % (c, h)
    if h:
        return "SLOW - %d high-priority issue(s)" % h
    if m:
        return "MOSTLY OK - %d medium issue(s)" % m
    if findings:
        return "HEALTHY - only minor notes"
    return "HEALTHY - nothing needs fixing"


# =============================================================================
# screens (pages) - every page is built to fit one console window
# =============================================================================
def wrap(text, indent="", first=""):
    return textwrap.wrap(
        text, WIDTH, initial_indent=first, subsequent_indent=indent
    ) or [""]


def bar(char="="):
    return char * WIDTH


def ms_cell(ms):
    return "%8.1f ms%s" % (ms, "  SLOW" if ms > SLOW_MS else "")


def page_overview(R, findings):
    L = []
    L.append("DATABASE: " + short_path(R["db"], WIDTH - 10))
    c = R.get("counts", {})
    L.append(
        "Size %s | visitors %s (inside now: %s) | log rows %s | integrity: %s"
        % (
            fmt_mb(R["size"]),
            R.get("visitors", "?"),
            R.get("inside", "?"),
            R.get("logs", "?"),
            "OK" if R.get("quick_check") == "ok" else R.get("quick_check", "?"),
        )
    )
    L.append(
        "Journal mode: %s | page size %s | free pages %s (%.1f%%) | WAL file: %s"
        % (
            R.get("journal", "?").upper(),
            R.get("page_size"),
            R.get("freelist"),
            R.get("free_pct", 0),
            fmt_mb(R["wal_size"]) if R.get("wal_size") else "none",
        )
    )
    if R.get("log_first"):
        L.append(
            "Log history: %s  ->  %s"
            % (str(R["log_first"])[:19], str(R["log_last"])[:19])
        )
    loc = R.get("location") or []
    L.append("Location: " + ("; ".join(loc).upper() if loc else "local disk (OK)"))
    L.append(
        "Disk write+flush: %s | commit now: %s | commit with WAL: %s"
        % (
            "%.1f ms" % R["fsync_ms"] if R.get("fsync_ms") is not None else "n/a",
            (
                "%.1f ms" % R["commit_delete"]
                if R.get("commit_delete") is not None
                else "n/a"
            ),
            "%.1f ms" % R["commit_wal"] if R.get("commit_wal") is not None else "n/a",
        )
    )
    if R.get("n1_ms") is not None:
        L.append(
            "'Inside' list (%d inside): old server %.0f ms | new server, today %.0f ms"
            % (R["n1_rows"], R["n1_ms"], R.get("join_ms", 0))
        )
    if R.get("pred_join_ms") is not None:
        L.append(
            "PREDICTED after the fixes: 'inside' list %.1f ms | logs screen %.1f ms | "
            "save %s ms"
            % (
                R["pred_join_ms"],
                R.get("pred_logs_ms", 0),
                "%.1f" % R["commit_wal"] if R.get("commit_wal") is not None else "?",
            )
        )
    L.append("Backup taken: " + short_path(R["backup"], WIDTH - 14))
    L.append("")
    L.append(bar("-"))
    L.append("VERDICT:  " + verdict(findings))
    L.append(bar("-"))
    L.append("Top issues (details + fixes on the next pages):")
    for sev, text, _ in findings[:5]:
        L += wrap("[%s] %s" % (sev, text), indent="    ", first=" *  ")[:3]
    if not findings:
        L.append("  none")
    return "OVERVIEW", L


def page_speed(R):
    L = [
        "Best of 3 runs per query. SLOW = over %d ms. Plan: SCAN = reads whole table, "
        "IDX = uses an index." % SLOW_MS,
        "",
    ]
    L.append("%-34s %-14s %6s  %s" % ("QUERY", "TIME", "ROWS", "PLAN"))
    L.append(bar("-"))
    for q in R.get("queries", []):
        pl = "; ".join(q["plan"])
        pl = pl.replace("USING INDEX", "IDX").replace("USING COVERING INDEX", "IDX")
        pl = pl.replace("USE TEMP B-TREE FOR ORDER BY", "SORT")
        flag = " (!)" if q["bad"] else ""
        L.append(
            "%-34s %-14s %6d  %s%s"
            % (q["label"][:34], ms_cell(q["ms"]).strip(), q["rows"], pl[:34], flag)
        )
    if R.get("n1_ms") is not None:
        L.append("")
        L.append("'Inside' list for %d visitors:" % R["n1_rows"])
        L.append("   old server (query per visitor) : %s" % ms_cell(R["n1_ms"]).strip())
        L.append(
            "   new server, database as it is  : %s" % ms_cell(R["join_ms"]).strip()
        )
        if R.get("pred_join_ms") is not None:
            L.append(
                "   new server, after the fixes    : %s"
                % ms_cell(R["pred_join_ms"]).strip()
            )
    L.append("")
    L.append("Commit speed (30 saves on a throw-away copy):")
    for key, label in (
        ("commit_delete", "current mode (rollback journal)"),
        ("commit_wal", "WAL mode"),
    ):
        if R.get(key) is not None:
            L.append("   %-34s %s per save" % (label, ms_cell(R[key]).strip()))
    if R.get("fsync_ms") is not None:
        L.append(
            "Raw disk write+flush: %.1f ms (SSD under 5 ms is healthy)" % R["fsync_ms"]
        )
    return "SPEED", L


def page_structure(R):
    L = []
    L += wrap(
        "Tables: "
        + ", ".join("%s=%d" % (t, n) for t, n in R.get("counts", {}).items()),
        indent="  ",
    )
    L.append("INDEXES")
    for t, items in R.get("indexes", {}).items():
        for name, cols, uniq in items:
            L.append(
                "  %-16s %-36s %s%s"
                % (t[:16], name[:36], ",".join(cols), " UNIQUE" if uniq else "")
            )
    L.append(
        "  ANALYZE statistics            : %s"
        % ("present" if R.get("has_stat") else "MISSING")
    )
    L.append(
        "  visitor_logs(visitor_dbid, ..): %s"
        % ("present" if has_index(R, "visitor_logs", ["visitor_dbid"]) else "MISSING")
    )
    L.append(
        "  visitor_logs(timestamp)       : %s"
        % ("present" if has_index(R, "visitor_logs", ["timestamp"]) else "MISSING")
    )
    if R.get("space"):
        L.append("SPACE USED BY")
        for name, nbytes in R["space"][:5]:
            L.append("  %-44s %s" % (name[:44], fmt_mb(nbytes)))
    L.append("COLUMNS")
    for t, cols in R.get("columns", {}).items():
        L += wrap("%s: %s" % (t, ", ".join(cols)), indent="    ", first="  ")
    L.append(
        "Properties size per visitor: avg %.0f bytes, max %s bytes"
        % (R.get("avg_props", 0), R.get("max_props", 0))
    )
    if R.get("disk_free") is not None:
        L.append("Free disk space on the database drive: %s" % fmt_mb(R["disk_free"]))
    L.append(
        "Python %s | SQLite %s | %s"
        % (sys.version.split()[0], sqlite3.sqlite_version, sys.platform)
    )
    return "STRUCTURE", L


def page_findings(R, findings):
    L = []
    if not findings:
        L.append("No problems detected. Nothing to fix.")
    for i, (sev, text, fix) in enumerate(findings, 1):
        L += wrap("%d. [%s] %s" % (i, sev, text), indent="   ")
        L += wrap("-> %s" % fix, indent="      ", first="   ")
    L.append("")
    L.append(bar("-"))
    L.append("WHAT TO DO (in this order, server stopped for steps 2 and 4):")
    steps = []
    fixes = " ".join(f for _, _, f in findings)
    if FIX_WAL in fixes:
        steps.append("tools\\windows\\%s" % FIX_WAL)
    if FIX_IDX in fixes:
        steps.append("tools\\windows\\%s" % FIX_IDX)
    if FIX_VAC in fixes:
        steps.append("tools\\windows\\%s  (only if fragmentation is listed)" % FIX_VAC)
    if "NEW server version" in fixes:
        steps.append(
            "start the server from the NEW version of Kav1 (single-query list)"
        )
    for i, s in enumerate(steps, 1):
        L.append("  %d) %s" % (i, s))
    if not steps:
        L.append("  (no scripts needed)")
    L.append("Every script makes a verified backup first and never deletes data.")
    return "FINDINGS AND FIXES", L


def kind_note(e):
    return {"DATE": "date", "NUM": "number", "CATEG": "category", "TEXT": "text"}[
        e["kind"]
    ]


def page_fields(R):
    pr = R.get("props")
    if not pr:
        return "CONTRACTOR FIELDS", ["(not available)"]
    L = [
        "Field NAMES and counts only - no visitor names, IDs or phone numbers are shown.",
    ]
    L += wrap(HEB_LEGEND, indent="  ")
    L.append(
        "Visitors: %d with properties (unreadable: %d) | different fields in use: %d"
        % (pr["total"], pr["bad_json"], len(pr["keys"]))
    )
    L.append("%-34s %9s %9s  %s" % ("FIELD (key)", "FILLED", "DISTINCT", "LOOKS LIKE"))
    L.append(bar("-"))
    for e in pr["keys"]:
        L.append(
            "%-34s %9d %9s  %s"
            % (
                disp(e["key"])[:34],
                e["n"],
                e["distinct"] if e["distinct"] < 300 else "300+",
                kind_note(e),
            )
        )
    return "CONTRACTOR FIELDS (1/2)", L


def page_field_values(R):
    pr = R.get("props")
    if not pr:
        return "CONTRACTOR FIELD VALUES", ["(not available)"]
    L = []
    dates = pr["legacy_expiry_keys"]
    L.append("DATE FIELDS (possible validity / expiry dates)")
    if not dates:
        L.append("  none found")
    for e in dates[:6]:
        st = e["st"]
        L.append("  %s" % disp(e["key"])[: WIDTH - 4])
        L.append(
            "      %d dates | %s .. %s | expired %d | next 30 days %d | later %d"
            % (
                st["dates"],
                st["dmin"],
                st["dmax"],
                st["expired"],
                st["soon"],
                st["later"],
            )
        )
    L.append("")
    L.append(
        "PROJECT field: "
        + (
            ", ".join("%s x%d" % (disp(e["key"]), e["n"]) for e in pr["project_keys"])
            if pr["project_keys"]
            else "no field named like 'project'"
        )
    )
    for e in pr["project_keys"][:1]:
        vals = sorted(e["st"]["vals"].items(), key=lambda kv: -kv[1])
        for name, n in vals[:8]:
            L.append("    %-42s %d" % (disp(name)[:42], n))
        if len(vals) > 8:
            L.append("    ... %d more projects" % (len(vals) - 8))
    L.append("")
    inf = pr.get("infosec")
    L.append(
        "INFORMATION SECURITY field (%s): %s"
        % (disp(INFOSEC_KEY), "not found" if inf is None else "%d filled" % inf["n"])
    )
    if inf:
        for name, n in sorted(inf["st"]["vals"].items(), key=lambda kv: -kv[1])[:6]:
            tag = "" if name in INFOSEC_OPTIONS else "   <- not one of the 3 new values"
            L.append("    %-42s %d%s" % (disp(name)[:42], n, tag))
    L.append("")
    cats = [
        e
        for e in pr["keys"]
        if e["kind"] == "CATEG" and e not in pr["project_keys"] and e is not inf
    ][:5]
    L.append("SMALL CATEGORY FIELDS (up to 8 different values)")
    if not cats:
        L.append("  none")
    for e in cats:
        vals = sorted(e["st"]["vals"].items(), key=lambda kv: -kv[1])[:5]
        L += wrap(
            "%s: %s"
            % (
                disp(e["key"]),
                ", ".join("%s x%d" % (disp(v)[:20], n) for v, n in vals),
            ),
            indent="      ",
            first="  ",
        )
    return "CONTRACTOR FIELDS (2/2)", L


def build_pages(R, findings):
    return [
        page_overview(R, findings),
        page_speed(R),
        page_structure(R),
        page_findings(R, findings),
        page_fields(R),
        page_field_values(R),
    ]


def render_pages(pages, generated):
    """Split into screens that fit the console height."""
    rows = max(20, shutil.get_terminal_size((WIDTH, 30)).lines - 4)
    screens = []
    for title, lines in pages:
        lines = [x if len(x) <= WIDTH else x[: WIDTH - 1] + ">" for x in lines]
        size = rows - 3
        if size < len(lines) <= size + 3:  # avoid a tiny orphan page: shrink the header
            size = len(lines)
        chunks = [lines[i : i + size] for i in range(0, max(len(lines), 1), size)] or [
            []
        ]
        for n, chunk in enumerate(chunks, 1):
            suffix = "" if len(chunks) == 1 else " (%d/%d)" % (n, len(chunks))
            screens.append((title + suffix, chunk))
    total = len(screens)
    out = []
    for i, (title, lines) in enumerate(screens, 1):
        head = [
            "KAV1 DB DIAGNOSTIC v%s | %s | PAGE %d OF %d"
            % (TOOL_VERSION, generated, i, total),
            "== " + title + " " + "=" * max(3, WIDTH - len(title) - 4),
        ]
        out.append(head + lines)
    return out


def show_screens(screens, plain):
    for i, screen in enumerate(screens):
        if not plain:
            clear_screen()
        for line in screen:
            say(line)
        if i < len(screens) - 1 and not plain and interactive():
            say("")
            say(">>> Photograph this screen, then press Enter for the next page ...")
            ask("")
    if not plain and interactive():
        say("")
        say(
            ">>> End of report (%d pages). All pages are also saved in the report file."
            % len(screens)
        )


# =============================================================================
# main
# =============================================================================
def run(args):
    R = Result(errors=[])
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    say("Kav1 database diagnostic v%s - %s" % (TOOL_VERSION, generated))
    say("Python %s | SQLite %s" % (sys.version.split()[0], sqlite3.sqlite_version))
    db = find_db(args.db)
    R["db"] = str(db)
    say("Database: %s" % db)

    why = []
    ok, _ = looks_like_kav1(db, timeout=20, error=why)
    if not ok:
        reason = why[0] if why else "unknown reason"
        if "locked" in reason.lower():
            sys.exit(
                "ERROR: the database is locked by another program (%s).\n"
                "Wait a moment and run again; if it keeps happening, stop the "
                "Kav1 server first." % reason
            )
        sys.exit("ERROR: %s cannot be used as a Kav1 database: %s" % (db, reason))

    say("[1/6] Backing up the database (verified) ...")
    try:
        R["backup"] = make_backup(db)
    except Exception as e:
        sys.exit("ERROR: backup failed, nothing else was done: %s" % e)
    say("      OK: %s" % R["backup"])

    say("[2/6] Reading structure, integrity and data ...")
    con = connect(db, readonly=True)
    try:
        check_basics(R, con, db)
        safe(R, "integrity", lambda: check_integrity(R, con))
        safe(R, "schema", lambda: check_schema(R, con))
        safe(R, "data", lambda: check_data(R, con))
        say("[3/6] Timing the queries the server runs ...")
        safe(R, "query timings", lambda: check_queries(R, con))
        say("[4/6] Profiling contractor fields ...")
        if "visitors" in R["tables"]:
            safe(R, "properties", lambda: check_properties(R, con))
    finally:
        con.close()

    say("[5/6] Checking the disk and where the file lives ...")
    R["location"] = safe(R, "location", lambda: check_location(db), [])
    R["fsync_ms"] = safe(R, "disk speed", lambda: check_fsync(db.parent))
    R["disk_free"] = safe(
        R, "disk space", lambda: shutil.disk_usage(str(db.parent)).free
    )
    if not args.no_write_test:
        say("[6/6] Measuring commit speed on a temporary copy ...")
        safe(R, "commit speed", lambda: check_commit_latency(R, db, R["backup"]))
        safe(R, "prediction", lambda: check_predicted(R, db, R["backup"]))
    else:
        say("[6/6] Commit-speed test skipped.")

    findings = build_findings(R)
    screens = render_pages(build_pages(R, findings), generated)

    rdir = db.parent / "diagnostics"
    try:
        rdir.mkdir(exist_ok=True)
        rpath = rdir / ("diagnose_%s.txt" % datetime.now().strftime("%Y%m%d_%H%M%S"))
        flat = []
        for screen in render_pages(build_pages(R, findings), generated):
            flat += screen + [""]
        rpath.write_text("\n".join(flat), encoding="utf-8-sig")
        R["report"] = rpath
    except OSError as e:
        R["errors"].append("could not save the report file: %s" % e)

    show_screens(screens, args.plain)
    if R.get("report"):
        say("Report file: %s" % R["report"])
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Kav1 DB diagnostics (read-only, backs up first)."
    )
    ap.add_argument("--db", help="path to local_database.db")
    ap.add_argument(
        "--no-write-test", action="store_true", help="skip the commit-latency test"
    )
    ap.add_argument(
        "--plain", action="store_true", help="no screen clearing and no pauses"
    )
    ap.add_argument(
        "--no-pause", action="store_true", help="do not wait for Enter at the end"
    )
    args = ap.parse_args()
    setup_console()
    global WIDTH
    WIDTH = max(78, min(100, shutil.get_terminal_size((100, 30)).columns - 1))
    code = 0
    try:
        code = run(args)
    except SystemExit as e:
        if e.code not in (0, None):
            say(str(e.code))
            code = 1
    except KeyboardInterrupt:
        say("\nStopped by user.")
        code = 1
    except Exception:
        say("\nUNEXPECTED ERROR - please photograph this screen:")
        say(traceback.format_exc())
        code = 1
    if interactive() and not args.plain and not args.no_pause:
        ask("\nPress Enter to close ...")
    sys.exit(code)


if __name__ == "__main__":
    main()
