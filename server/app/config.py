"""Runtime configuration, overridable through environment variables."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

HOST = os.getenv("WAREHOUSE_HOST", "0.0.0.0")
PORT = int(os.getenv("WAREHOUSE_PORT", "8000"))
DATABASE_URL = os.getenv(
    "WAREHOUSE_DATABASE_URL", f"sqlite:///{BASE_DIR / 'warehouse.db'}"
)
