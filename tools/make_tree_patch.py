#!/usr/bin/env python3
"""Builds *.patch.json files for tools/code_patch.py by comparing two source trees.

  python make_tree_patch.py ORIG_KAV1_DIR NEW_KAV1_DIR OUT_DIR

Both directories are the project root that contains backend/ and frontend/. Output:
  backend.patch.json   paths relative to backend/app   (backend/migrate_db.py becomes ../migrate_db.py)
  frontend.patch.json  paths relative to frontend/web
A changed file becomes a list of exact "old text -> new text" hunks (each old text occurs exactly once,
so a file that differs from the expected one is refused instead of damaged); a new file is embedded whole.
Self-check: every patch is applied to a copy of ORIG and the result must equal NEW byte for byte.
"""

import difflib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKIP_DIRS = {"__pycache__", "visitor_logs", ".git"}
SKIP_SUFFIX = {".pyc", ".bak", ".db", ".log", ".ico", ".png", ".spec"}


def read(path):
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def files_under(root):
    for p in sorted(root.rglob("*")):
        if (
            p.is_file()
            and not (set(p.relative_to(root).parts) & SKIP_DIRS)
            and p.suffix not in SKIP_SUFFIX
            and ".bak_" not in p.name
        ):
            yield p.relative_to(root)


def hunks(old_text, new_text):
    a, b = old_text.splitlines(True), new_text.splitlines(True)
    ops = [
        op
        for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
        if op[0] != "equal"
    ]
    groups = []
    for op in ops:  # merge changes that are close together
        if groups and op[1] - groups[-1][-1][2] <= 3:
            groups[-1].append(op)
        else:
            groups.append([op])
    out = []
    for g in groups:
        i1, i2, j1, j2 = g[0][1], g[-1][2], g[0][3], g[-1][4]
        ctx = 1
        while True:
            lo, hi = max(0, i1 - ctx), min(len(a), i2 + ctx)
            old = "".join(a[lo:hi])
            new = "".join(b[max(0, j1 - (i1 - lo)) : min(len(b), j2 + (hi - i2))])
            if old_text.count(old) == 1 or ctx > 30:
                break
            ctx += 1
        if old_text.count(old) != 1:
            raise SystemExit("cannot make a unique hunk")
        out.append({"old": old, "new": new})
    return out


def build(orig, new, prefix_map):
    entries = {k: [] for k in prefix_map}
    for rel in files_under(new):
        key = next(
            (
                k
                for k, (pre, _) in prefix_map.items()
                if str(rel).replace("\\", "/").startswith(pre)
            ),
            None,
        )
        if key is None:
            continue
        pre, base = prefix_map[key]
        sub = str(rel).replace("\\", "/")[len(pre) :]
        path = base + sub
        o = orig / rel
        if not o.exists():
            entries[key].append({"path": path, "create": read(new / rel)})
        elif read(o) != read(new / rel):
            entries[key].append(
                {"path": path, "replace": hunks(read(o), read(new / rel))}
            )
    return entries


def make_set(orig, new, out, suffix):
    """backend{suffix}.patch.json / frontend{suffix}.patch.json for orig -> new, self-checked."""
    pm_back = {
        "app": ("backend/app/", ""),
        "mig": ("backend/migrate_db.py", "../migrate_db.py"),
    }
    back = build(orig, new, pm_back)
    back_files = back["app"] + [dict(e, path="../migrate_db.py") for e in back["mig"]]
    front = build(orig, new, {"web": ("frontend/web/", "")})["web"]
    names = {
        "backend%s.patch.json"
        % suffix: (
            "Kav1 update: backend (permissions fix, database settings, visitor additions, optional features)",
            back_files,
        ),
        "frontend%s.patch.json"
        % suffix: (
            "Kav1 update: web pages (project, expiry and latest-entry additions, optional features)",
            front,
        ),
    }
    for fname, (title, files) in names.items():
        (out / fname).write_text(
            json.dumps({"name": title, "files": files}, ensure_ascii=False, indent=1)
            + "\n",
            encoding="utf-8",
        )
        print("wrote", out / fname, "(%d files)" % len(files))
    here = Path(__file__).resolve().parent
    tmp = Path(tempfile.mkdtemp())
    try:
        shutil.copytree(
            orig,
            tmp / "k",
            ignore=shutil.ignore_patterns(
                "__pycache__", "*.bak", "*.bak_*", "visitor_logs", "*.db*"
            ),
        )
        pairs = (
            ("backend%s.patch.json" % suffix, tmp / "k/backend/app"),
            ("frontend%s.patch.json" % suffix, tmp / "k/frontend/web"),
        )
        for fname, folder in pairs:
            r = subprocess.run(
                [
                    sys.executable,
                    str(here / "code_patch.py"),
                    "--patch",
                    str(out / fname),
                    "--folder",
                    str(folder),
                    "--yes",
                    "--plain",
                    "--no-pause",
                ],
                capture_output=True,
                text=True,
            )
            if r.returncode != 0:
                raise SystemExit(
                    "self-check: patch did not apply\n" + r.stdout + r.stderr
                )
        bad = []
        for rel in files_under(new):
            t = tmp / "k" / rel
            if not t.exists() or read(t) != read(new / rel):
                bad.append(str(rel))
        for fname, folder in pairs:
            r = subprocess.run(
                [
                    sys.executable,
                    str(here / "code_patch.py"),
                    "--patch",
                    str(out / fname),
                    "--folder",
                    str(folder),
                    "--yes",
                    "--plain",
                    "--no-pause",
                ],
                capture_output=True,
                text=True,
            )
            if "Everything is already patched" not in r.stdout:
                bad.append("not idempotent: " + fname)
        if bad:
            raise SystemExit("self-check FAILED: " + ", ".join(bad))
        print(
            "self-check ok (%s): applying the patches gives NEW byte for byte, a second run changes nothing"
            % (suffix or "orig")
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    orig, new, out = (Path(x).resolve() for x in sys.argv[1:4])
    out.mkdir(parents=True, exist_ok=True)
    make_set(orig, new, out, "")
    if (
        len(sys.argv) > 4
    ):  # an earlier version of the update that may already be installed
        make_set(Path(sys.argv[4]).resolve(), new, out, ".upgrade")


if __name__ == "__main__":
    main()
