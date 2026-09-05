# Continuity design — planned, not implemented

Office mode uses one protected local node. A future Travel mode carries an owner-selected read-only snapshot plus new proposals. Continuity mode works from the latest verified copy when the office is unavailable, displaying as_of, last_sync_at and unavailable sources. Neither travel synchronization nor encrypted backup is shipped in P0.

Planned backup procedure: select a reviewed encryption/backup tool; store an encrypted copy off-site; hold recovery keys separately; create a consistent SQLite backup using its backup API or a quiesced application; include immutable source versions with a manifest and hashes. Restore to an isolated machine, verify database revision/manifest/access controls, reindex Qdrant from confirmed sources, verify the canary and an approved workflow, rotate credentials as appropriate. Never copy a live .db file alone. No custom cryptography.

RPO, RTO and restore duration: unmeasured. Record them only after repeated recovery drills. A synthetic unencrypted export, if introduced, must never be advertised as production backup. No export command currently exists.

Separate 4G/5G router, primary connection and UPS are deployment candidates, not guaranteed availability. A laptop's battery does not protect every component. Portability must not make one device the only copy of the business.

Future reconnect contract: read-only versioned snapshot; new ActionProposals in an outbox; recheck object versions, role and exact approval before remote writes. Ambiguous timeouts → needs_reconciliation. No blind two-way CRM overwrite or last-write-wins for critical data. Discarding/expiring access does not erase an already decrypted offline copy; remote revocation is not remote wipe.
