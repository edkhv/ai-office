# Operations

## Demo

Install Docker Engine/Desktop with Compose v2, then run `make demo`. Init applies Alembic migrations and seeds Northline Demo once; app and worker start only after init succeeds. Open http://127.0.0.1:8090 and run `make credential` to issue an owner login token. Keep this terminal output private. `make credential ROLE=manager` or `ROLE=employee` creates scoped credentials. The original first-run tokens are in the private Docker volume, never in Git.

On Windows without Make: `docker compose up -d --build --wait --wait-timeout 180`, then `docker compose exec app python -m app.cli credential owner`. If using another loopback port, also update the base URL in the smoke/screenshot scripts. Do not open Qdrant ports.

`make down` stops this project's containers and retains volumes. `make demo` preserves task status and document revisions. There is intentionally no implicit reset command. Container failures are inspected with `docker compose ps` and `docker compose logs --tail 50 app worker init`; application errors omit content. `make doctor` outputs safe mode/provider/storage/hardware statuses.

Revoke all credentials and sessions for one actor: `docker compose exec app python -m app.cli revoke-credentials employee`. Issue a replacement with `make credential ROLE=employee`. HTTPS deployments must set `AI_OFFICE_COOKIE_SECURE=true`, terminate TLS in a reviewed reverse proxy, restrict host/origin access and replace synthetic fixtures before any production evaluation. No reverse-proxy deployment has been validated here.

## Worker recovery

A long-running job remains visible with its ID, attempts, lease and error code. UI automatic polling stops after approximately one minute; refresh the persisted status manually. If worker heartbeat is stale, readiness reports degraded. Restart with `docker compose restart worker`. Leases normally expire after 300 seconds. Atomic local execution rolls back on process crash; reclaim does not duplicate tasks. Provider/schema failures are recorded as failed. Inspect and submit a new corrected command rather than blindly retrying a future external action.

No network timeout can be interpreted as a successful external write. There are no external write connectors in P0. Future ambiguous writes require needs_reconciliation, an outbox and provider-specific idempotency.

## Documents and indexes

Upload TXT/Markdown (default 128 KiB), text PDF or DOCX (up to 10 MiB) through Knowledge. Binary files preserve original bytes and extracted page/paragraph/table-row anchors. Scanned PDFs without a text layer return `OCR_REQUIRED`; encrypted, malformed or oversized files return explicit errors. Parsing has a 20-second wall limit, 10-second CPU limit and Linux 768 MiB address-space limit; this is not an OS sandbox. Same visible filename creates a new version; identical current content is idempotent, while changed binary originals retain distinct versions. ACLs can be patched by the owner at `/api/v1/documents/{id}/acl`; ordinary re-import does not modify existing ACLs. Failed versions can be retried by importing the same file. Old indexed versions stay immutable.

The active collection name fingerprints embedding provider/model, dimensions and chunk algorithm. Model changes do not delete old collections. Explicitly rebuild current source versions using `docker compose exec app python -m app.cli reindex`. Schedule a maintenance window: reindexing marks each affected current version pending during the rebuild; source retrieval is unavailable for it until indexing succeeds. If a document is not accessible to the owner role, grant owner access explicitly before running this alpha CLI. This is a limitation, not a background zero-downtime migration.

## Catalogs, quotes and task control

Download the CSV/XLSX template in Commercial proposals. Use one sheet and exactly `sku,name,unit,price_without_vat,vat_percent,currency` columns, at most 1,000 items and 2 MiB. Currency is RUB; prices exclude VAT; quantities/discounts are entered per quote. Formula cells, duplicate SKUs, unknown currency and malformed values are rejected with the affected row/cell where available. Importing a new catalog version preserves earlier evidence.

Select a price-list version and enter a request or choose a permitted document/version. In demo, only explicit `STEEL-01 × 5` style items are suggested; review every line manually. Save the quote, inspect the calculated amounts and source-row formulas, and download DOCX/PDF. Exports remain marked DRAFT until the approved execution job completes. Choose a same-team active assignee, deadline and acceptance criteria before proposing approval. New quote versions invalidate earlier pending approvals; an already executed task remains historical evidence.

The creator alone approves a quote workflow. Source/catalog access and assignee membership are rechecked before execution. No email is sent. The local task title and criteria are explicit user inputs; do not copy confidential quote/source details into a team-visible task unless that visibility is intended.

Task filters and the on-demand briefing accept the browser IANA timezone. Dates are stored in UTC; overdue means earlier than the server clock and not done. Counters include every visible task, independent of the 50-row detail page. Existing unassigned tasks keep team-scoped editing; individual assignments restrict employee edits to the assignee. This is not an automatic notification scheduler.

## Backups

Manual encrypted offline backup/restore is implemented for the company pilot. Follow [the exact procedure](continuity/PILOT_BACKUP_RESTORE.md): stop app/worker, use the exclusive maintenance lease, preserve immutable source versions and SQL, then restore into an empty target and rebuild Qdrant. Scheduled/off-site production operations remain planned. Never copy a live SQLite db file without its WAL consistency. No Docker volume deletion is needed for normal operation.

## Development

`uv sync --frozen --python 3.11`; `make lint`; `make test`; `make integration-test`; `make eval-demo`. `make smoke` and `make customer-demo` require the running Compose demo. The customer command checks upload → quote/export/approval → assigned task/deadline in a real browser; its report is `.runtime/customer-demo.json`. CI installs Chromium and runs the customer scenario after an app/worker restart. `make screenshots` uses Chrome on macOS if installed, otherwise Playwright Chromium: install it into this project with `PLAYWRIGHT_BROWSERS_PATH=.runtime/browsers uv run playwright install chromium`, and use the same environment when running screenshots. No frontend build or CDN is needed.

Direct non-Docker app start after supplying a reachable Qdrant URL: `uv run python -m app.cli init`, then run `uv run python -m app.worker` in one terminal and `uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8090 --no-access-log` in another. The supported clean-checkout demo command remains `make demo`.

Company setup and employee administration: [PILOT_SETUP.md](PILOT_SETUP.md). `make pilot` uses a separate project at port 8091; `make pilot-setup-token` prints a private one-time initialization token only while setup is unfinished. Existing data cannot be switched between demo and pilot.
