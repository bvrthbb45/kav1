def test_panel_page_is_served(client):
    r = client.get("/panel")
    assert r.status_code == 200
    assert "אולימפוס" in r.text


def test_panel_status_without_usb(client):
    body = client.get("/api/panel/status").json()
    assert body["counts"]["items"] == 1
    assert body["counts"]["available"] == 1
    assert body["usb"]["enabled"] is False
    steps = body["usb"]["check"]["steps"]
    assert steps[0]["ok"] is True
    assert steps[-1]["ok"] is False and steps[-1]["detail"]
    assert any(e["message"] == "השרת הופעל ומחכה לטאבלטים" for e in body["events"])


def test_panel_data_names_holders(client):
    client.post(
        "/api/sync/push",
        json={
            "device_id": "dev-1",
            "transactions": [
                {
                    "tx_id": "t1",
                    "qr_id": "q1",
                    "user_id": "u1",
                    "action_type": "BORROW",
                    "timestamp": 1_700_000_000_000,
                }
            ],
        },
    )
    body = client.get("/api/panel/data").json()
    assert body["items"][0]["holder_name"] == "ישראל ישראלי"
    assert body["transactions"][0]["item_name"] == "מכשיר קשר"
    status = client.get("/api/panel/status").json()
    assert status["counts"]["borrowed"] == 1
    assert any(e["source"] == "network" for e in status["events"])


def test_panel_is_local_only(client):
    from fastapi.testclient import TestClient

    from app.main import app

    remote = TestClient(app, client=("10.0.0.5", 50000))
    r = remote.get("/api/panel/status")
    assert r.status_code == 403
    assert r.json()["message"] == "פאנל הבקרה זמין רק מהמחשב של השרת"
    # Tablets keep working from the network.
    assert remote.get("/api/health").status_code == 200


def test_panel_actions_without_usb(client):
    r = client.post("/api/panel/sync-now").json()
    assert r["success"] is False and r["message"]


def test_panel_logo_is_served(client):
    r = client.get("/panel/logo.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:4] == b"\x89PNG"
