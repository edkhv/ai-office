# Threat model and alpha limits

Assets: source documents, credentials, plans, approvals, tasks and business records. Trusted: installation administrator, host OS, approved runtime endpoint and application code. Untrusted: command text, uploaded documents, retrieved content, model output, API input and other local users without credentials.

| Risk | Current control | Remaining boundary |
|---|---|---|
| Lost portable node | Credentials expire; roles; local data separated from code | No disk encryption, remote wipe or secure travel snapshots implemented |
| Token theft / replay | Random 288-bit tokens, digests in DB, revocation, short browser sessions, login limit | Token files are local secrets; compromised OS can read them |
| Cross-role source leak / IDOR | SQL role checks → Qdrant version filter → source recheck, including persisted answers | Authorized users can copy data; cached screenshots/downloads cannot be recalled |
| Prompt injection | No model tools; document text stays evidence; dispatch and approval outside model | Models can still produce poor prose; citations do not prove entailment |
| Wrong or duplicate action | Schema + exact hash/version/expiry + active-role check + SQL transaction + unique keys | Only local task creation is supported; external exactly-once is not promised |
| Stale/revoked evidence | Current source/version checks before issuing answers and links | Data quality is only as good as imported sources |
| Logs leaking content | Safe JSON metadata; SDK replay logging and tracing disabled | Host administrator can inspect application DB/files |
| Network redirection | Admin host allowlist, no credentials in URL, HTTP redirects disabled, trust_env=False | Hostname resolution is not pinned; an allowlist is not a firewall |
| XSS / CSRF | textContent/plain text rendering, CSP, HttpOnly/SameSite cookies, CSRF header check | Local HTTP exception for demo; HTTPS is required remotely |
| Dependency compromise | Lockfile, current audit and known-findings disclosure | See DEPENDENCY_REVIEW; no supply-chain certification |
| SQLite/worker crash | WAL, short writes, leases/fencing, idempotent local commits | One-node availability; no HA or production backup |
| Upload/resource abuse | Body/file/type/encoding limits, bounded queue, generation budget | Rate limits and resource quotas need production load testing |

Audit is append-only through API. SQLite administrators can edit it; no cryptographic immutability is claimed. Scope tests cover owner, manager and employee. Investor is not an alias for owner and has no implemented access route.
