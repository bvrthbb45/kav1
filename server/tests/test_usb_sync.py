import json
import sys
from pathlib import Path

FAKE_ADB = Path(__file__).with_name("fake_adb.py")

OUTBOX = {
    "device_id": "tab-1",
    "items": [{"qr_id": "new-item", "name": "אפוד"}],
    "users": [{"user_id": "u2", "full_name": "דנה כהן", "unit": "ב"}],
    "transactions": [
        {
            "tx_id": "t1",
            "qr_id": "new-item",
            "user_id": "u2",
            "action_type": "ISSUE",
            "timestamp": 1000,
        },
        {
            "tx_id": "bad",
            "qr_id": "missing",
            "user_id": "u1",
            "action_type": "BORROW",
            "timestamp": 1000,
        },
    ],
}


def test_process_outbox_applies_edits_before_actions(client):
    from app.database import SessionLocal
    from app.usb_sync import process_outbox

    with SessionLocal() as db:
        inbox = process_outbox(db, {"request_id": "r1", **OUTBOX})

    assert inbox["request_id"] == "r1"
    assert inbox["push"]["accepted"] == ["t1"]
    assert inbox["push"]["rejected"][0]["tx_id"] == "bad"
    assert inbox["items_uploaded"] == [{"qr_id": "new-item", "name": "אפוד"}]
    items = {i["qr_id"]: i for i in inbox["state"]["items"]}
    assert items["new-item"]["current_status"] == "ISSUED"
    assert items["new-item"]["holder_user_id"] == "u2"
    assert "u2" in {u["user_id"] for u in inbox["state"]["users"]}


def test_agent_round_trip_with_fake_adb(client, tmp_path, monkeypatch):
    from app.database import SessionLocal
    from app.usb_sync import UsbSyncAgent

    root = tmp_path / "tablet"
    root.mkdir()
    (root / "tablet_outbox.json").write_text(json.dumps(OUTBOX))
    monkeypatch.setenv("FAKE_ADB_ROOT", str(root))
    wrapper = tmp_path / "adb"
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_ADB}" "$@"\n')
    wrapper.chmod(0o755)

    agent = UsbSyncAgent(str(wrapper), SessionLocal)
    assert agent.devices() == {"FAKE123": "device"}
    status, message = agent.sync("FAKE123")

    assert status == "ok"
    inbox = json.loads((root / "received_inbox.json").read_text(encoding="utf-8"))
    assert inbox["push"]["accepted"] == ["t1"]
    status_by_item = {i["qr_id"]: i["current_status"] for i in inbox["state"]["items"]}
    assert status_by_item["new-item"] == "ISSUED"
    # The server database was updated too.
    pulled = client.get("/api/sync/pull").json()
    assert {i["qr_id"] for i in pulled["items"]} >= {"q1", "new-item"}
