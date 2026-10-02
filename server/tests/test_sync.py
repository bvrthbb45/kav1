def _tx(tx_id, action, ts, qr_id="q1", user_id="u1"):
    return {
        "tx_id": tx_id,
        "qr_id": qr_id,
        "user_id": user_id,
        "action_type": action,
        "timestamp": ts,
    }


def _status(client):
    items = client.get("/api/sync/pull").json()["items"]
    return {i["qr_id"]: i["current_status"] for i in items}


def test_pull_returns_state(client):
    body = client.get("/api/sync/pull").json()
    assert body["success"]
    assert body["message"] == "הנתונים נטענו בהצלחה"
    assert body["users"][0]["full_name"] == "ישראל ישראלי"
    assert body["items"][0]["current_status"] == "AVAILABLE"


def test_push_updates_status(client):
    r = client.post(
        "/api/sync/push", json={"transactions": [_tx("t1", "BORROW", 1000)]}
    )
    body = r.json()
    assert r.status_code == 200
    assert body["accepted"] == ["t1"]
    assert "בהצלחה" in body["message"]
    assert _status(client)["q1"] == "BORROWED"


def test_push_is_idempotent(client):
    payload = {"transactions": [_tx("t1", "BORROW", 1000)]}
    client.post("/api/sync/push", json=payload)
    body = client.post("/api/sync/push", json=payload).json()
    assert body["accepted"] == ["t1"]
    assert body["rejected"] == []


def test_late_older_action_does_not_override_newer(client):
    client.post("/api/sync/push", json={"transactions": [_tx("t2", "RETURN", 2000)]})
    client.post("/api/sync/push", json={"transactions": [_tx("t1", "BORROW", 1000)]})
    assert _status(client)["q1"] == "AVAILABLE"


def test_batch_applied_in_time_order(client):
    txs = [_tx("t2", "RETURN", 2000), _tx("t1", "BORROW", 1000)]
    client.post("/api/sync/push", json={"transactions": txs})
    assert _status(client)["q1"] == "AVAILABLE"


def test_invalid_transactions_rejected_in_hebrew(client):
    txs = [
        _tx("ok", "BORROW", 1000),
        _tx("bad-item", "BORROW", 1000, qr_id="nope"),
        _tx("bad-user", "BORROW", 1000, user_id="nope"),
        _tx("bad-action", "STEAL", 1000),
    ]
    body = client.post("/api/sync/push", json={"transactions": txs}).json()
    assert body["accepted"] == ["ok"]
    reasons = {r["tx_id"]: r["message"] for r in body["rejected"]}
    assert reasons["bad-item"] == "פריט לא קיים במערכת: nope"
    assert reasons["bad-user"] == "משתמש לא קיים במערכת: nope"
    assert reasons["bad-action"] == "סוג פעולה לא חוקי: STEAL"
    assert not body["success"]


def test_validation_error_is_hebrew(client):
    r = client.post("/api/sync/push", json={"foo": 1})
    assert r.status_code == 422
    assert r.json()["message"] == "הבקשה שנשלחה אינה תקינה"


def test_not_found_is_hebrew(client):
    r = client.get("/api/nothing")
    assert r.status_code == 404
    assert r.json()["message"] == "הכתובת המבוקשת לא נמצאה"


def test_db_error_rolls_back_whole_batch(client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app import services

    def boom(*_args, **_kwargs):
        raise OperationalError("stmt", {}, Exception("disk full"))

    monkeypatch.setattr(services, "_recompute_item_status", boom)
    r = client.post(
        "/api/sync/push", json={"transactions": [_tx("t1", "BORROW", 1000)]}
    )
    assert r.status_code == 500
    assert r.json()["message"].startswith("שגיאה בשמירת הנתונים")
    monkeypatch.undo()
    # Nothing from the failed batch was stored.
    body = client.post(
        "/api/sync/push", json={"transactions": [_tx("t1", "RETURN", 5000)]}
    ).json()
    assert body["accepted"] == ["t1"]
    assert _status(client)["q1"] == "AVAILABLE"


def test_issue_sets_issued_and_holder(client):
    client.post("/api/sync/push", json={"transactions": [_tx("t1", "ISSUE", 1000)]})
    item = client.get("/api/sync/pull").json()["items"][0]
    assert item["current_status"] == "ISSUED"
    assert item["holder_user_id"] == "u1"
    assert item["last_action_at"] == 1000


def test_return_clears_holder(client):
    txs = [_tx("t1", "BORROW", 1000), _tx("t2", "RETURN", 2000)]
    client.post("/api/sync/push", json={"transactions": txs})
    item = client.get("/api/sync/pull").json()["items"][0]
    assert item["current_status"] == "AVAILABLE"
    assert item["holder_user_id"] is None
    assert item["last_action_at"] == 2000


def test_item_without_actions_has_no_holder(client):
    item = client.get("/api/sync/pull").json()["items"][0]
    assert item["holder_user_id"] is None
    assert item["last_action_at"] is None


def test_admin_upsert_keeps_status(client):
    client.post("/api/sync/push", json={"transactions": [_tx("t1", "ISSUE", 1000)]})
    client.post("/api/admin/items", json=[{"qr_id": "q1", "name": "שם חדש"}])
    item = client.get("/api/sync/pull").json()["items"][0]
    assert item["name"] == "שם חדש"
    assert item["current_status"] == "ISSUED"


def test_root_page_is_hebrew(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["message"].startswith("שרת אולימפוס פעיל")
