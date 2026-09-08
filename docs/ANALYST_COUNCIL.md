# Analyst council / Совет аналитиков

Included in the base software prototype. An owner or manager can examine an idea from several professional perspectives without granting an agent business tools.

## Customer workflow

1. Open **Analyst council / Совет аналитиков** and describe an idea or question. Import relevant documents in Knowledge first. Retrieval uses only the requesting user's accessible document excerpts; it is not an exhaustive review of a tender or contract.
2. Use automatic composition or choose 3–5 roles including Critic. The six available roles are Strategy, Finance, Operations, Procurement, Contracts and Critic. These are analytical perspectives, not qualified staff or independently trained models.
3. Follow the saved stages. Each specialist receives the same evidence snapshot and question without seeing the other specialists' answers. The chair then receives their conclusions and the evidence.
4. Read opportunities, risks, missing data, agreements, disagreements and next steps. GO / NO-GO / NEEDS DATA are recommendations for the human decision maker. Sources open the existing permission-checked document viewer.
5. With a real model, **Prepare instruction** copies the suggested next steps to Chief of Staff. Review the wording, explicitly choose the team, assignee and deadline, then approve the resulting plan. The council itself does not create tasks, approve anything or send messages.

Try: «Стоит ли участвовать в тендере на поставку материалов, учитывая бюджет и срок?» Automatic composition selects Strategy, Procurement, Contracts, Finance and Critic. You can select Operations manually if delivery capacity matters more.

## Honest demo and model behavior

Without a model, both demo and pilot modes display labeled, deterministic role question templates and NEEDS DATA. They do **not** claim to analyze arbitrary business ideas, predict profit or establish consensus. No sample company facts are added to pilot mode.

With a configured local provider, each role and the chair use the existing CrewAI typed-output adapter and isolated runtime in pilot deployments. All roles share the configured model. Same-model agreement is not independent verification. Citation IDs are validated against the retrieved snapshot; this does not prove that a model's interpretation is correct. Unsupported GO/NO-GO without citations fails closed. Finance asks for missing assumptions and code-calculated figures; model prose is not an authoritative financial calculation. Contracts produces questions for human review.

Council model quality and target-device performance require a separate human-labeled evaluation. Existing planner or RAG model evidence does not validate this new scenario.

One new local qwen3.5:9b council contract sample passed Strategy, Finance, Critic and chair with supplied synthetic evidence and a final NEEDS DATA recommendation. This validates that the new roles execute through the runtime for this sample; it is not a statistical quality result. [Recorded model metadata](validation/council-llm.json).

## Engineering contract

- `GET /api/v1/council/roles`: authenticated owner/manager registry, version `council-v1`.
- `POST /api/v1/council` with `Idempotency-Key` and JSON `{"question":"...at least 10 characters...","roles":[]}` returns 202 and a status URL. Question limit 4,000 characters. Empty roles invokes deterministic keyword routing; explicit roles must contain 3–5 distinct allowlisted roles including Critic.
- Automatic routing always includes Strategy and Critic, plus up to three matching specialist lenses. Ties prioritize Contracts, Finance, Procurement, Operations; no match defaults to Operations. The routing method is visible. This is a rule-based router, not an LLM orchestrator.
- Six application-owned skill definitions in `app/council.py`. No installed third-party prompts, executable plugins, customer-editable policy prompts or external tools.
- Existing SQLite `runs`, `jobs` and `audit` store the team selection, one stage per role, synthesis and checkpoint timestamps. No PostgreSQL migration or Markdown source of truth is introduced.
- At most seven stages (selection + five specialists + chair), executed sequentially by the existing worker. Model stages use existing bounded SDK calls and at most one schema repair; there is no debate loop. A lease expiry can repeat only an uncommitted stage; committed checkpoints are not recomputed. A failed stage stops the council and preserves previous checkpoints without presenting them as a completed result. Start a new council after addressing the error.
- Provider/model and registry version must remain unchanged between stages. Schema-invalid replies, invented citations, access changes and excessive context fail closed. Model context data is limited to 20,000 characters and five retrieved excerpts; large output sets may require a narrower question.
- Current role/organization/document rights are checked before model work, before committing each result, and on read. Losing access to any snapshot source hides the entire saved council output, including intermediate conclusions. Audit stores safe stage metadata rather than prompts or document contents.
- History shows councils within the most recent 100 personal workflows. There is no autonomous event loop, outgoing connector, computed council KPI or automatic company-state export.

## Verification

`tests/unit/test_council.py` covers routing, permissions, idempotency, isolated histories, worker restart, lease fencing, revocation, model schema/citations, demo honesty and context limits. `scripts/council_demo.py` exercises the actual Docker worker/API/UI and records EN/RU/mobile screenshots. See IMPLEMENTATION_STATUS.md for executed checks and evidence.
