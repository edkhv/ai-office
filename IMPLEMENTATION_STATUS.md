# AI Office implementation status

Updated 2026-09-07 (Europe/Moscow). Version 0.1.0-alpha plus the company pilot increment. This is a runnable software prototype, not a production installation or hardware-validation claim.

## Implemented

- Preserved FastAPI/Pydantic, CrewAI/Ollama, LangChain/Qdrant, Docker Compose and pytest. SQLAlchemy/Alembic/SQLite WAL and one separate leased worker own durable state. The original `edkhv/ai-docs-assistant` repository remains unchanged.
- Instruction → typed plan → clarification/approval/rejection → real local tasks. Exact version/hash/expiry approvals, creator-only decisions, actor/organization/assignee revalidation, queue limits, restart fencing, atomic execution and audit.
- Text PDF and DOCX, including tables, alongside TXT/Markdown: bounded extraction in a separate process, byte-preserved originals, immutable text/versions, page/paragraph/table-row source anchors, SQL/Qdrant ACL filtering, protected originals and saved-answer revocation. OCR is not implemented.
- Excel/CSV catalogs and versioned RUB quotations. A user reviews proposed SKU/quantity pairs; Decimal code calculates discounts, VAT and totals. Why exposes formula and catalog rows. DOCX/PDF exports use the same saved calculation and mark unapproved revisions as drafts. A quoted task is created only after exact-version approval.
- Personal task assignees, My/Today/Overdue/Blocked filters, UTC storage and IANA local-day boundaries. Team visibility is retained; assigned employee tasks are updated only by their assignee or a manager/owner. SQL counters cover all visible records, including beyond the first page.
- Five synthetic Northline financial metrics remain separate from user-uploaded files, catalogs and stored task facts. The on-demand briefing links task records and distinguishes synthetic finance. No notification scheduler or external sending exists.
- Existing demo and local-model paths, bilingual interface, operations/security/hardware documentation and supplied synthetic examples. The new customer and original interface walkthroughs were both verified against the current Docker demo.

- Company pilot: separate persisted data mode, empty initialization, private one-time setup, company identity, owner-created users, display names, roles/teams, token rotation and immediate session revocation. Last-active-owner and cross-organization boundaries are checked transactionally. Existing demo data is preserved; mixing data modes is rejected.
- Manual authenticated-encryption backup/restore, offline writer locks, preserved SQL/source versions, rebuilt Qdrant and revoked old credentials. See the [recovery procedure](docs/continuity/PILOT_BACKUP_RESTORE.md).
- CrewAI runs in an optional separate image without business-volume access, with a restricted model gateway. Core installation excludes CrewAI/ChromaDB; SDK-side advisories are retained transparently.

## Current pilot verification

`make lint` passed Ruff/formatting and mypy; **202 unit/security tests passed**, 3 integration tests deselected, **84%** aggregate coverage. Fresh `make integration-test` passed **3** real-Qdrant checks; `make eval-demo` passed **4** deterministic cases. Workspace tests include migration from 0004, token races, mode mismatch, empty pilot data, fresh owner permissions, last-owner protection, credential/session revocation and HTTP setup. A previously strict assignee-output assertion was updated for the new non-secret `display_name` field.

The real browser pilot run at isolated port 8092 passed setup, two employees, employee administration denial, account disabling, DOCX/catalog import, quote approval, named overdue tasks and briefing. Three screenshots contain no tokens; the run recorded **zero browser errors and external requests**. The test company/files are explicitly synthetic test input, not automatically seeded pilot content. See [pilot browser evidence](docs/validation/pilot-browser.json).

A real Docker/Qdrant offline recovery drill preserved documents, quotation, assigned task and company profile while revoking previous credentials. The refreshed frozen **core dependency audit has zero findings** across 69 packages; **four ChromaDB advisories remain in the isolated optional SDK environment**. Isolation mitigates exposure and does not fix these advisories. See [dependency review](docs/DEPENDENCY_REVIEW.md).

Fresh actual-model host-boundary checks passed health, a sourced answer, explicit-SKU quote suggestion and embeddings (two vectors, dimension 4096); the Planner/Reviewer sample failed closed with `REVIEW_REJECTED`. This is **4/5 checks, not a fully passed model suite** or statistical quality result. [Host model evidence](docs/validation/pilot-isolated-llm-host.json).

## Earlier customer increment verification (historical)


Final local backend checks passed: **149 unit/security tests**, 3 integration tests deselected, **83%** aggregate coverage; **3 real-Qdrant integration tests**; **4 deterministic demo evals**. `make lint` passed Ruff, formatting for all 81 Python files and mypy on contracts/config/metrics. Frozen installation and wheel/source build passed, including the new modules, embedded export font and its license. Parser subprocesses are exercised but are not included in parent-process coverage instrumentation.

