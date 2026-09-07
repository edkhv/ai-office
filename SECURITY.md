# Security posture

This alpha provides a synthetic demo and a separate company pilot, not a production security certification. Do not put real personal, financial, medical or confidential company records into a public demo.

Authentication uses random local credentials whose SHA-256 digests are stored in SQLite. Browser sessions use HttpOnly/SameSite cookies and a server-checked CSRF token. Role and team scopes come from SQL. Revoking credentials invalidates associated sessions. Credentials expire after 30 days by default; sessions after 8 hours.

Report a suspected vulnerability privately to the repository owner through an available private GitHub reporting/contact channel. Do not include secrets or customer data in a public issue. No dedicated response SLA is promised.

See [threat model](docs/THREAT_MODEL.md), [dependency findings](docs/DEPENDENCY_REVIEW.md) and [operations](docs/OPERATIONS.md). Passing tests or a secret scan does not establish production safety.

A company pilot starts empty and requires a locally obtained one-time bootstrap token. Public setup never returns that token and closes after owner creation. Owner administration rechecks active identity and organization in the write transaction. Disabling an account or changing its role/team revokes its credentials and sessions immediately; the final active owner cannot be removed.

The core image excludes CrewAI/ChromaDB and has a zero-finding frozen dependency audit. Four unresolved ChromaDB advisories remain in the separate optional SDK runtime. Docker isolation denies that runtime business-volume access and unrestricted egress; only scoped data for the current model step crosses the interface. This reduces exposure without claiming those advisories are fixed. The model gateway validates request routes, model names and bounded payloads.

Manual backups use authenticated encryption and a separately retained passphrase. Offline maintenance locks prevent concurrent application writers. Restore requires an empty destination and revokes old credentials; public setup remains closed. See the [backup runbook](docs/continuity/PILOT_BACKUP_RESTORE.md) for archive limits, key handling and the validated recovery procedure.
