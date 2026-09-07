# Validation evidence

## Company pilot increment — 2026-09-07

- `make lint`: Ruff, formatting and mypy passed. `make test`: **202 passed**, 3 integration deselected, **84%** coverage. Fresh integration: **3 passed**; deterministic evals: **4 passed**.
- Real-browser pilot: private setup, two employees, owner-only management, immediate token revocation, imported DOCX/catalog, quote approval, named overdue task and briefing; three screenshots; zero browser errors or external requests. [Evidence](validation/pilot-browser.json).
- Real Docker/Qdrant recovery drill: company, source documents, quotation and assigned task preserved; old credentials revoked. [Procedure](continuity/PILOT_BACKUP_RESTORE.md).
- Frozen core audit: 69 packages, zero findings. Optional SDK audit: four ChromaDB advisories remain; isolated runtime is a mitigation, not a clean SDK audit. [Dependency review](DEPENDENCY_REVIEW.md).
- Fresh host HTTP-boundary model checks: health, sourced answer, quote suggestion and two 4096-dimensional embedding vectors passed; Planner/Reviewer rejected its sample (`REVIEW_REJECTED`). **4/5**, not a complete pass. [Evidence](validation/pilot-isolated-llm-host.json).

The prior sections below retain their original verification scope and dates; their missing-feature statements describe those earlier increments.


## Customer increment — 2026-09-07 (Europe/Moscow)

| Current check | Result | Scope |
|---|---|---|
| Frozen install and `make lint` | Passed | Added parser/export dependencies; Ruff check/format of 81 Python files; mypy contracts/config/metrics |
| `make test` | 149 passed, 3 integration tests deselected; 83% coverage | Unit/security with socket denial; real parser subprocesses; new customer HTTP APIs; actual CrewAI quote step over mocked local transport |
| `make integration-test` | 3 passed | Isolated real Qdrant container, current ACL/version/recovery behavior |
| `make eval-demo` | 4 passed | Real SQL outcomes with deterministic providers; model quality not measured |
| `uv build` | Passed | New modules, export font and font license included |
| `make customer-demo` | Passed twice consecutively, 5 screenshots | Current Docker image and retained data; PDF/DOCX → catalog/quote → draft/approved exports → assigned task/deadline/briefing; delayed/overlapping catalog response checks; EN/RU/mobile; zero JS errors/external requests |
| `make smoke` | 7 passed, 0 failed | Current live API/worker/Qdrant, unchanged core workflow, finance and role boundaries |
| `make screenshots` | Passed, 7 screenshots | Original login/plan/approval/task/source/lineage/system/RU/mobile walkthrough; zero JS errors/external requests |

The new quote suite has 28 unit/security cases, including long 100-line DOCX/PDF exports, exact formula/source provenance, unchanged history after catalog updates, revoked source/catalog access, cached-actor downgrade, concurrent approvals and reclaimed-worker fencing. The initial-schema migration test preserves old task records. Binary extraction tests launch the real child process, whose lines are not measured by parent-only coverage. The two customer browser runs retained existing data and passed on the image containing the final actor-organization check and capability registry. Russian dynamic labels, source viewer and rendered exports were visually reviewed. Earlier CI reports below remain historical.

