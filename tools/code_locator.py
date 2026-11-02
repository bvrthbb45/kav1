#!/usr/bin/env python3
"""Kav1 - code locator / viewer (standalone, stdlib only, Python 3.8+). READ-ONLY.

For when the server code cannot leave the closed network: it finds WHERE in the
server's source folder the code touches roles / permissions / start-up seeding and
shows only those lines, as photo-friendly console pages. It can also show a chosen
line range of one file.

  python code_locator.py                              # drag the server folder in
  python code_locator.py --folder C:\\path\\backend  --pattern seed --pattern lifespan
  python code_locator.py --preset fields              # where contractor fields are defined
  python code_locator.py --show app\\main.py:1-60       # show lines 1-60 of a file

Lines that look like they hold a password / secret / token are NEVER printed (replaced
by a marker). Hebrew is printed as Latin transliteration (H:...). Nothing is modified.
"""

import argparse
import os
import re
import shutil
import sys
import textwrap
import time
import traceback
from datetime import datetime
from pathlib import Path

TOOL_VERSION = "1.0"
WIDTH = 100
DB_NAME = "local_database.db"
SEARCH_BUDGET_S = 25

SECRET_RE = re.compile(
    r"(passw|secret|token|api[_-]?key|private[_-]?key|credential)", re.I
)
# Words that point at permission handling and start-up seeding
CORE = ["role_permissions", "RolePermission", "is_protected", "permissions"]
SEED = [
    "seed",
    "default_roles",
    "default_perm",
    "DEFAULT_ROLE",
    "DEFAULT_PERM",
    "bootstrap",
    "ensure_",
    "init_db",
    "startup",
    "lifespan",
    "on_event",
    "create_all",
]
RISKY = [
    "DELETE FROM",
    ".delete(",
    "drop_all",
    "INSERT OR REPLACE",
    "merge(",
    "truncate",
    "role_permissions.clear",
    "perms = ",
    ".permissions = ",
]
SKIP_DIRS = {
    "venv",
    ".venv",
    "node_modules",
    "__pycache__",
    ".git",
    "site-packages",
    "dist",
    "build",
    "backups",
    "diagnostics",
    "visitor_logs",
    "wheels",
    ".idea",
    ".vscode",
}
EXTS = (".py", ".html", ".js")
MAX_FILE_BYTES = 400_000  # skips minified libraries (alpine.min.js, tailwind, ...)

# --preset fields: where the app defines / validates contractor fields (UI + API)
PRESET_FIELDS = {
    "CORE": ["שינוי שם", "איחוד", "אבטחת מידע", "rename", "merge", "/fields", "field_"],
    "SEED": ["properties", "x-data", "fetch(", "@router.", "@app."],
    "RISKY": ["validate", "required", "<select", "<option", "enum", "Literal"],
}


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
# locator
# =============================================================================
def clean_line(text):
    if SECRET_RE.search(text):
        return "<line hidden: looks sensitive>"
    return disp(text.rstrip())


def walk_sources(root, max_depth=7):
    base = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(str(root)):
        depth = len(Path(dirpath).parts) - base
        dirnames[:] = (
            [d for d in dirnames if d.lower() not in SKIP_DIRS]
            if depth < max_depth
            else []
        )
        for name in filenames:
            if name.lower().endswith(EXTS) and ".min." not in name.lower():
                path = Path(dirpath) / name
                try:
                    if path.stat().st_size > MAX_FILE_BYTES:
                        continue
                except OSError:
                    continue
                yield path


def read_lines(path):
    for enc in ("utf-8", "utf-8-sig", "cp1255", "latin-1"):
        try:
            return path.read_text(encoding=enc).splitlines()
        except (UnicodeDecodeError, OSError):
            continue
    return []


def analyse(root, extra_patterns):
    files = []
    words = CORE + SEED + RISKY + list(extra_patterns)
    for p in walk_sources(root):
        lines = read_lines(p)
        enclosing, hits = "", []
        for n, line in enumerate(lines, 1):
            m = re.match(r"\s*(?:async\s+)?(def|class)\s+(\w+)", line)
            if m:
                enclosing = m.group(2)
            low = line.lower()
            found = [w for w in words if w.lower() in low]
            if found and not line.strip().startswith("#"):
                hits.append({"n": n, "text": line, "in": enclosing, "words": found})
        core = sum(1 for h in hits if any(w in h["words"] for w in CORE[:6]))
        seed = sum(1 for h in hits if any(w in h["words"] for w in SEED))
        risky = sum(1 for h in hits if any(w in h["words"] for w in RISKY))
        score = core * 3 + seed * 2 + risky
        files.append(
            {
                "path": p,
                "lines": len(lines),
                "hits": hits,
                "score": score,
                "core": core,
                "seed": seed,
                "risky": risky,
                "entry": any("FastAPI(" in l or "uvicorn.run" in l for l in lines),
            }
        )
    return files


def rel(p, root):
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def page_structure(root, files):
    L = [
        "FOLDER: " + short_path(root, WIDTH - 10),
        "%d source files, %d lines in total"
        % (len(files), sum(f["lines"] for f in files)),
        "",
    ]
    L.append(
        "%-52s %6s %5s %5s %5s"
        % ("FILE (largest first)", "LINES", "CORE", "SEED", "RISKY")
    )
    L.append(bar("-"))
    for f in sorted(files, key=lambda f: -f["lines"])[:20]:
        L.append(
            "%-52s %6d %5d %5d %5d%s"
            % (
                disp(rel(f["path"], root))[:52],
                f["lines"],
                f["core"],
                f["seed"],
                f["risky"],
                "  <- entry" if f["entry"] else "",
            )
        )
    L += [
        "",
        "CORE = lines about role_permissions / is_protected; SEED = start-up / default-data",
        "words; RISKY = deletes / replaces. Files with the highest score come next.",
    ]
    return "SOURCE FILES", L