The 28 quote unit/security cases cover deterministic rounding, unknown SKUs, formulas, false spreadsheet dimensions, stale quote/catalog/source access, stale actor roles, concurrent/repeated approval, reclaimed-worker fencing, XML controls, long 100-line exports and oversized requests without silent truncation. Task tests cover migration from the initial schema with existing records preserved, per-assignee updates, inactive/foreign-team assignees, revocation between approval and execution, offset/DST deadlines, counters beyond 50 tasks and approval queue limits. Existing crash-before-commit rollback tests remain passing.

The connected customer browser scenario passed **twice consecutively with retained data** against the current Docker image, including deliberately delayed/overlapping catalog responses: PDF/DOCX upload and anchored sources, catalog import, reviewed quote revisions, formula, draft/approved DOCX/PDF export, assigned task, overdue/blocked filters and briefing. Five actual EN/RU/mobile customer screenshots and seven refreshed original walkthrough screenshots were captured with **zero browser errors or external requests**. The original live HTTP smoke passed **7 checks**, 0 failures. Visual review covered the source viewer, Russian quote interface and rendered exports. See [current validation evidence](docs/VALIDATION.md).

The earlier full-environment dependency audit reported **4 advisories in ChromaDB 1.1.1**, constrained transitively by CrewAI. No advisories were reported for the newly added document/catalog/export packages. This is not a clean dependency result. See [dependency review](docs/DEPENDENCY_REVIEW.md) and [current dependency evidence](docs/validation/customer-dependencies.json).

## Publication and earlier evidence

Repository: https://github.com/edkhv/ai-office. The public `main` before this pilot increment is `bad5fd9542037fb71a0f7df9469fac7fd32775e7`, the merged customer demonstration increment. Earlier software CI, Docker smoke/restart and actual browser screenshots are preserved in [VALIDATION.md](docs/VALIDATION.md) and `docs/validation/`; they are historical evidence.

The customer increment is submitted through repository pull requests; see [pull requests](https://github.com/edkhv/ai-office/pulls) and [latest GitHub Actions results](https://github.com/edkhv/ai-office/actions). Local verification below does not assert remote CI success. The original release identifier remains `v0.1.0-alpha`; git history and the old tag are not rewritten.

## Limits and next steps

**Local AI Station 96–128 GB: Target hardware; not yet validated on device.** Vendor/runtime, performance, capacity, power and recovery remain untested on a target station. Application development does not require buying the proposed hardware.

No production deployment, independent statistical model-quality result, OCR, live mail/CRM/accounting connector, external messaging, scheduler, scheduled/off-site backup operations, Investor Room, meetings, multi-tenant isolation or high availability is delivered. The broader Office Manager and P2 directions remain in the [roadmap](docs/ROADMAP.md). Existing local-model Planner/Reviewer evidence does not validate new quote-generation quality.

Resolve the remaining isolated SDK advisories, establish repeatable human-labeled model evaluations and validate deployment/security/operational gates before a production installation. No distribution license has yet been selected.

## Reproduce

`make demo` → http://127.0.0.1:8090 → private token from `make credential`. `make down` preserves data. Follow [the walkthrough](docs/DEMO_WALKTHROUGH.md) for document → catalog/quote → assigned task. Checks: `make lint`, `make test`, `make integration-test`, `make eval-demo`, then `make smoke`, `make customer-demo` and `make screenshots` for live checks.

Company pilot: `make pilot` → http://127.0.0.1:8091 → `make pilot-setup-token` → owner setup → People and access. It uses separate volumes and starts empty. [Pilot instructions](docs/PILOT_SETUP.md). The user-facing pilot can remain uninitialized until the owner enters the private setup token.

The fresh isolated Docker model-boundary run also passed **4/5** checks: health, sourced answer, quote suggestion and embeddings passed; Planner/Reviewer failed closed with `REVIEW_REJECTED`. [Docker model evidence](docs/validation/pilot-isolated-llm-docker.json). This confirms the transport/model boundary for those samples, not reliable free-form planning or statistical model quality.

Latest preserved-data demo regression: `make smoke` **7 passed**; `make customer-demo` completed the original customer workflow with **zero browser errors/external requests** and five refreshed EN/RU/mobile screenshots. Evidence: [legacy smoke](docs/validation/pilot-legacy-smoke.json), [legacy customer browser](docs/validation/pilot-legacy-customer.json).
