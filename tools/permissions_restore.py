#!/usr/bin/env python3
"""Kav1 - restore lost role permissions (standalone, stdlib only, Python 3.8+).

Problem it solves: after a server restart some role-permission links disappear (for
example CISO 21 -> 12 and the controller role 3 -> 2). This tool puts the lost links
back, in ONE run, from a saved snapshot that was taken while the permissions were right
(the snapshots written by permissions_check.py, or a baseline you saved with
--save-baseline).

Safety:
  * makes a verified backup of the database first (only when something has to change);
  * ONLY ADDS missing role-permission links (INSERT OR IGNORE). It never deletes or
    changes anything else, never touches users, passwords, visitors or settings;
  * idempotent: run it twice and the second run changes nothing;
  * skips a role whose id/name no longer matches the snapshot and permission keys that no
    longer exist, and tells you;
  * shows exactly what it will add and asks for confirmation (Y) before writing;
  * verifies integrity and the result afterwards.
Safe to run while the server is running (a short write); stopping it first is cleaner.

NOTE: this repairs the damage. It does not stop the server from removing the permissions
again at the next restart - that needs the code fix. Until then run this tool after
every restart (and then check the roles again with permissions_check.py).

Usage:
  python permissions_restore.py                      # drag the database in, pick the baseline, confirm
  python permissions_restore.py --db C:\\path\\local_database.db --yes
  python permissions_restore.py --check              # only compare with the baseline (exit 1 if different)
  python permissions_restore.py --save-baseline      # make the CURRENT permissions the baseline
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import textwrap
import time
import traceback
from datetime import datetime
from pathlib import Path

TOOL_VERSION = "1.0"
DB_NAME = "local_database.db"
WIDTH = 100
SEARCH_BUDGET_S = 25
BASELINE_NAME = "permissions_baseline.json"


# =============================================================================
# shared helpers (same code as the other tools: each tool is standalone)
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
        "%s.pre-permrestore.%s.db" % (db.stem, datetime.now().strftime("%Y%m%d_%H%M%S"))
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


# =============================================================================
# screens (pages) - every page is built to fit one console window
# =============================================================================
def wrap(text, indent="", first=""):
    return textwrap.wrap(
        text, WIDTH, initial_indent=first, subsequent_indent=indent
    ) or [""]


def bar(char="="):
    return char * WIDTH


# =============================================================================
# permissions
# =============================================================================
def table_rows(con, sql):
    try:
        return con.execute(sql).fetchall()
    except sqlite3.Error:
        return None


def collect(con):
    R = {}
    tables = set(user_tables(con))
    R["tables"] = tables
    need = {"roles", "permissions", "role_permissions"}
    R["missing_tables"] = sorted(need - tables)
    if R["missing_tables"]:
        return R
    cols = {t: [r[1] for r in con.execute("PRAGMA table_info('%s')" % t)] for t in need}
    R["columns"] = cols
    rid = "id" if "id" in cols["roles"] else cols["roles"][0]
    rname = "name" if "name" in cols["roles"] else cols["roles"][1]
    pkey = "key" if "key" in cols["permissions"] else cols["permissions"][0]
    rp_role = (
        "role_id"
        if "role_id" in cols["role_permissions"]
        else cols["role_permissions"][0]
    )
    rp_perm = (
        "permission_key"
        if "permission_key" in cols["role_permissions"]
        else cols["role_permissions"][1]
    )
    protected = "is_protected" if "is_protected" in cols["roles"] else None
    roles = {}
    for row in con.execute(
        'SELECT "%s", "%s"%s FROM roles ORDER BY "%s"'
        % (rid, rname, (', "%s"' % protected) if protected else "", rid)
    ):
        roles[row[0]] = {
            "name": str(row[1]),
            "protected": bool(row[2]) if protected else None,
            "perms": [],
        }
    R["all_perms"] = sorted(
        str(r[0]) for r in con.execute('SELECT "%s" FROM permissions' % pkey)
    )
    R["orphan_links"] = 0
    perm_set = set(R["all_perms"])
    R["unknown_perm_links"] = 0
    for role_id, perm in con.execute(
        'SELECT "%s", "%s" FROM role_permissions' % (rp_role, rp_perm)
    ):
        if role_id not in roles:
            R["orphan_links"] += 1
            continue
        roles[role_id]["perms"].append(str(perm))
        if str(perm) not in perm_set:
            R["unknown_perm_links"] += 1
    for r in roles.values():
        r["perms"] = sorted(set(r["perms"]))
    R["roles"] = roles
    # users per role (counts only)
    R["users_per_role"] = {}
    if "users" in tables:
        ucols = [r[1] for r in con.execute("PRAGMA table_info('users')")]
        if "role_id" in ucols:
            for role_id, n in con.execute(
                "SELECT role_id, COUNT(*) FROM users GROUP BY role_id"
            ):
                R["users_per_role"][role_id] = n
    # settings: keys + timestamps only (never values)
    R["settings"] = {}
    if "settings" in tables:
        scols = [r[1] for r in con.execute("PRAGMA table_info('settings')")]
        upd = "updated_at" if "updated_at" in scols else None
        for row in con.execute(
            'SELECT "key"%s FROM settings' % ((', "%s"' % upd) if upd else "")
        ):
            R["settings"][str(row[0])] = str(row[1]) if upd else ""
    # audit log: action names + timestamps (no usernames / details except for role/permission actions)
    R["audit"] = {"total": 0, "last_id": 0, "recent": [], "actions": {}}
    if "audit_logs" in tables:
        acols = [r[1] for r in con.execute("PRAGMA table_info('audit_logs')")]
        R["audit"]["total"], R["audit"]["last_id"] = con.execute(
            "SELECT COUNT(*), COALESCE(MAX(id),0) FROM audit_logs"
        ).fetchone()
        if "action" in acols:
            R["audit"]["actions"] = dict(
                con.execute(
                    "SELECT action, COUNT(*) FROM audit_logs GROUP BY action ORDER BY 2 DESC LIMIT 12"
                ).fetchall()
            )
            sel = "id, timestamp, action" + (
                ", detail" if "detail" in acols else ", ''"
            )
            for i, ts, action, detail in con.execute(
                "SELECT %s FROM audit_logs ORDER BY id DESC LIMIT 400" % sel
            ):
                R["audit"]["recent"].append(
                    {
                        "id": i,
                        "ts": str(ts),
                        "action": str(action),
                        "detail": str(detail or ""),
                    }
                )
    return R


def snapshot_of(R):
    return {
        "taken": datetime.now().isoformat(timespec="seconds"),
        "roles": {
            str(k): {"name": v["name"], "perms": v["perms"]}
            for k, v in R["roles"].items()
        },
        "all_perms": R["all_perms"],
        "settings": R["settings"],
        "audit_last_id": R["audit"]["last_id"],
    }


def previous_snapshot(ddir, current_name):
    files = sorted(ddir.glob("permissions_snapshot_*.json"))
    files = [f for f in files if f.name != current_name]
    if not files:
        return None, None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8")), files[-1]
    except (OSError, ValueError):
        return None, None


def compare(prev, cur):
    changes = {
        "roles": [],
        "role_added": [],
        "role_removed": [],
        "perm_table_added": [],
        "perm_table_removed": [],
        "settings": [],
    }
    for rid, now in cur["roles"].items():
        before = prev["roles"].get(rid)
        if before is None:
            changes["role_added"].append(now["name"])
            continue
        lost = sorted(set(before["perms"]) - set(now["perms"]))
        gained = sorted(set(now["perms"]) - set(before["perms"]))
        if lost or gained:
            changes["roles"].append(
                {
                    "name": now["name"],
                    "before": len(before["perms"]),
                    "after": len(now["perms"]),
                    "lost": lost,
                    "gained": gained,
                }
            )
    for rid, before in prev["roles"].items():
        if rid not in cur["roles"]:
            changes["role_removed"].append(before["name"])
    changes["perm_table_added"] = sorted(set(cur["all_perms"]) - set(prev["all_perms"]))
    changes["perm_table_removed"] = sorted(
        set(prev["all_perms"]) - set(cur["all_perms"])
    )
    for k, v in cur["settings"].items():
        if k not in prev["settings"]:
            changes["settings"].append("%s: NEW" % k)
        elif prev["settings"][k] != v:
            changes["settings"].append(
                "%s: updated %s -> %s" % (k, prev["settings"][k][:19], v[:19])
            )
    for k in prev["settings"]:
        if k not in cur["settings"]:
            changes["settings"].append("%s: REMOVED" % k)
    return changes


# =============================================================================
# restore logic
# =============================================================================
def link_columns(con):
    cols = [r[1] for r in con.execute("PRAGMA table_info('role_permissions')")]
    role_col = "role_id" if "role_id" in cols else cols[0]
    perm_col = "permission_key" if "permission_key" in cols else cols[1]
    return role_col, perm_col


def list_baselines(ddir):
    """[(path, data)] newest first. The saved baseline (if any) comes first."""
    found = []
    for p in sorted(ddir.glob("permissions_snapshot_*.json"), reverse=True):
        try:
            found.append((p, json.loads(p.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    base = ddir / BASELINE_NAME
    if base.exists():
        try:
            found.insert(0, (base, json.loads(base.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            pass
    return found


def links_in(data):
    return sum(len(r["perms"]) for r in data["roles"].values())


def make_plan(baseline, R):
    """What to add: [(role_id, role_name, key)], plus notes for what was skipped."""
    adds, notes = [], []
    known = set(R["all_perms"])
    for rid, b in baseline["roles"].items():
        cur = R["roles"].get(int(rid)) if str(rid).isdigit() else None
        if cur is None:
            notes.append(
                "role %s (id %s) no longer exists - skipped" % (disp(b["name"]), rid)
            )
            continue
        if cur["name"] != b["name"]:
            notes.append(
                "role id %s was %s, now %s - skipped"
                % (rid, disp(b["name"]), disp(cur["name"]))
            )
            continue
        for key in sorted(set(b["perms"]) - set(cur["perms"])):
            if key not in known:
                notes.append("permission %s no longer exists - skipped" % key)
            else:
                adds.append((int(rid), cur["name"], key))
    return adds, notes


def choose_baseline(ddir, db):
    cands = list_baselines(ddir)
    if not cands:
        sys.exit(
            "No saved snapshot found in %s.\nRun permissions_check.py once while the permissions "
            "are correct (before a restart), or restore them by hand once and use --save-baseline."
            % ddir
        )
    if cands[0][0].name == BASELINE_NAME:  # a baseline you saved on purpose wins
        best = 0
    else:
        best = max(range(len(cands)), key=lambda i: (links_in(cands[i][1]), -i))
    if not interactive() or len(cands) == 1:
        return cands[best]
    say("")
    say(
        "Saved states of the permissions (the tool restores what is MISSING compared to one of them):"
    )
    for i, (p, d) in enumerate(cands, 1):
        say(
            "  %d) %s   taken %s   %d links%s%s"
            % (
                i,
                "BASELINE" if p.name == BASELINE_NAME else "snapshot",
                d.get("taken", "?").replace("T", " "),
                links_in(d),
                "   <- suggested" if i - 1 == best else "",
                "",
            )
        )
    choice = ask(
        "Which state is the CORRECT one? number [%d]: " % (best + 1), str(best + 1)
    )
    try:
        return cands[int(choice) - 1]
    except (ValueError, IndexError):
        sys.exit("Invalid choice.")


def show_plan(R, baseline_taken, adds, notes):
    per_role = {}
    for rid, name, key in adds:
        per_role.setdefault((rid, name), []).append(key)
    L = []
    L.append("State used as the reference: taken %s" % baseline_taken.replace("T", " "))
    L.append("")
    L.append("%-26s %12s %10s" % ("ROLE", "NOW HAS", "TO ADD"))
    L.append(bar("-"))
    for rid, r in R["roles"].items():
        L.append(
            "%-26s %6d of %-3d %10d"
            % (
                disp(r["name"])[:26],
                len(r["perms"]),
                len(R["all_perms"]),
                len(per_role.get((rid, r["name"]), [])),
            )
        )
    L.append(bar("-"))
    L.append("Total links to add: %d" % len(adds))
    for (rid, name), keys in per_role.items():
        L += wrap("  + %s: %s" % (disp(name), ", ".join(keys)), indent="      ")
    for n in list(dict.fromkeys(notes))[:6]:
        L += wrap("  ! " + n, indent="      ")
    for line in L:
        say(line)


def apply_adds(db, adds):
    con = sqlite3.connect(str(db), timeout=30)
    try:
        role_col, perm_col = link_columns(con)
        con.execute("BEGIN IMMEDIATE")
        before = con.execute("SELECT COUNT(*) FROM role_permissions").fetchone()[0]
        for rid, _, key in adds:
            con.execute(
                'INSERT OR IGNORE INTO role_permissions ("%s", "%s") VALUES (?, ?)'
                % (role_col, perm_col),
                (rid, key),
            )
        con.commit()
        after = con.execute("SELECT COUNT(*) FROM role_permissions").fetchone()[0]
        return before, after
    except sqlite3.OperationalError as e:
        try:
            con.rollback()
        except sqlite3.Error:
            pass
        raise RuntimeError(
            "could not write (%s). Nothing was changed. Stop the Kav1 server and run again."
            % e
        )
    finally:
        con.close()


def read_state(db):
    con = connect(db, readonly=True)
    try:
        R = collect(con)
    finally:
        con.close()
    return R


def run(args):
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    say("Kav1 permissions restore v%s - %s" % (TOOL_VERSION, generated))
    db = find_db(args.db)
    say("Database: %s" % db)
    why = []
    ok, _ = looks_like_kav1(db, timeout=20, error=why)
    if not ok:
        sys.exit("ERROR: cannot use %s: %s" % (db, why[0] if why else "unknown"))
    R = read_state(db)
    if R["missing_tables"]:
        sys.exit(
            "This database has no table(s): %s - nothing to do."
            % ", ".join(R["missing_tables"])
        )
    ddir = db.parent / "diagnostics"
    ddir.mkdir(exist_ok=True)

    if args.save_baseline:
        snap = snapshot_of(R)
        path = ddir / BASELINE_NAME
        if interactive() and not args.yes:
            say(
                "This will save the CURRENT permissions (%d links) as the baseline to restore from."
                % links_in(snap)
            )
            if ask("Type Y to save: ").lower() != "y":
                sys.exit("Cancelled.")
        path.write_text(
            json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        say("Baseline saved: %s" % path)
        return 0

    path, baseline = choose_baseline(ddir, db)
    adds, notes = make_plan(baseline, R)
    show_plan(R, baseline.get("taken", "?"), adds, notes)
    if args.check:
        say("")
        say(
            "CHECK: %s"
            % (
                "permissions DIFFER from the reference (%d missing)" % len(adds)
                if adds
                else "permissions match the reference (nothing missing)"
            )
        )
        return 1 if adds else 0
    if not adds:
        say("")
        say("Nothing to restore - no backup made, nothing changed.")
        return 0
    if interactive() and not args.yes:
        say("")
        if (
            ask(
                "Add these %d links now? (a verified backup is made first)  Type Y: "
                % len(adds)
            ).lower()
            != "y"
        ):
            sys.exit("Cancelled - nothing was changed.")
    say("")
    say("[1/3] Backing up the database (verified) ...")
    try:
        backup = make_backup(db)
    except Exception as e:
        sys.exit("ERROR: backup failed, nothing was changed: %s" % e)
    say("      OK: %s" % backup)
    say("[2/3] Restoring ...")
    try:
        before, after = apply_adds(db, adds)
    except RuntimeError as e:
        sys.exit("ERROR: %s" % e)
    say("      links %d -> %d" % (before, after))
    say("[3/3] Verifying ...")
    con = connect(db, readonly=True)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()
    R2 = read_state(db)
    still = make_plan(baseline, R2)[0]
    snap = snapshot_of(R2)
    name = "permissions_snapshot_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S")
    (ddir / name).write_text(
        json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    say(
        "      integrity_check=%s | still missing: %d | new snapshot: %s"
        % (integrity, len(still), name)
    )
    say("")
    say(bar("-"))
    if integrity == "ok" and not still:
        say("DONE: %d permission links restored." % len(adds))
    else:
        say(
            "WARNING: the result does not match - restore the backup above and tell the developer."
        )
    say(
        "Remember: until the code fix, the server may remove them again at the next restart."
    )
    say(bar("-"))
    return 0 if integrity == "ok" and not still else 2


def main():
    ap = argparse.ArgumentParser(
        description="Restore lost role-permission links (adds only, backup first)."
    )
    ap.add_argument("--db", help="path to local_database.db")
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    ap.add_argument(
        "--check", action="store_true", help="only compare with the reference state"
    )
    ap.add_argument(
        "--save-baseline",
        action="store_true",
        help="save the current permissions as the baseline",
    )
    ap.add_argument("--plain", action="store_true", help="no pauses")
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