def page_hits(root, f, rank):
    L = [
        "%s   (score %d: core %d, seed %d, risky %d)"
        % (disp(rel(f["path"], root)), f["score"], f["core"], f["seed"], f["risky"]),
        "",
    ]
    shown = 0
    last_in = None
    for h in f["hits"]:
        if shown >= 34:
            L.append(
                "... %d more matching lines in this file (use --show to read them)"
                % (len(f["hits"]) - shown)
            )
            break
        if h["in"] != last_in:
            L.append("  [in %s]" % (disp(h["in"]) or "module level"))
            last_in = h["in"]
        L.append("   %4d: %s" % (h["n"], clean_line(h["text"]).strip()[: WIDTH - 12]))
        shown += 1
    return "LIKELY FILE %d" % rank, L


def page_show(path, a, b):
    lines = read_lines(path)
    L = [
        "%s  lines %d-%d of %d" % (disp(path.name), a, min(b, len(lines)), len(lines)),
        "",
    ]
    for n in range(a, min(b, len(lines)) + 1):
        L.append("%4d| %s" % (n, clean_line(lines[n - 1])[: WIDTH - 7]))
    return "CODE", L


def make_screens(pages, generated, lines_per_screen=None):
    rows = max(20, shutil.get_terminal_size((WIDTH, 30)).lines - 4)
    screens = []
    for title, lines in pages:
        lines = [x if len(x) <= WIDTH else x[: WIDTH - 1] + ">" for x in lines]
        size = rows - 3
        chunks = [lines[i : i + size] for i in range(0, max(len(lines), 1), size)] or [
            []
        ]
        for n, chunk in enumerate(chunks, 1):
            screens.append(
                (
                    title + ("" if len(chunks) == 1 else " (%d/%d)" % (n, len(chunks))),
                    chunk,
                )
            )
    out = []
    for i, (title, lines) in enumerate(screens, 1):
        out.append(
            [
                "KAV1 CODE LOCATOR v%s | %s | PAGE %d OF %d"
                % (TOOL_VERSION, generated, i, len(screens)),
                "== " + title + " " + "=" * max(3, WIDTH - len(title) - 4),
            ]
            + lines
        )
    return out


def show(screens, plain):
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
        say(">>> End (%d pages)." % len(screens))


def ask_folder():
    say("")
    say(
        "Drag the SERVER folder (the one that contains the 'app' folder, e.g. backend) into THIS"
    )
    say("window and press Enter.")
    while True:
        typed = ask("> ")
        if not typed:
            sys.exit("Stopped: no folder selected.")
        p = Path(clean_dropped(typed)).expanduser()
        if p.is_dir():
            return p.resolve()
        say("Not a folder: %s - drag the folder again." % p)


def run(args):
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    say("Kav1 code locator v%s - %s" % (TOOL_VERSION, generated))
    if args.show:
        m = re.match(r"^(.*):(\d+)-(\d+)$", args.show)
        if not m:
            sys.exit("--show needs  file:first-last  e.g. app\\main.py:1-60")
        path = Path(m.group(1)).expanduser()
        if not path.is_file():
            sys.exit("File not found: %s" % path)
        show(
            make_screens(
                [page_show(path, int(m.group(2)), int(m.group(3)))], generated
            ),
            args.plain,
        )
        return 0
    root = (
        Path(clean_dropped(args.folder)).expanduser().resolve()
        if args.folder
        else ask_folder()
    )
    if not root.is_dir():
        sys.exit("Not a folder: %s" % root)
    say("Reading source files ...")
    if args.preset == "fields":
        global CORE, SEED, RISKY
        CORE, SEED, RISKY = (PRESET_FIELDS[k] for k in ("CORE", "SEED", "RISKY"))
    files = analyse(root, args.pattern or [])
    if not files:
        sys.exit("No .py files found under %s" % root)
    pages = [page_structure(root, files)]
    ranked = [f for f in sorted(files, key=lambda f: -f["score"]) if f["score"] > 0][
        : args.top
    ]
    for i, f in enumerate(ranked, 1):
        pages.append(page_hits(root, f, i))
    if not ranked:
        pages.append(
            (
                "LIKELY FILES",
                [
                    "No file mentions roles / permissions / seeding words.",
                    "Try --pattern <word> with a word you expect to find.",
                ],
            )
        )
    show(make_screens(pages, generated), args.plain)
    return 0


def main():
    ap = argparse.ArgumentParser(description="Kav1 code locator (read-only).")
    ap.add_argument("--folder", help="server source folder (contains the app folder)")
    ap.add_argument(
        "--pattern", action="append", help="extra word to look for (repeatable)"
    )
    ap.add_argument(
        "--preset",
        choices=["permissions", "fields"],
        default="permissions",
        help="what to look for: permissions/seeding (default) or contractor fields",
    )
    ap.add_argument(
        "--top", type=int, default=3, help="how many likely files to show (default 3)"
    )
    ap.add_argument("--show", help="show lines of one file:  path:first-last")
    ap.add_argument("--plain", action="store_true", help="no screen clearing / pauses")
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
