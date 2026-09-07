# Continuity: implemented recovery and planned extensions

The company pilot now includes manual encrypted offline backup and restore. Follow [PILOT_BACKUP_RESTORE.md](PILOT_BACKUP_RESTORE.md) for the actual CLI, writer-stop requirement, passphrase handling, archive limits and empty-destination recovery. The Docker/Qdrant drill preserves company users, documents, quotes and tasks, rebuilds the index and invalidates old credentials. This is local recovery software, not an operational off-site backup service or high availability.

A future Travel mode carries an owner-selected read-only snapshot plus new proposals. A future Continuity mode works from a verified copy while the office is unavailable, displaying source timestamps and unavailable services. Travel synchronization, conflict reconciliation and automatic failover remain planned.

Scheduled off-site storage, separately managed recovery keys and repeated restore drills remain deployment work. RPO/RTO guarantees are not established by one successful synthetic recovery drill. Never copy a live SQLite `.db` file alone or bypass the shared/exclusive maintenance lock. Keep the encryption passphrase separately from its archive.
