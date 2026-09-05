# Business evals

Run `make eval-demo`. Four declarative YAML cases check real service/SQL outcomes: approval before local task creation and replay, denied evidence/direct links, exact forecast margin with source IDs, and provider failure without task creation. Embedded Qdrant is real in-process code; network Qdrant is tested separately with `make integration-test`.

Reports go to ignored `.runtime/eval-demo.json` with actual timestamp, Git SHA, fixture/config/model version, case outcomes and measured latency. Tokens and cost are null when not measured. Demo evaluation is not model intelligence or factual entailment evaluation. Unit/security tests forbid socket connections.

`uv run python scripts/local_llm.py` is an explicit local-model check and writes a separate report. It does not establish repeated quality, robustness across prompts or hardware performance. The next quality gate is a repeated local-LLM evidence/abstention/schema suite with human-checked cases and sample statistics.
