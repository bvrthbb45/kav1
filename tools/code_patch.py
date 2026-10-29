#!/usr/bin/env python3
"""Kav1 - safe code patcher (standalone, stdlib only, Python 3.8+).

Applies a small, reviewed text patch to the server's source files in ONE run, with a
backup, a preview and automatic undo. Built for a machine where only small files can be
brought in: the patch is a tiny .json file of exact "old text -> new text" replacements.

  python code_patch.py --patch fix_permissions.patch.json --folder C:\\path\\backend\\app
  python code_patch.py --patch fix_permissions.patch.json --check    # only verify it applies
  python code_patch.py --patch fix_permissions.patch.json --revert   # put the backups back

What it guarantees:
  * every "old" text must be found EXACTLY the expected number of times (default 1);
    otherwise NOTHING is changed (it means your file differs from the one the patch was
    written for);
  * idempotent: if the new text is already in place the file is reported as "already patched";
  * a backup copy  <file>.bak_<time>  is made before the first change of each file;
  * after writing, each changed .py file is syntax-checked; on an error ALL files are
    restored from their backups at once;
  * line endings (CRLF / LF) and file encoding are preserved;
  * shows the exact lines that change and asks for confirmation (Y) before writing.
The server must be restarted afterwards for a code change to take effect.

Patch file format (UTF-8 JSON):
  {"name": "short title",
   "files": [{"path": "seed.py",
              "replace": [{"old": "exact old text", "new": "replacement", "expect": 1}]}]}
"""

import argparse
import ast
import difflib
import json
import os
import shutil
import sys
import textwrap
import time
import traceback
from datetime import datetime
from pathlib import Path

TOOL_VERSION = "1.0"
WIDTH = 100


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
# patcher
# =============================================================================
def read_text(path):
    """(text, encoding, newline) of a source file; line endings are normalised to \\n."""
    raw = path.read_bytes()
    enc = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
    try:
        text = raw.decode(enc)
    except UnicodeDecodeError:
        enc = "cp1255"
        text = raw.decode(enc)
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), enc, newline


def write_text(path, text, enc, newline):
    path.write_bytes(text.replace("\n", newline).encode(enc))


def plan_file(path, replaces):
    """(new_text, status, problems, hunks) for one file. Nothing is written here."""
    text, enc, newline = read_text(path)
    problems, hunks, status = [], [], "will change"
    new_text = text
    applied = 0
    for r in replaces:
        old = r["old"].replace("\r\n", "\n")
        new = r["new"].replace("\r\n", "\n")
        expect = int(r.get("expect", 1))
        found = new_text.count(old)
        if old in new and new_text.count(new) >= 1:
            continue  # the new text contains the old one and is already in place
        if found == expect:
            new_text = new_text.replace(old, new)
            applied += 1
            hunks.append((old, new))
        elif found == 0 and new and new_text.count(new) >= 1:
            continue  # already in place
        else:
            problems.append(
                "expected the old text %d time(s) but found %d: %s"
                % (expect, found, disp(old.strip().split("\n")[0])[:60])
            )
    if not problems and applied == 0:
        status = "already patched"
    return new_text, enc, newline, status, problems, hunks


def show_diff(path, old_text, new_text):
    lines = list(
        difflib.unified_diff(
            old_text.split("\n"),
            new_text.split("\n"),
            "before",
            "after",
            n=2,
            lineterm="",
        )
    )
    out = []
    for ln in lines[:60]:
        out.append(disp(ln)[: WIDTH - 2])
    if len(lines) > 60:
        out.append("... (%d more diff lines)" % (len(lines) - 60))
    return out


def latest_backups(folder, rel_paths):
    found = {}
    for rel in rel_paths:
        target = folder / rel
        cands = sorted(target.parent.glob(target.name + ".bak_*"))
        if cands:
            found[rel] = cands[-1]
    return found


