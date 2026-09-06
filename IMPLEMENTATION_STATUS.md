# AI Office implementation status

Updated 2026-09-07 (Europe/Moscow). Version 0.1.0-alpha plus the customer demonstration increment. This is a runnable software prototype, not a production installation or hardware-validation claim.

## Implemented

- Preserved FastAPI/Pydantic, CrewAI/Ollama, LangChain/Qdrant, Docker Compose and pytest. SQLAlchemy/Alembic/SQLite WAL and one separate leased worker own durable state. The original `edkhv/ai-docs-assistant` repository remains unchanged.
- Instruction → typed plan → clarification/approval/rejection → real local tasks. Exact version/hash/expiry approvals, creator-only decisions, actor/organization/assignee revalidation, queue limits, restart fencing, atomic execution and audit.
- Text PDF and DOCX, including tables, alongside TXT/Markdown: bounded extraction in a separate process, byte-preserved originals, immutable text/versions, page/paragraph/table-row source anchors, SQL/Qdrant ACL filtering, protected originals and saved-answer revocation. OCR is not implemented.
- Excel/CSV catalogs and versioned RUB quotations. A user reviews proposed SKU/quantity pairs; Decimal code calculates discounts, VAT and totals. Why exposes formula and catalog rows. DOCX/PDF exports use the same saved calculation and mark unapproved revisions as drafts. A quoted task is created only after exact-version approval.
- Personal task assignees, My/Today/Overdue/Blocked filters, UTC storage and IANA local-day boundaries. Team visibility is retained; assigned employee tasks are updated only by their assignee or a manager/owner. SQL counters cover all visible records, including beyond the first page.
- Five synthetic Northline financial metrics remain separate from user-uploaded files, catalogs and stored task facts. The on-demand briefing links task records and distinguishes synthetic finance. No notification scheduler or external sending exists.
- Existing demo and local-model paths, bilingual interface, operations/security/hardware documentation and supplied synthetic examples. The new customer and original interface walkthroughs were both verified against the current Docker demo.

## Current verification

Final local backend checks passed: **149 unit/security tests**, 3 integration tests deselected, **83%** aggregate coverage; **3 real-Qdrant integration tests**; **4 deterministic demo evals**. `make lint` passed Ruff, formatting for all 81 Python files and mypy on contracts/config/metrics. Frozen installation and wheel/source build passed, including the new modules, embedded export font and its license. Parser subprocesses are exercised but are not included in parent-process coverage instrumentation.

The 28 quote unit/security cases cover deterministic rounding, unknown SKUs, formulas, false spreadsheet dimensions, stale quote/catalog/source access, stale actor roles, concurrent/repeated approval, reclaimed-worker fencing, XML controls, long 100-line exports and oversized requests without silent truncation. Task tests cover migration from the initial schema with existing records preserved, per-assignee updates, inactive/foreign-team assignees, revocation between approval and execution, offset/DST deadlines, counters beyond 50 tasks and approval queue limits. Existing crash-before-commit rollback tests remain passing.

The connected customer browser scenario passed **twice consecutively with retained data** against the current Docker image, including deliberately delayed/overlapping catalog responses: PDF/DOCX upload and anchored sources, catalog import, reviewed quote revisions, formula, draft/approved DOCX/PDF export, assigned task, overdue/blocked filters and briefing. Five actual EN/RU/mobile customer screenshots and seven refreshed original walkthrough screenshots were captured with **zero browser errors or external requests**. The original live HTTP smoke passed **7 checks**, 0 failures. Visual review covered the source viewer, Russian quote interface and rendered exports. See [current validation evidence](docs/VALIDATION.md).

The refreshed dependency audit still reports **4 advisories in ChromaDB 1.1.1**, constrained transitively by CrewAI. No advisories were reported for the newly added document/catalog/export packages. This is not a clean dependency result. See [dependency review](docs/DEPENDENCY_REVIEW.md) and [current dependency evidence](docs/validation/customer-dependencies.json).

## Publication and earlier evidence

Repository: https://github.com/edkhv/ai-office. The existing public `main` before this increment is `2f023316ff52bc5096771eac0719a128443d9a87`, the hardware-neutral naming update. Earlier software CI, Docker smoke/restart and actual browser screenshots are preserved in [VALIDATION.md](docs/VALIDATION.md) and `docs/validation/`; they are historical evidence.

The customer increment is submitted through repository pull requests; see [pull requests](https://github.com/edkhv/ai-office/pulls) and [latest GitHub Actions results](https://github.com/edkhv/ai-office/actions). Local verification below does not assert remote CI success. The original release identifier remains `v0.1.0-alpha`; git history and the old tag are not rewritten.

## Limits and next steps

**Local AI Station 96–128 GB: Target hardware; not yet validated on device.** Vendor/runtime, performance, capacity, power and recovery remain untested on a target station. Application development does not require buying the proposed hardware.

No production deployment, independent statistical model-quality result, OCR, live mail/CRM/accounting connector, external messaging, scheduler, user-administration workflow, empty-customer initialization, encrypted backup/restore, Investor Room, meetings, multi-tenant isolation or high availability is delivered. The broader Office Manager and P2 directions remain in the [roadmap](docs/ROADMAP.md). Existing local-model Planner/Reviewer evidence does not validate new quote-generation quality.

Resolve or isolate the remaining dependency advisories, establish repeatable human-labeled model evaluations and implement production provisioning/backup/security gates before a real-data production pilot. No distribution license has yet been selected.

## Reproduce

`make demo` → http://127.0.0.1:8090 → private token from `make credential`. `make down` preserves data. Follow [the walkthrough](docs/DEMO_WALKTHROUGH.md) for document → catalog/quote → assigned task. Checks: `make lint`, `make test`, `make integration-test`, `make eval-demo`, then `make smoke`, `make customer-demo` and `make screenshots` for live checks.
