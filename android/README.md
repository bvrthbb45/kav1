# Kav1 Inventory (Android)

Offline-first warehouse inventory app. Scan an item's QR code, choose **Borrow** or
**Return**, pick a user, and the action is stored locally in Room. A WorkManager
`SyncWorker` pushes queued actions to the local FastAPI server and pulls fresh
items/users whenever the server is reachable over USB tethering.

- Package: `com.kav1.inventory`
- Server: `http://192.168.42.100:8000/` (`SYNC_BASE_URL` in `app/build.gradle.kts`;
  also update `res/xml/network_security_config.xml`, which allows cleartext only for that host)
- Stack: Room, Retrofit + Gson, CameraX + ZXing core (no Google Play services needed), WorkManager

## Layout

```
data/local    Room entities (Item, User, PendingTransaction), DAOs, AppDatabase
data/remote   Retrofit SyncApi, DTOs, ApiClient
data          InventoryRepository (push/pull logic)
sync          SyncWorker (CoroutineWorker), SyncScheduler (15-min periodic + on-demand)
ui            MainActivity, ScannerFragment (CameraX + QrCodeAnalyzer), ItemActionFragment
```

## Sync behaviour

1. Recording an action inserts a `PendingTransaction` (client UUID `txId`) and
   optimistically updates the local item's status, then requests an immediate sync.
2. `SyncWorker` pushes the queue oldest-first in batches of 100, deleting every `txId`
   the server lists as accepted or rejected, then pulls changes since the last
   `server_time`. Items that still have unpushed actions keep their local status.
3. I/O errors, 408/429 and 5xx responses back off and retry. There is no network-type
   constraint, because Android often doesn't count the tether link as a usable network.

## Server contract

The server must implement these endpoints. JSON uses snake_case; times are epoch millis.

`POST /api/sync/push`

```json
{
  "device_id": "uuid",
  "transactions": [
    {"tx_id": "uuid", "qr_id": "ITEM-001", "user_id": "u42",
     "action_type": "BORROW", "timestamp": 1758790000000}
  ]
}
```

Response: `{"accepted": ["uuid", ...], "rejected": [{"tx_id": "uuid", "reason": "unknown item"}]}`.
Pushes must be **idempotent by `tx_id`**: a retried batch can contain transactions the
server already stored, and those should come back as `accepted`.

`GET /api/sync/pull?since=<server_time>` (`since` is omitted on first sync to get a full snapshot)

```json
{
  "server_time": 1758790000000,
  "items": [{"qr_id": "ITEM-001", "name": "Drill", "status": "BORROWED"}],
  "users": [{"user_id": "u42", "name": "Dana"}],
  "deleted_item_ids": [],
  "deleted_user_ids": []
}
```

`status` is `AVAILABLE` or `BORROWED`.

## Building

Open this `android/` directory in Android Studio, or run `./gradlew assembleDebug` with
the Android SDK installed (`sdk.dir` in `local.properties` or `ANDROID_HOME`).
