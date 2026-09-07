# Offline pilot backup and restore

This release provides a manually operated recovery path for one company, on Linux/macOS. It is not scheduled offsite backup, high availability, or a hardware validation claim. Use the same application revision for restore; run migrations only after a successful recovery checkpoint.

## What is preserved

The SQLite online backup includes the company profile, users and roles, tasks and assignments, catalogs, quote revisions/calculations/approvals, document versions/anchors, workflow jobs and audit records. All immutable originals and extracted texts are included, including historical and revoked document versions. The vector index is derived and rebuilt from current non-revoked versions without changing source IDs or hashes. Historical originals remain available under existing access checks.

No raw login token files, setup token file, `.env`, endpoint URLs, API keys, model weights, logs, or Qdrant files enter the archive. A small manifest stores only mode, data mode, timezone, and embedding provider name. The company timezone also remains in its authoritative database profile. Configure endpoints and model choices explicitly at the recovery installation; this archive does not silently copy them. Run `doctor` and a document search before resuming work.

AES-256-GCM authenticates the complete archive and header. A random 16-byte salt and Scrypt (N=32768, r=8, p=1) derive the key from the passphrase; every archive receives a random 12-byte nonce. ZIP entries are stored without compression and authenticated before parsing. The v1 pilot limit is **256 MiB for the whole encrypted archive, 10,000 payload files, and 32 MiB per document file**. Keep the passphrase separately from the backup. A lost passphrase cannot be recovered.

## Create a backup

Complete initial company setup first. Stop **both app and worker** (and any running import/reindex CLI). They hold shared locks for their lifetime; backup obtains an exclusive `.maintenance.lock` in the same data directory and fails while any writer is active. Never bypass these locks with direct SQL or filesystem edits.

For the pilot Docker deployment:

```sh
mkdir -p .runtime/pilot-backups
chmod 700 .runtime/pilot-backups
docker compose -p ai-office-pilot -f compose.yaml -f compose.pilot.yaml stop app worker
docker compose -p ai-office-pilot -f compose.yaml -f compose.pilot.yaml run --rm --no-deps -v "$PWD/.runtime/pilot-backups:/backups" app python -m app.backup backup /backups/company.aioffice
docker compose -p ai-office-pilot -f compose.yaml -f compose.pilot.yaml start app worker
```

The command prompts twice for a passphrase of at least 16 characters. The output archive is mode `0600`; it never overwrites an existing archive. On Linux, the mounted output directory must be writable by container UID 10001. Stop/start the existing service rather than deleting its volumes.

For a local installation, after stopping uvicorn and the worker:

```sh
AI_OFFICE_DATA_MODE=pilot AI_OFFICE_DATA_DIR=.runtime/company uv run --frozen python -m app.backup backup .runtime/pilot-backups/company.aioffice
```

For unattended invocation supply `--passphrase-file /private/path` using a regular file with permissions `0600`. Never put the passphrase itself in command arguments, environment variables, logs, or Git. The command fails on missing or corrupted immutable sources; repair the source installation before relying on a backup.

## Restore into a new installation

Keep the source stopped for the final recovery snapshot. Create a **new empty application data directory/volume and a dedicated fresh Qdrant service**. Do not run `init` on the recovery target before restore: it would create a database and invalidate the empty-target requirement. The recovery Qdrant service must have no collections: even an existing empty collection is rejected before indexing. Existing collections are never modified or deleted by failed-restore cleanup.

Configure the target with `AI_OFFICE_DATA_MODE=pilot` (matching the archive), and explicitly select inference/embedding settings. Start Qdrant alone. Then, using the recovery deployment's environment and data volume:

```sh
python -m app.backup restore /backups/company.aioffice
```

Complete Docker example, preserving the source project and using a new project/volumes and port 8093:

```sh
docker compose -p ai-office-recovered -f compose.yaml -f compose.pilot.yaml up -d --no-build qdrant
docker compose -p ai-office-recovered -f compose.yaml -f compose.pilot.yaml run --rm --no-deps -v "$PWD/.runtime/pilot-backups:/backups:ro" app python -m app.backup restore /backups/company.aioffice
AI_OFFICE_PILOT_PORT=8093 docker compose -p ai-office-recovered -f compose.yaml -f compose.pilot.yaml up -d --no-build --no-deps --wait --wait-timeout 120 app worker
docker compose -p ai-office-recovered -f compose.yaml -f compose.pilot.yaml exec -T app python -m app.cli doctor
docker compose -p ai-office-recovered -f compose.yaml -f compose.pilot.yaml exec -T app python -c "from pathlib import Path; print(Path('/data/recovery-owner.token').read_text().strip())"
```

Open `http://127.0.0.1:8093` and use that local recovery token. The final command intentionally displays a credential only to the operator; do not copy its output into reports or Git. The archive mount is read-only, and restore prompts for its passphrase. Use a new project name if `ai-office-recovered` already has data. These commands use deterministic demonstration inference with a clean pilot workspace; for real models, include `-f compose.local.yaml`, configure and start its model gateway/runtime, and then run the same recovery steps. The real model endpoint and embedding model must be available before indexing.

For a host process, an example with a separately started local Qdrant endpoint is:

```sh
AI_OFFICE_DATA_MODE=pilot AI_OFFICE_DATA_DIR=.runtime/recovered-company AI_OFFICE_QDRANT_URL=http://127.0.0.1:6335 uv run --frozen python -m app.backup restore .runtime/pilot-backups/company.aioffice
```

An unavailable embedding provider or Qdrant aborts restore. Authentication, inventory, path/type/size checks, hashes and SQLite integrity checks precede publishing the recovered database. Restore builds in a private staging directory; publishes originals and a recovery credential before moving the database into place last. Normal exceptions remove unpublished staging and partial destination files. After a power loss, do not start an incomplete target: inspect it and retry into another empty target. This is not a cross-service distributed transaction.

All previous login credentials are marked revoked, sessions are removed, and stale worker heartbeats are cleared. A new local owner token is written to **`recovery-owner.token` with mode 0600**; only its path and the owner ID are printed. Read it locally, sign in as that owner, then issue new employee credentials. User accounts, roles and disabled states remain unchanged. The completed setup stays completed.

Start the recovered application and worker, run `doctor`, then verify:

1. Company name and both employee accounts remain correct.
2. A document search returns current citations; old versions and original PDF/DOCX downloads remain accessible to authorized users.
3. An approved quote exports with its original calculation and linked task/assignee.
4. Old login tokens are rejected; the new recovery token works.
5. A new task can be updated and appears in the briefing.

Retain the encrypted snapshot and a dated record of this drill. No recovery-time or recovery-point SLA is claimed yet. A separate offsite copy, retention policy, key escrow, scheduled backups and repeated production-volume recovery drills remain planned.
