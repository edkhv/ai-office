# Roadmap and future contracts

All entries below are **implementation=planned, validation=not_run**. Written contracts are not shipped agents. The completed P0 slice is described in MVP_SCOPE and the evidence matrix. No medical diagnosis, prescribing, covert surveillance or employee personality scoring is planned.

## P1 — small complete increments

| Increment | Future input → output contract | Acceptance gate |
|---|---|---|
| Office Manager | Imported synthetic email + approved catalog → typed line items, code-calculated quote and reply draft | Prices/taxes match catalog, injection/ACL tests, no automatic sending |
| DOCX / text PDF | Validated file → immutable source + extracted spans and citations | Format/size limits, accurate page anchors, parser isolation; scans/OCR separate |
| Meetings | Authorized transcript → minutes, evidence spans, proposed tasks | No task writes before approval, uncertain speakers and missing deadlines marked |
| Investor Room | Owner-approved evidence selection → versioned read-only snapshot | ID/date/scope/assumptions/revocation, separate role, no salaries or unrestricted internal documents; downloaded copies cannot be recalled |
| Reminders | Due task + work-hour policy → proposed/local reminder | Scheduling, deduplication, quiet hours, opt-out and delivery evidence |
| One read-only connector | Scoped credential + cursor → typed SourceSnapshot | Real integration test, source timestamp, availability and freshness; no write scopes |
| Encrypted backup/restore | Consistent DB/source manifest → encrypted off-site archive → isolated restore | Reviewed tool, separate keys, repeated restore drill and measured RPO/RTO |
| Orange Pi pilot | Vendor-supported hardware/runtime/model → the same provider contract | Gate-by-gate physical validation and measured workload; no device claim until passed |
| Database scaling | Validated PostgreSQL schema + worker leases | Migration/concurrency/load tests; SQLite behavior preserved |

## P2 — product directions retained

| Direction | Future contract | Readiness criterion / boundary |
|---|---|---|
| Sales | Lead + permitted catalog/CRM → qualification, quote draft, reminders | Deterministic prices/discount rules; human-approved outgoing messages |
| Support | Request + permitted evidence → cited answer or human handoff | Action scopes, explicit escalation, measured evidence correctness |
| Procurement | Comparable offers + previous prices/stock/terms → sourced comparison | Comparable currencies/units/taxes; no autonomous payments |
| Tenders | Tender specification + approved records → compliance matrix | Traceable criteria, missing evidence and human participation decision |
| Contracts | Versioned contracts → cited discrepancies, deadlines and fields | Qualified human review; no unsupported legal conclusions |
| HR / recruiter | Authorized application/portfolio → clarifying dialogue and structured review | Consent and access controls, no final automated rejection |
| HR onboarding mentor | Role + corporate training sources → cited learning guidance | Source permissions and freshness; no hidden performance ranking |
| Code assessment | Candidate-authorized artifacts → isolated assessment report | Voluntary participation, sandboxed execution, no unrestricted host access |
| MCP / A2A | Capability manifest + scoped tool contract → bounded request/result | Authentication, policy, timeout, audit and protocol integration tests |
| Marketing | Approved business facts + brief → campaign/copy proposals | Claims substantiated, review before publication |
| Design | Brand brief + permitted assets → design candidate through image provider | Separate licensing/approval path; no unsupported Orange Pi speed claim |
| Calls / voice | Authorized recording → transcript and verified working summary | Consent, retention rules; no covert monitoring or identity recognition |
| Programming | Allowed repository/task → reviewable changes | Isolated workspace, tests, human controls; business agent has no shell |
| Production / vision | Authorized images/docs → bounded observations | Separate hardware/data pilot, error analysis and quality gates |
| Process management | Confirmed business events → bottleneck analysis with evidence | Distinguish delay facts from character judgments; no “laziness” inference |
| Business continuity | Scoped travel snapshot + proposals → conflict-aware recovery | Version checks and reconciliation; no blind two-way overwrite |
| Agent quality control / AI Office Bench | Versioned workflow case sets → measured outcome reports | Separate demo, real LLM and device runs; repeated samples, human evidence labels |
| Hybrid retrieval / reranker | Permission-filtered dense+sparse candidates → ranked evidence | Measured recall/precision and ACL regressions; current dense path not called hybrid |

Industry packs: construction, service businesses, retail, manufacturing, logistics and clinic administration. Each requires a scoped data model, fixtures and real-world acceptance tests before any deployment claim.

Portable deployment candidate: management laptop with SSD and battery, independently validated Orange Pi inference node, separate 4G/5G router, primary internet and UPS. Maintain encrypted off-site copies and separately stored recovery keys. Redundant connectivity does not guarantee service in every outage. See continuity/RUNBOOK.md.

Next engineering priority: a repeated, human-labeled local-model evidence/abstention suite plus resolution or isolation of the remaining ChromaDB advisories before using real company data; then choose one read-only connector with an explicit source contract.
