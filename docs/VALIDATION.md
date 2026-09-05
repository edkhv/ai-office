# Validation evidence — 2026-09-05

Environment: Python 3.11.15 on macOS ARM64; Docker Engine 29.7.2 running a Linux ARM64 VM; Qdrant v1.16.2. These results do not validate Orange Pi, Ascend or arbitrary platform combinations. This report distinguishes software behavior from model quality.

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

Known test warnings: upstream Starlette/AnyIO and CrewAI deprecation warnings. They are not suppressed as passes. No independent LLM judge, repeated grounded-answer evaluation, load benchmark, multi-tenant test, hardware benchmark, encrypted restore drill or production security audit was performed.

Gitleaks 8.30.1 reported zero findings in the final staged publication tree and in remote CI. GitHub Actions quality and demo jobs passed on software commit `a9166bdd3fc5a3af804841a088c30f1663bf3292`: https://github.com/edkhv/ai-office/actions/runs/33960962345. The Linux x86_64 runner used Python 3.11.16; Docker uses pinned Python 3.11.15. The earlier clean-checkout failure was test-directory initialization and was fixed without skipping tests. Screenshots are generated from the running UI; they are not rendered design mockups.
