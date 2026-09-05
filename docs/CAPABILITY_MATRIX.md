# Capability matrix

Implementation and validation are independent. Runtime mode and health are separate from historical test evidence. Hardware is never inferred from HTTP mock tests.

| Module | Implementation | Validation | Mode | Evidence | Limitations |
|---|---|---|---|---|---|
| Chief of Staff | implemented | integration | demo | tests/unit/test_workflows.py | Local tasks and unsent drafts only |
| Knowledge | implemented | integration | demo | tests/security/test_knowledge.py | Markdown/TXT only; hash embedding demo is not semantic quality validation |
| Business Control | implemented | integration | synthetic | tests/unit/test_metrics.py | Fixture ledger, no live accounting source |
| Ollama + CrewAI | implemented | local_llm | local_ollama | tests/unit/test_providers.py, scripts/local_llm.py | Single installed-model planner/reviewer and embeddings check; repeated quality evaluation pending |
| Compatible HTTP | implemented | unit | compatible_http | tests/unit/test_providers.py | Runtime contract must be explicitly verified; no device claim |
| Investor Room, Office Manager, connectors | planned | not_run | roadmap | — | P1/P2; not implemented |
| Orange Pi target profile | partial | not_run | target only | hardware/ORANGE_PI_VALIDATION.md | Device not available; transport/runtime not configured |

Synthetic data is used throughout. API/UI read app/capabilities.json; this document mirrors that registry. On-device status requires physical evidence. See VALIDATION.md for exact commands and scope.
