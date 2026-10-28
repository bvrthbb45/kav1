# API endpoints

Generated from the source by `tools/make_api_doc.py`. A request needs a logged-in session (cookie `kav1_session`);
the permission column is what the role must hold (`or` = any one of them). `-` means: logged in is enough, or public (login, branding).

| Method | Path | Permission | File | What |
|---|---|---|---|---|
| POST | `/admin/categories/delete` | `admin.categories.edit` | routes_categories.py |  |
| POST | `/admin/categories/merge` | `admin.categories.edit` | routes_categories.py |  |
| POST | `/admin/categories/rename` | `admin.categories.edit` | routes_categories.py |  |
| POST | `/admin/categories/replace-value` | `admin.categories.edit` | routes_categories.py |  |
| GET | `/admin/panel/audit` | `admin.audit` | routes_admin_panel.py |  |
| GET | `/admin/panel/backup` | `admin.backup` | routes_admin_panel.py | Stream a consistent copy of the SQLite DB for download. |
| GET | `/admin/panel/keys` | `admin.dashboard` | routes_admin_panel.py |  |
| GET | `/admin/panel/overview` | `admin.dashboard` | routes_admin_panel.py |  |
| POST | `/admin/panel/restore` | `admin.backup` | routes_admin_panel.py | Replace the live DB with an uploaded backup. |
| GET | `/admin/panel/settings` | `admin.settings` | routes_admin_panel.py |  |
| PUT | `/admin/panel/settings` | `admin.settings` | routes_admin_panel.py |  |
| GET | `/admin/permissions` | `roles.manage` | routes_admin.py | The static catalog, grouped, for building the role editor UI. |
| GET | `/admin/roles` | `roles.manage` | routes_admin.py |  |
| POST | `/admin/roles` | `roles.manage` | routes_admin.py |  |
| DELETE | `/admin/roles/{role_id}` | `roles.manage` | routes_admin.py |  |
| PUT | `/admin/roles/{role_id}` | `roles.manage` | routes_admin.py |  |
| PUT | `/admin/roles/{role_id}/permissions` | `roles.manage` | routes_admin.py |  |
| GET | `/admin/users` | `users.view` | routes_admin.py |  |
| POST | `/admin/users` | `users.create` | routes_admin.py |  |
| DELETE | `/admin/users/{user_id}` | `users.delete` | routes_admin.py |  |
| PUT | `/admin/users/{user_id}` | `users.edit` | routes_admin.py |  |
| GET | `/auth/branding` | - | routes_auth.py | Public (no auth): branding values for the login screen. |
| POST | `/auth/change-password` | - | routes_auth.py |  |
| POST | `/auth/login` | - | routes_auth.py |  |
| POST | `/auth/logout` | - | routes_auth.py |  |
| GET | `/auth/me` | - | routes_auth.py |  |
| GET | `/locations/entries` | - | routes_locations.py |  |
| POST | `/locations/entries` | - | routes_locations.py |  |
| DELETE | `/locations/entries/{entry_id}` | - | routes_locations.py |  |
| PUT | `/locations/entries/{entry_id}` | - | routes_locations.py |  |
| GET | `/locations/flags` | - | routes_locations.py |  |
| PUT | `/locations/flags` | - | routes_locations.py |  |
| GET | `/locations/maps` | - | routes_locations.py |  |
| POST | `/locations/maps` | - | routes_locations.py | Raw image bytes in the request body (PNG or JPEG); the name is a query parameter. |
| DELETE | `/locations/maps/{map_id}` | - | routes_locations.py | Removes only the map picture; the rows that used it keep their text and lose the point. |
| PUT | `/locations/maps/{map_id}` | - | routes_locations.py |  |
| GET | `/locations/maps/{map_id}/image` | - | routes_locations.py |  |
| GET | `/logs` | `logs.view` | routes.py |  |
| GET | `/logs/{visitor_id}` | `logs.view` | routes.py |  |
| GET | `/reports/dashboard` | `reports.view` | routes_reports.py |  |
| GET | `/reports/export/excel` | `reports.export` | routes_reports.py |  |
| GET | `/reports/visitor/{visitor_id}/export` | `reports.export` | routes_reports.py | Excel report of one visitor's entry/exit history. |
| GET | `/reports/visitor/{visitor_id}/history` | `logs.view` | routes_reports.py | JSON entry/exit history for one visitor (for the on-screen view). |
| POST | `/visitor` | `visitor.create` | routes.py |  |
| GET | `/visitors` | `control.panel` or `visitor.view` | routes.py |  |
| GET | `/visitors/categories/list` | `control.panel` or `visitor.view` | routes.py | Return every distinct property key (category) used across visitors, |
| GET | `/visitors/inside` | `control.panel` or `visitor.view` | routes.py |  |
| GET | `/visitors/overview` | `control.panel` or `visitor.view` | visitor_extras.py | Extra columns for the visitor lists (see the module header). |
| GET | `/visitors/presets/list` | `visitor.create` | routes.py | Return the visitor presets defined in settings. Available to anyone |
| GET | `/visitors/search` | `control.panel` or `visitor.view` | routes.py |  |
| GET | `/visitors/search-by-key-value` | `control.panel` or `visitor.view` | routes.py |  |
| GET | `/visitors/{visitor_id}` | `control.panel` or `visitor.view` | routes.py |  |
| PUT | `/visitors/{visitor_id}` | `visitor.edit` | routes.py |  |
| POST | `/visitors/{visitor_id}/delete` | `visitor.delete` | routes.py |  |
| POST | `/visitors/{visitor_id}/status` | `visitor.entry_exit` | routes.py |  |
| WEBSOCKET | `/ws` | - | routes.py |  |
