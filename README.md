# Kav1 Visitor Management System
<div align="center">
  
![Kav1](https://github.com/user-attachments/assets/6bcebb1b-bc3e-4e3b-b4d5-faece9b61698)<svg width="500" height="500" xmlns="http://www.w3.org/2000/svg">
 <g>
  <rect rx="60" id="svg_11" height="500" width="500" y="0" x="0" stroke-width="0" stroke="#000" fill="#000000"/>
  <rect transform="rotate(45 210 325)" stroke-width="0" id="svg_13" height="50" width="200" y="300" x="110" stroke="#000" fill="#fff"/>
  <rect transform="rotate(-45 210 175)" stroke-width="0" id="svg_15" height="50" width="200" y="150" x="110" stroke="#000" fill="#fff"/>
  <rect transform="rotate(90 100 250)" stroke-width="0" id="svg_19" height="50" width="300" y="225" x="-50" stroke="#000" fill="#fff"/>
  <rect transform="rotate(90 400 250)" stroke-width="0" id="svg_20" height="50" width="300" y="225" x="250" stroke="#000" fill="#fff"/>
 </g>

</svg>

</div>


Kav1 is a modern visitor management system designed to streamline guest check-ins and improve security in controlled environments.
It features a PySide6 desktop frontend and a FastAPI backend, connected through a lightweight REST API with support for real-time updates via WebSocket.

Kav1 is ideal for environments where offline-capable, locally hosted visitor management is preferred over cloud-based tools.

## Warehouse Inventory (offline-first)

This repository also contains an offline-first warehouse inventory system:

- `server/` — FastAPI + SQLite sync server (see [server/README.md](server/README.md)).
- `app/` — Android app (Kotlin, XML views, Hebrew RTL UI, minSdk 19). Open the repository root in
  Android Studio, or build with `./gradlew assembleDebug`. The server address is set by
  `SERVER_BASE_URL` in `app/build.gradle.kts` (default `http://192.168.42.100:8000/`).

The app stores every borrow/return in a local outbox (Room) first, so it works without a
connection. Sync (manual button, 10 s after each action, and every 15 minutes via WorkManager)
pushes the outbox, removes what the server accepted, then replaces the local items and users
with the server's state. Actions the server rejects stay on the device with the reason and can be
re-sent or deleted from the main screen.

## License

This project is licensed under the [GNU General Public License (GPL)](https://www.gnu.org/licenses/gpl-3.0.html). You are free to use, modify, and distribute the project under the terms of this license.
