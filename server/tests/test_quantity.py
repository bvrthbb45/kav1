"""Items with a stock quantity: actions take or return part of it."""

from datetime import datetime

from app import models
from app.stock import replay


class Tx:
    def __init__(self, ts, user, action, qty):
        self.timestamp = datetime(2026, 1, 1, 0, 0, ts)
        self.user_id = user
        self.action_type = action
        self.quantity = qty
        self.tx_id = f"{ts}-{user}"


def test_replay_splits_stock_between_soldiers():
    state = replay(
        50,
        [
            Tx(1, "a", "BORROW", 5),
            Tx(2, "b", "ISSUE", 7),
            Tx(3, "a", "RETURN", 2),
        ],
    )
    assert state.available == 40
    assert (state.holders["a"].borrowed, state.holders["b"].issued) == (3, 7)
    assert state.status == models.STATUS_AVAILABLE


def test_replay_single_unit_keeps_latest_action_wins():
    state = replay(1, [Tx(1, "a", "BORROW", 1), Tx(2, "b", "BORROW", 1)])
    assert list(state.holders) == ["b"]
    assert state.status == models.STATUS_BORROWED
    # A return by anyone brings the unit back.
    state = replay(1, [Tx(1, "a", "ISSUE", 1), Tx(2, "c", "RETURN", 1)])
    assert state.holders == {} and state.available == 1


def test_replay_takes_missing_units_from_oldest_holder():
    state = replay(
        10, [Tx(1, "a", "BORROW", 6), Tx(2, "b", "BORROW", 4), Tx(3, "c", "ISSUE", 3)]
    )
    assert state.holders["a"].borrowed == 3
    assert state.available == 0
    assert state.status == models.STATUS_BORROWED


def _push(client, tx_id, action, qty, ts, user="u1", qr="BOX"):
    return client.post(
        "/api/sync/push",
        json={
            "transactions": [
                {
                    "tx_id": tx_id,
                    "qr_id": qr,
                    "user_id": user,
                    "action_type": action,
                    "timestamp": ts,
                    "quantity": qty,
                }
            ]
        },
    ).json()


def _item(client, qr):
    return next(
        i for i in client.get("/api/sync/pull").json()["items"] if i["qr_id"] == qr
    )


def test_loan_quantities_end_to_end(client):
    client.post(
        "/api/panel/items",
        json={"qr_id": "BOX", "name": "מכשירי קשר", "category": "קשר", "quantity": 50},
    )
    client.post(
        "/api/admin/users", json=[{"user_id": "u2", "full_name": "דנה", "unit": "ב"}]
    )
    assert _push(client, "t1", "BORROW", 5, 1_700_000_000_000)["accepted"] == ["t1"]
    assert _push(client, "t2", "BORROW", 7, 1_700_000_001_000, user="u2")["accepted"]

    pulled = client.get("/api/sync/pull").json()
    box = next(i for i in pulled["items"] if i["qr_id"] == "BOX")
    assert box["kind"] == "LOAN"
    assert (box["quantity"], box["available_qty"], box["borrowed_qty"]) == (50, 38, 12)
    held = {(h["user_id"], h["borrowed"]) for h in pulled["holdings"]}
    assert held == {("u1", 5), ("u2", 7)}
    assert {h["quantity"] for h in pulled["history"]} == {5, 7}

    card = client.get("/api/panel/users/card", params={"user_id": "u2"}).json()
    assert card["holding"][0]["borrowed"] == 7
    summary = {c["name"]: c for c in client.get("/api/panel/data").json()["categories"]}
    assert summary["קשר"]["total"] == 50 and summary["קשר"]["available"] == 38

    # Lowering the stock below what is out marks the item as fully taken.
    client.post(
        "/api/panel/items",
        json={"qr_id": "BOX", "name": "מכשירי קשר", "category": "קשר", "quantity": 12},
    )
    box = _item(client, "BOX")
    assert box["available_qty"] == 0 and box["current_status"] == "BORROWED"


def test_consumables_are_issued_and_leave_the_stock(client):
    client.post(
        "/api/panel/items",
        json={"qr_id": "BAT", "name": "סוללות", "quantity": 200, "kind": "CONSUMABLE"},
    )
    assert _push(client, "t1", "ISSUE", 20, 1_000, qr="BAT")["accepted"] == ["t1"]
    assert _push(client, "t2", "ISSUE", 30, 2_000, qr="BAT")["accepted"] == ["t2"]
    bat = _item(client, "BAT")
    assert (bat["kind"], bat["quantity"], bat["available_qty"], bat["issued_qty"]) == (
        "CONSUMABLE",
        150,
        150,
        20 + 30,
    )
    # Issued units are gone, not held by anyone.
    assert client.get("/api/sync/pull").json()["holdings"] == []
    counts = client.get("/api/panel/status").json()["counts"]
    assert counts["issued"] == 50

    # Consumables cannot be borrowed or returned.
    body = _push(client, "t3", "BORROW", 1, 3_000, qr="BAT")
    assert body["accepted"] == [] and "ניצרך" in body["rejected"][0]["message"]
    assert _push(client, "t4", "RETURN", 1, 3_000, qr="BAT")["accepted"] == []

    # The operator enters the stock on the shelf now; issued units stay counted.
    client.post(
        "/api/panel/items",
        json={"qr_id": "BAT", "name": "סוללות", "quantity": 400, "kind": "CONSUMABLE"},
    )
    bat = _item(client, "BAT")
    assert (bat["quantity"], bat["issued_qty"]) == (400, 50)

    # Issuing more than the stock empties it.
    _push(client, "t5", "ISSUE", 500, 4_000, qr="BAT")
    bat = _item(client, "BAT")
    assert (bat["quantity"], bat["current_status"]) == (0, "ISSUED")


def test_old_tablets_push_without_quantity(client):
    r = client.post(
        "/api/sync/push",
        json={
            "transactions": [
                {
                    "tx_id": "x",
                    "qr_id": "q1",
                    "user_id": "u1",
                    "action_type": "BORROW",
                    "timestamp": 1,
                }
            ]
        },
    )
    assert r.json()["accepted"] == ["x"]
    q1 = next(
        i for i in client.get("/api/sync/pull").json()["items"] if i["qr_id"] == "q1"
    )
    assert q1["current_status"] == "BORROWED" and q1["holder_user_id"] == "u1"


def test_excel_import_reads_quantity(client):
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["מספר סידורי", "שם פריט", "כמות במלאי"])
    ws.append(["BAT", "סוללות", 200])
    ws.append(["BAD", "שבור", "הרבה"])
    out = io.BytesIO()
    wb.save(out)
    body = client.post("/api/panel/import", content=out.getvalue()).json()
    assert body["message"].startswith("הייבוא הושלם: 0 חיילים, 1 פריטים")
    assert len(body["errors"]) == 1
    bat = next(
        i for i in client.get("/api/sync/pull").json()["items"] if i["qr_id"] == "BAT"
    )
    assert bat["quantity"] == 200 and bat["available_qty"] == 200


def test_excel_import_reads_kind(client):
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["מספר סידורי", "שם פריט", "סוג שימוש", "כמות"])
    ws.append(["C1", "חטיפים", "ניצרך", 100])
    ws.append(["L1", "משקפת", "מושאל", 3])
    out = io.BytesIO()
    wb.save(out)
    assert client.post("/api/panel/import", content=out.getvalue()).json()["success"]
    assert _item(client, "C1")["kind"] == "CONSUMABLE"
    assert _item(client, "L1")["kind"] == "LOAN"
