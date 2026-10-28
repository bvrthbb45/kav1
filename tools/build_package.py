#!/usr/bin/env python3
"""Assembles the final update package (a folder and a zip) from the original and the updated source trees.

  python build_package.py ORIG_KAV1_DIR NEW_KAV1_DIR OUT_DIR

ORIG / NEW are the project roots that contain backend/ and frontend/. The package contains:
  INSTALL.bat UNDO.bat DB_PORTABILITY.bat      one-click wrappers
  install_update.py code_patch.py db_portability.py   the tools (standalone, stdlib only)
  patches/        backend.patch.json, frontend.patch.json (checked: ORIG + patches == NEW)
  ready_files/    the finished files, to copy by hand over the source folder instead of using the installer
  docs/           maintenance guide, architecture, database schema, API list
  db_tools/       database diagnostic / fix / permission tools
  checksums.txt   SHA-256 of every file (the installer verifies it: catches damage during the transfer)
  README.txt
"""

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    orig, new, out = (Path(a).resolve() for a in sys.argv[1:4])
    if out.exists():
        shutil.rmtree(out)
    pkg = out / "kav1_update"
    (pkg / "patches").mkdir(parents=True)
    subprocess.run(
        [
            sys.executable,
            str(HERE / "make_tree_patch.py"),
            str(orig),
            str(new),
            str(pkg / "patches"),
        ],
        check=True,
    )
    for name in ("install_update.py", "code_patch.py", "db_portability.py"):
        shutil.copy2(HERE / name, pkg / name)
    for name in ("INSTALL.bat", "DRY_RUN.bat", "UNDO.bat", "DB_PORTABILITY.bat"):
        shutil.copy2(HERE / "windows" / name, pkg / name)

    # ready files + the table for the README
    rows = []
    for fname, base_back in (
        ("backend.patch.json", True),
        ("frontend.patch.json", False),
    ):
        data = json.loads((pkg / "patches" / fname).read_text(encoding="utf-8"))
        for f in data["files"]:
            p = f["path"]
            if base_back:
                rel = (
                    "backend/migrate_db.py"
                    if p == "../migrate_db.py"
                    else "backend/app/" + p
                )
            else:
                rel = "frontend/web/" + p
            dst = pkg / "ready_files" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(new / rel, dst)
            rows.append(
                (
                    rel.replace("/", "\\"),
                    "קובץ חדש" if "create" in f else "מחליף קובץ קיים",
                )
            )

    # docs + db tools
    shutil.copytree(REPO / "docs" / "package", pkg / "docs")
    tools = pkg / "db_tools"
    tools.mkdir()
    for n in (
        "diagnose_db.py",
        "fix_01_enable_wal.py",
        "fix_02_add_indexes.py",
        "fix_03_vacuum_analyze.py",
        "probe_server.py",
        "permissions_check.py",
        "permissions_restore.py",
        "permissions_watch.py",
        "code_locator.py",
    ):
        shutil.copy2(HERE / n, tools / n)
    for n in sorted((HERE / "windows").glob("[1-9]_*.bat")):
        if not n.name.startswith("10_"):
            shutil.copy2(n, tools / n.name)

    table = "\n".join("  %-48s %s" % row for row in rows)
    readme = (
        (HERE / "package_README.txt")
        .read_text(encoding="utf-8")
        .replace("{{FILES}}", table)
    )
    (pkg / "README.txt").write_bytes(
        ("﻿" + readme.replace("\n", "\r\n")).encode("utf-8")
    )

    # checksums (everything except the file itself)
    lines = []
    for p in sorted(pkg.rglob("*")):
        if p.is_file() and p.name != "checksums.txt":
            lines.append("%s  %s" % (sha(p), p.relative_to(pkg).as_posix()))
    (pkg / "checksums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    zpath = out / "kav1_update.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(pkg.rglob("*")):
            if p.is_file():
                z.write(p, "kav1_update/" + p.relative_to(pkg).as_posix())
    print("package:", zpath, "(%d files)" % len(list(pkg.rglob("*"))))


if __name__ == "__main__":
    main()
