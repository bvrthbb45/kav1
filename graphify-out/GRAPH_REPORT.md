# Graph Report - kav1  (2026-11-02)

## Corpus Check
- Corpus is ~6,777 words - fits in a single context window. You may not need a graph.

## Summary
- 347 nodes · 640 edges · 21 communities (9 shown, 12 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 55 edges (avg confidence: 0.89)
- Token cost: 92,645 input · 0 output

## Community Hubs (Navigation)
- Visitor CRUD Operations
- CI/CD Pipeline Config
- Logging, Settings and WS Setup
- WebSocket Client
- Search and Visitor Details Dialogs
- Backend Module Overview
- Database Migrations
- API Client
- Create Visitor Dialog
- Visitor Logger
- Alembic Env and Versioning
- Graphify Knowledge Graph Docs
- Server Startup Arguments
- WebSocket Connection Manager

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 34 edges
2. `ApiClient` - 32 edges
3. `VisitorDetailsDialog` - 21 edges
4. `Kav1 Frontend` - 19 edges
5. `show_warning()` - 17 edges
6. `with` - 15 edges
7. `SearchDialog` - 15 edges
8. `CreateVisitorDialog` - 15 edges
9. `EditVisitorDialog` - 13 edges
10. `Kav1 Server (Backend)` - 13 edges

## Surprising Connections (you probably didn't know these)
- `Kav1 Logo Mark` --references--> `Kav1 Visitor Management System`  [INFERRED]
  frontend/app/views/Kav1.png → README.md
- `PySide6 Desktop Frontend` --conceptually_related_to--> `Kav1 Frontend`  [INFERRED]
  README.md → frontend/README.md
- `frontend/clienticon.ico` --semantically_similar_to--> `Kav1 Logo Mark`  [INFERRED] [semantically similar]
  frontend/README.md → frontend/app/views/Kav1.png
- `Graphify Skill Reference` --conceptually_related_to--> `Graphify Knowledge Graph`  [INFERRED]
  .claude/CLAUDE.md → CLAUDE.md
- `Kav1 Visitor Management System` --references--> `Kav1 Frontend`  [INFERRED]
  README.md → frontend/README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Graphify Query-First Exploration Workflow** — claude_graphify_knowledge_graph, claude_graphify_query, claude_graphify_path, claude_graphify_explain, claude_graphify_update [INFERRED 0.75]
- **FastAPI/SQLAlchemy/Pydantic Backend Stack** — requirements_fastapi, requirements_sqlalchemy, requirements_pydantic, backend_readme_kav1_server [INFERRED 0.75]
- **Frontend Server Connection Setup Flow** — frontend_app_views_connection_dialog, frontend_app_core_api_client, frontend_app_core_settings, frontend_app_core_ws_client [INFERRED 0.75]

## Communities (21 total, 12 thin omitted)

### Community 0 - "Visitor CRUD Operations"
Cohesion: 0.09
Nodes (29): create_visitor(), delete_visitor(), get_latest_log_for_visitor(), get_logs(), get_logs_for_visitor(), get_visitor_by_dbid(), get_visitor_by_id(), get_visitors() (+21 more)

### Community 1 - "CI/CD Pipeline Config"
Cohesion: 0.05
Nodes (44): name, needs, runs-on, steps, GITHUB_TOKEN, jobs, build, lint (+36 more)

### Community 2 - "Logging, Settings and WS Setup"
Cohesion: 0.12
Nodes (9): Settings, Log, show_critical_disconnection_warning(), show_warning(), LogsDialog, Kav1 Frontend, frontend/main.spec, pyside6 (package) (+1 more)

### Community 3 - "WebSocket Client"
Cohesion: 0.07
Nodes (4): WebSocketClient, ConnectionDialog, MainWindow, main()

### Community 4 - "Search and Visitor Details Dialogs"
Cohesion: 0.07
Nodes (4): SearchDialog, SearchResultDialog, EditVisitorDialog, VisitorDetailsDialog

### Community 5 - "Backend Module Overview"
Cohesion: 0.11
Nodes (24): Alembic Migration Tool, backend/crud.py, backend/database.py, Kav1 Server (Backend), backend/main.py, backend/models.py, backend/routes.py, backend/schemas.py (+16 more)

### Community 6 - "Database Migrations"
Cohesion: 0.13
Nodes (6): upgrade(), VisitorBase, VisitorCreate, Config, VisitorUpdate, Config

### Community 10 - "Alembic Env and Versioning"
Cohesion: 0.22
Nodes (3): run_migrations_offline(), run_migrations_online(), get_version()

### Community 11 - "Graphify Knowledge Graph Docs"
Cohesion: 0.22
Nodes (9): Graphify Skill Reference, graphify explain command, Graphify Knowledge Graph, graphify-out/graph.json, graphify-out/GRAPH_REPORT.md, graphify-out/wiki/index.md, graphify path command, graphify query command (+1 more)

## Knowledge Gaps
- **19 isolated node(s):** `Graphify Skill Reference`, `graphify query command`, `graphify path command`, `graphify explain command`, `graphify update command` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 127 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `WebSocket Client` to `Create Visitor Dialog`, `Logging, Settings and WS Setup`, `Search and Visitor Details Dialogs`, `API Client`?**
  _High betweenness centrality (0.121) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `MainWindow` (e.g. with `ApiClient` and `Settings`) actually correct?**
  _`MainWindow` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Graphify Skill Reference`, `graphify query command`, `graphify path command` to the rest of the system?**
  _19 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Visitor CRUD Operations` be split into smaller, more focused modules?**
  _Cohesion score 0.09485815602836879 - nodes in this community are weakly interconnected._
- **Why does `Kav1 Frontend` connect `Logging, Settings and WS Setup` to `Backend Module Overview`?**
  _High betweenness centrality (0.105) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `ApiClient` (e.g. with `Settings` and `Log`) actually correct?**
  _`ApiClient` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Should `CI/CD Pipeline Config` be split into smaller, more focused modules?**
  _Cohesion score 0.052525252525252523 - nodes in this community are weakly interconnected._