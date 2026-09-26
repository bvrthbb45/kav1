import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WAREHOUSE_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    # Re-import with the temp database URL.
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        c.post(
            "/api/admin/users",
            json=[{"user_id": "u1", "full_name": "ישראל ישראלי", "unit": "א"}],
        )
        c.post("/api/admin/items", json=[{"qr_id": "q1", "name": "מכשיר קשר"}])
        yield c
