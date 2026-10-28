#!/usr/bin/env python3
"""Generates the API table (route, method, required permission) from the backend source files.

  python make_api_doc.py BACKEND_APP_DIR > API_ENDPOINTS.md
Reads routes*.py (and routes_locations.py / visitor_extras.py) as text: no imports, no database.
"""

import re
import sys
from pathlib import Path


def balanced(text, start):
    depth, i = 0, start
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    return text[start:]


def main():
    app = Path(sys.argv[1])
    rows = []
    for f in sorted(app.glob("routes*.py")) + sorted(app.glob("visitor_extras.py")):
        src = f.read_text(encoding="utf-8")
        m = re.search(r"APIRouter\(([^)]*)\)", src)
        prefix = ""
        if m:
            p = re.search(r'prefix\s*=\s*"([^"]*)"', m.group(1))
            prefix = p.group(1) if p else ""
        for d in re.finditer(r"@router\.(get|post|put|delete|websocket)\(", src):
            call = balanced(src, d.end() - 1)
            path = re.search(r'"([^"]*)"', call)
            perms = re.findall(r"require_(?:any_)?permission\(([^)]*)\)", call)
            keys = sorted({k for p in perms for k in re.findall(r'"([^"]+)"', p)})
            after = src[d.end() + len(call) - 1 :]
            fn = re.search(r"def\s+(\w+)", after)
            doc = re.search(
                r'"""(.*?)"""',
                after[: after.find("\n\n\n") if "\n\n\n" in after else 800],
                re.S,
            )
            rows.append(
                (
                    prefix + (path.group(1) if path else ""),
                    d.group(1).upper(),
                    keys,
                    f.name,
                    fn.group(1) if fn else "",
                    (doc.group(1).strip().splitlines()[0] if doc else ""),
                )
            )
    print("# API endpoints\n")
    print(
        "Generated from the source by `tools/make_api_doc.py`. A request needs a logged-in session (cookie `kav1_session`);"
    )
    print(
        "the permission column is what the role must hold (`or` = any one of them). `-` means: logged in is enough, or public (login, branding).\n"
    )
    print("| Method | Path | Permission | File | What |")
    print("|---|---|---|---|---|")
    for path, method, keys, fname, fn, doc in sorted(rows):
        print(
            "| %s | `%s` | %s | %s | %s |"
            % (
                method,
                path,
                " or ".join("`%s`" % k for k in keys) or "-",
                fname,
                doc.replace("|", "/"),
            )
        )


if __name__ == "__main__":
    main()
