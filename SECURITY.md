# Security posture

This is an alpha prototype for synthetic demonstration, not a production security certification. Do not put real personal, financial, medical or confidential company records into a public demo.

Authentication uses random local credentials whose SHA-256 digests are stored in SQLite. Browser sessions use HttpOnly/SameSite cookies and a server-checked CSRF token. Role and team scopes come from SQL. Revoking credentials invalidates associated sessions. Credentials expire after 30 days by default; sessions after 8 hours.

Report a suspected vulnerability privately to the repository owner through an available private GitHub reporting/contact channel. Do not include secrets or customer data in a public issue. No dedicated response SLA is promised.

See [threat model](docs/THREAT_MODEL.md), [dependency findings](docs/DEPENDENCY_REVIEW.md) and [operations](docs/OPERATIONS.md). Passing tests or a secret scan does not establish production safety.