Machine-readable current evidence: [backend checks](validation/customer-software.json), [customer browser](validation/customer-browser.json), [core browser regression](validation/customer-core-browser.json), [live HTTP smoke](validation/customer-http-smoke.json). These local results do not assert a remote CI result; follow [GitHub Actions](https://github.com/edkhv/ai-office/actions) for the published revision.

The refreshed dependency report still contains the same four ChromaDB advisories; new direct dependencies have no reported findings in that run. See [current dependency evidence](validation/customer-dependencies.json). Backend tests cover original-download ACL, PDF pages/DOCX rows, malicious XML, formula cells, Decimal quote arithmetic, stale versions, protected exports, assignees, timezone boundaries and migration of existing tasks.

## Initial release evidence — 2026-09-05

Environment: Python 3.11.15 on macOS ARM64; Docker Engine 29.7.2 running a Linux ARM64 VM; Qdrant v1.16.2. These results do not validate the proposed Local AI Station or arbitrary platform combinations. This report distinguishes software behavior from model quality.

| Check actually run | Result | Scope |
|---|---|---|
| `uv sync --frozen --python 3.11` | Passed | Real lockfile install; CrewAI 1.15.20 |
| `make lint` | Passed | Ruff lint/format; mypy on contracts/config/metrics |
| `make test` | 84 passed, 0 failed; 3 integration tests deselected | Unit/security, real SQL and embedded Qdrant, network sockets blocked; 85% aggregate coverage (CLI/worker main covered separately via live smoke) |
| `make integration-test` | 3 passed, 0 failed | Isolated real Qdrant container: canary/reconnect/ACL, versions/partial-index failure/revocation, embedding collection isolation; clean migrations applied twice |
| `make eval-demo` | 4 passed, 0 failed, 0 skipped | Critical workflow/evidence/lineage/provider-failure cases; actual SQL outputs, measured step latency |
| `make demo` | Passed | Build, fresh volumes, init migration/seed, distinct API/worker, Qdrant, loopback web and readiness |
| `make smoke` | 7 checks passed | Live HTTP + worker + Qdrant, approvals/replay, three tasks, status change, citations, all five metrics/lineage, briefing/audit/role scopes |
| Restart app and worker | Passed | Existing task records and statuses identical after readiness recovered; no duplicate rows |
| `make screenshots` | Passed | Actual Chrome walkthrough: login, plan, approve, task edit, answer/source, lineage, system, RU and mobile. Seven screenshots; no JS errors or browser external requests |
| `uv build` | Passed | Wheel and source distribution built |
| `uv run python scripts/local_llm.py` | 2 checks passed in the final run | Actual CrewAI Planner/Reviewer over local Ollama qwen3.5:9b; qwen3-embedding:latest returned two vectors of dimension 4096. One planning sample; no statistical model quality claim |
| `pip-audit --local --skip-editable` | **4 advisories remain in ChromaDB 1.1.1** | Python dependency audit, not a clean security result; see DEPENDENCY_REVIEW |

Machine-readable reports in `docs/validation/` include actual timestamps, measured durations, mode/fixture/model names, outcomes and Git SHA where recorded. Raw credentials, SDK state, databases, logs and package caches remain under ignored runtime storage or Docker volumes. Model token counts and cost are null because they were not measured.

A first model attempt with mistral:latest was rejected by the Reviewer. No model-produced tasks were executed. The later qwen3.5:9b path passed; both the rejected and successful reports are retained. These are different attempts/configurations, not a claim of a 100% success rate across models.

Unit tests cover concurrent/repeated approval, revised/expired/foreign approval, payload tampering, role revocation before execution, crash before commit, stale worker fencing, queue limits, document ACL changes before model context, stored answer revocation, IDOR, CSRF, login expiry/revocation/rate limits, unsafe uploads/symlinks/XSS, exact `valid`, HTTP redirect/timeout/no fallback, missing/partial/mixed-source arithmetic and zero denominators.

Known test warnings: upstream Starlette/AnyIO and CrewAI deprecation warnings. They are not suppressed as passes. In this earlier run no independent LLM judge, repeated grounded-answer evaluation, load benchmark, multi-tenant test, hardware benchmark, encrypted restore drill or production security audit was performed. The later pilot increment adds an encrypted restore drill; the other validation limits remain.

Gitleaks 8.30.1 reported zero findings in the final staged publication tree and in remote CI. GitHub Actions quality and demo jobs passed on software commit `a9166bdd3fc5a3af804841a088c30f1663bf3292`: https://github.com/edkhv/ai-office/actions/runs/33960962345. The Linux x86_64 runner used Python 3.11.16; Docker uses pinned Python 3.11.15. The earlier clean-checkout failure was test-directory initialization and was fixed without skipping tests. Screenshots are generated from the running UI; they are not rendered design mockups.

The fresh isolated Docker model-boundary run also passed **4/5** checks: health, sourced answer, quote suggestion and embeddings passed; Planner/Reviewer failed closed with `REVIEW_REJECTED`. [Docker model evidence](validation/pilot-isolated-llm-docker.json). This confirms the transport/model boundary for those samples, not reliable free-form planning or statistical model quality.

Latest preserved-data demo regression: `make smoke` **7 passed**; `make customer-demo` completed the original customer workflow with **zero browser errors/external requests** and five refreshed EN/RU/mobile screenshots. Evidence: [legacy smoke](validation/pilot-legacy-smoke.json), [legacy customer browser](validation/pilot-legacy-customer.json).
