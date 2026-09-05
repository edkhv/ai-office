# AI Office implementation status

Updated 2026-09-05. Version 0.1.0-alpha. Software MVP is implemented and locally demonstrated. No hardware integration claim.

## Completed and verified

- Original repository read at `d24f1e98078009b89ee1a93eedc61bc1fc3be8f4`; original tracked files unchanged; no original LICENSE found.
- Separate project, Python 3.11, actual uv.lock, FastAPI/Pydantic, SQLAlchemy/Alembic/SQLite WAL, separate leased worker, Qdrant, CrewAI/Ollama and local vanilla UI.
- Durable instruction → plan → clarification/approval/rejection → real local tasks. Exact payload/version/hash/expiry approvals, role revalidation, idempotency, atomic local execution and audit.
- Markdown/TXT source versions, recoverable pending/failed indexing, current-version retrieval, pre-context SQL/Qdrant ACL filtering, protected citations and persisted-answer revocation.
- Five Decimal metrics, actual source rows/hashes/formulas, timestamps/freshness, on-demand briefing and audit.
- English/Russian desktop/mobile UI. Seven actual screenshots and a browser walkthrough with no external browser requests or JS errors.
- Deterministic demo is clearly marked. Real local CrewAI Planner/Reviewer + Ollama and embedding calls were exercised. Compatible HTTP contract is unit-tested; not on-device validated.
- Documentation: baseline/provenance, architecture, threat model, operations, data lineage, capability matrix, roadmap, continuity, demo guide, English partner overview and hardware plan.

## Checks

84 unit/security tests passed, 3 real-Qdrant integration tests passed, 4 demo evals passed, 7 live HTTP smoke checks passed. Ruff/format/mypy and package build passed. Fresh Compose build/start and app/worker restart with preserved rows passed. See docs/VALIDATION.md and docs/validation/ for scope and timestamps.

Dependency audit: reduced from 20 findings across 8 packages to 4 remaining advisories in unused transitive ChromaDB 1.1.1. This is not a clean dependency-security result. See docs/DEPENDENCY_REVIEW.md.

Secret scan: Gitleaks 8.30.1 scanned the final staged publication tree with zero findings; custom tracked-file publication gate and staged diff whitespace check passed. The initial scan matched a synthetic evidence marker; its wording was changed without suppressing scanner rules. No real secret was found in that result.

## Publication

Public repository: https://github.com/edkhv/ai-office, branch main. Software commit `a9166bdd3fc5a3af804841a088c30f1663bf3292` passed both remote quality and demo jobs: https://github.com/edkhv/ai-office/actions/runs/33960962345. This includes a clean Linux x86_64 frozen install, lint/type checks, 84 unit/security tests, 3 real-Qdrant integration tests, 4 demo evals, package build, publication gate, Gitleaks and Compose demo/smoke/restart/repeat smoke.

The initial quality run failed because pytest's ignored .runtime parent did not exist in a clean checkout. Explicit bootstrap creation fixed it; an independent fresh-directory local run and the repeated remote CI passed. The original failed run remains visible in GitHub history. Subsequent documentation commits record this evidence; they do not change business code. Release identifier: `v0.1.0-alpha`; no production-readiness or clean dependency-audit claim.

## Honest limits

Local AI Station: **Target hardware; not yet validated on device.** No device, driver, vendor runtime, device compatibility, throughput or purchase/partnership is asserted. The target YAML is descriptive, not a driver installer.

No external sending, live business connector, Office Manager, DOCX/PDF/OCR, meetings, Investor Room, scheduler, encrypted backup/restore, travel synchronization or P2 workforce implementation. Roadmap entries remain planned. No production, multi-tenant, independent model-quality or HA claim. Reindex CLI requires owner access and a maintenance window. Demo only plans its supported procurement scenario and requires confirmed structured assignment fields.

## Reproduce / continue

`make demo` → http://127.0.0.1:8090 → private token from `make credential`. `make down` preserves data. Checks: `make lint`, `make test`, `make integration-test`, `make eval-demo`, `make smoke`.

Next engineering step: resolve/isolate ChromaDB dependency advisories and build a repeated, human-labeled real-model evidence/abstention suite; then implement one read-only business connector. Do not hide this work behind claims of device readiness.

## Hardware-neutral naming update — 2026-09-05

The target is now **Local AI Station 96–128 GB**, without a mandatory vendor, accelerator or separate host. Updated the application/API, bilingual README, capability registry, hardware profile, validation plan, roadmap and partner material. Development continues on available computers; physical performance and delivery checks remain `not_run`. No hardware test result was added.

Validation for this change: Ruff/format/mypy passed; 84 existing unit/security tests passed (3 integration tests deselected); the Docker demo rebuilt and reached healthy state. Seven actual application screenshots were regenerated by the existing browser walkthrough with no browser errors or external requests. Previous dependency findings and device limitations remain recorded.