def run(args):
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    say("Kav1 code patcher v%s - %s" % (TOOL_VERSION, generated))
    try:
        spec = json.loads(
            Path(clean_dropped(args.patch)).read_text(encoding="utf-8-sig")
        )
        files = spec["files"]
    except (OSError, ValueError, KeyError) as e:
        sys.exit("ERROR: cannot read the patch file: %s" % e)
    say("Patch: %s" % disp(spec.get("name", "(unnamed)")))
    folder = (
        Path(clean_dropped(args.folder)).expanduser().resolve() if args.folder else None
    )
    if folder is None:
        say("")
        say(
            "Drag the server's 'app' folder (the one with seed.py) into THIS window, then Enter."
        )
        typed = ask("> ")
        if not typed:
            sys.exit("Stopped: no folder selected.")
        folder = Path(clean_dropped(typed)).expanduser().resolve()
    if not folder.is_dir():
        sys.exit("Not a folder: %s" % folder)
    say("Folder: %s" % folder)
    rels = [f["path"] for f in files]

    if args.revert:
        backs = latest_backups(folder, rels)
        if not backs:
            sys.exit("No backups (.bak_*) found for this patch - nothing to revert.")
        for rel, b in backs.items():
            shutil.copy2(str(b), str(folder / rel))
            say("restored %s from %s" % (rel, b.name))
        say("Reverted. Restart the server.")
        return 0

    plans, bad = {}, False
    for f in files:
        path = folder / f["path"]
        if "create" in f:  # whole new file (or an update of a file this patch owns)
            content = f["create"].replace("\r\n", "\n")
            before = read_text(path)[0] if path.is_file() else ""
            if path.is_file():
                status = "already patched" if before == content else "will change"
            else:
                status = "will create"
            plans[f["path"]] = (path, before, content, "utf-8", "\n", status, [])
            say("  %-24s %s" % (f["path"], status.upper()))
            continue
        if not path.is_file():
            say("  %-24s FILE NOT FOUND" % f["path"])
            bad = True
            continue
        before_text = read_text(path)[0]
        new_text, enc, newline, status, problems, hunks = plan_file(path, f["replace"])
        plans[f["path"]] = (path, before_text, new_text, enc, newline, status, problems)
        say(
            "  %-24s %s"
            % (f["path"], status.upper() if not problems else "CANNOT APPLY")
        )
        for p in problems:
            say("      ! " + p)
            bad = True
    if bad:
        sys.exit(
            "\nNothing was changed: the files do not match what this patch expects.\n"
            "Send me a photo of this screen and of the lines around the place to change."
        )
    changing = {
        k: v for k, v in plans.items() if v[5] in ("will change", "will create")
    }
    for rel, (path, bt, nt, *_rest) in changing.items():
        say("")
        say("--- changes in %s ---" % rel)
        for ln in show_diff(path, bt, nt):
            say(ln)
    if not changing:
        say("")
        say("Everything is already patched - nothing to do.")
        return 0
    if args.check:
        say("")
        say("CHECK OK: the patch applies cleanly to %d file(s)." % len(changing))
        return 0
    if interactive() and not args.yes:
        say("")
        if (
            ask("Apply these changes now? (backups are made first)  Type Y: ").lower()
            != "y"
        ):
            sys.exit("Cancelled - nothing was changed.")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backups, created = {}, []
    try:
        for rel, (path, bt, nt, enc, newline, *_r) in changing.items():
            if not path.is_file():
                continue  # a new file: nothing to back up
            b = path.with_name(path.name + ".bak_" + stamp)
            shutil.copy2(str(path), str(b))
            backups[rel] = (path, b)
        for rel, (path, bt, nt, enc, newline, *_r) in changing.items():
            if not path.is_file():
                created.append(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            write_text(path, nt, enc, newline)
            if path.suffix == ".py":
                ast.parse(read_text(path)[0], str(path))
    except Exception as e:
        for rel, (path, b) in backups.items():
            shutil.copy2(str(b), str(path))
        for path in created:
            try:
                path.unlink()
            except OSError:
                pass
        sys.exit(
            "ERROR: %s\nAll files were restored from their backups. Nothing is changed."
            % e
        )
    say("")
    say(bar("-"))
    for rel in changing:
        b = backups.get(rel, (None, None))[1]
        say("patched %s   (backup: %s)" % (rel, b.name if b else "none - new file"))
    say(
        "DONE. Syntax check passed. RESTART the Kav1 server for the change to take effect."
    )
    say("To undo: run this tool again with --revert.")
    say(bar("-"))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Apply a reviewed text patch with backup and undo."
    )
    ap.add_argument("--patch", required=True, help="the .patch.json file")
    ap.add_argument(
        "--folder", help="folder the patch paths are relative to (the app folder)"
    )
    ap.add_argument(
        "--check", action="store_true", help="only verify the patch applies"
    )
    ap.add_argument("--revert", action="store_true", help="restore the latest backups")
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    ap.add_argument(
        "--no-pause", action="store_true", help="do not wait for Enter at the end"
    )
    ap.add_argument("--plain", action="store_true", help="no pauses")
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
    except Exception:
        say("\nUNEXPECTED ERROR - please photograph this screen:")
        say(traceback.format_exc())
        code = 1
    if interactive() and not args.plain and not args.no_pause:
        ask("\nPress Enter to close ...")
    sys.exit(code)


if __name__ == "__main__":
    main()
