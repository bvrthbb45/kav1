#!/usr/bin/env python3
"""Builds tools/patches/locations_feature.patch.json from backend/production_modules/locations.

The patch creates app/routes_locations.py and wires it into app/main.py (3 small, exact edits).
locations.html is a static page: copy it by hand into the folder the server prints as
"Serving web frontend from: ...". Re-run this script after editing the module.
"""

import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
src = root / "backend" / "production_modules" / "locations"
patch = {
    "name": "Optional feature: control & locations (maps, escorts, group-by-project switch)",
    "files": [
        {
            "path": "routes_locations.py",
            "create": (src / "routes_locations.py").read_text(encoding="utf-8"),
        },
        {
            "path": "main.py",
            "replace": [
                {
                    "old": "from .seed import run_seed",
                    "new": "from .routes_locations import router as locations_router, ensure_locations_permissions\nfrom .seed import run_seed",
                },
                {
                    "old": "run_seed(db)",
                    "new": "run_seed(db); ensure_locations_permissions(db)",
                },
                {
                    "old": "app.include_router(visitor_router)",
                    "new": "app.include_router(visitor_router); app.include_router(locations_router)",
                },
            ],
        },
    ],
}
out = root / "tools" / "patches" / "locations_feature.patch.json"
out.write_text(json.dumps(patch, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("wrote", out)
