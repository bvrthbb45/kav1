# Graph Report - kav1  (2026-11-02)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 310 nodes · 581 edges · 19 communities (6 shown, 13 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 34 edges (avg confidence: 0.91)
- Token cost: 42,619 input · 255 output

## Graph Freshness
- Built from commit: `7a270a37`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Visitor CRUD Operations
- CI/CD Pipeline Config
- Logging and Warnings
- Main Window and Connection
- Search and Log Dialogs
- Database Migrations
- API Client
- Create Visitor Dialog
- WebSocket Client Setup
- Edit Visitor Dialog
- Server Startup Arguments
- WebSocket Connection Manager

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 34 edges
2. `ApiClient` - 32 edges
3. `VisitorDetailsDialog` - 21 edges
4. `show_warning()` - 17 edges
5. `SearchDialog` - 15 edges
6. `CreateVisitorDialog` - 15 edges
7. `with` - 15 edges
8. `EditVisitorDialog` - 13 edges
9. `Log` - 12 edges
10. `SearchResultDialog` - 12 edges

## Surprising Connections (you probably didn't know these)
- `ApiClient` --uses--> `Settings`  [INFERRED]
  frontend/app/core/api_client.py → frontend/app/core/settings.py
- `MainWindow` --uses--> `Settings`  [INFERRED]
  frontend/app/views/main_window.py → frontend/app/core/settings.py
- `ApiClient` --uses--> `Log`  [INFERRED]
  frontend/app/core/api_client.py → frontend/app/utils/log.py
- `MainWindow` --uses--> `Log`  [INFERRED]
  frontend/app/views/main_window.py → frontend/app/utils/log.py
- `VisitorDetailsDialog` --uses--> `Log`  [INFERRED]
  frontend/app/views/visitor/visitor_details_dialog.py → frontend/app/utils/log.py

## Import Cycles
- None detected.

## Communities (19 total, 13 thin omitted)

### Community 0 - "Visitor CRUD Operations"
Cohesion: 0.06
Nodes (35): create_visitor(), delete_visitor(), get_latest_log_for_visitor(), get_logs(), get_logs_for_visitor(), get_visitor_by_dbid(), get_visitor_by_id(), get_visitors() (+27 more)

### Community 1 - "CI/CD Pipeline Config"
Cohesion: 0.05
Nodes (44): name, needs, runs-on, steps, GITHUB_TOKEN, jobs, build, lint (+36 more)

### Community 2 - "Logging and Warnings"
Cohesion: 0.18
Nodes (4): Settings, Log, show_critical_disconnection_warning(), show_warning()

### Community 3 - "Main Window and Connection"
Cohesion: 0.10
Nodes (3): ConnectionDialog, MainWindow, main()

### Community 4 - "Search and Log Dialogs"
Cohesion: 0.08
Nodes (4): LogsDialog, SearchDialog, SearchResultDialog, VisitorDetailsDialog

### Community 5 - "Database Migrations"
Cohesion: 0.11
Nodes (4): run_migrations_offline(), run_migrations_online(), upgrade(), get_version()

## Knowledge Gaps
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `Main Window and Connection` to `Logging and Warnings`, `Search and Log Dialogs`, `API Client`, `Create Visitor Dialog`, `WebSocket Client Setup`?**
  _High betweenness centrality (0.139) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `MainWindow` (e.g. with `ApiClient` and `Settings`) actually correct?**
  _`MainWindow` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Should `Visitor CRUD Operations` be split into smaller, more focused modules?**
  _Cohesion score 0.058823529411764705 - nodes in this community are weakly interconnected._
- **Why does `ApiClient` connect `API Client` to `Logging and Warnings`, `Main Window and Connection`, `Search and Log Dialogs`, `Create Visitor Dialog`, `WebSocket Client Setup`, `Edit Visitor Dialog`?**
  _High betweenness centrality (0.115) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `ApiClient` (e.g. with `Settings` and `Log`) actually correct?**
  _`ApiClient` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Should `CI/CD Pipeline Config` be split into smaller, more focused modules?**
  _Cohesion score 0.052525252525252523 - nodes in this community are weakly interconnected._
- **Why does `VisitorDetailsDialog` connect `Search and Log Dialogs` to `Logging and Warnings`, `Main Window and Connection`, `API Client`, `WebSocket Client Setup`, `Edit Visitor Dialog`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._