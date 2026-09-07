# Company pilot / Пилот компании

The pilot is a separate single-company workspace. It starts without Northline users, documents, catalogs, tasks or financial fixtures. `AI_OFFICE_DATA_MODE=pilot` selects company data; `AI_OFFICE_MODE=demo` independently selects deterministic model behavior. This lets you test document imports, calculations, approvals and task control without buying hardware or using paid APIs. Financial metrics remain unavailable until an accounting source is implemented.

```sh
make pilot
make pilot-setup-token
```

Open http://127.0.0.1:8091. Enter the private setup token, company name, owner name and timezone. Save the owner access token shown once, then sign in. Setup cannot be repeated or taken over after completion. `make pilot-setup-token` rotates the unfinished setup token; it does not reset an existing company.

In **People and access / Сотрудники и доступ**, add employees and give each their personal token privately. The supported roles are owner, manager and employee; teams are operations and procurement. Owners can rename accounts, change roles/teams, disable access and rotate tokens. Changing role/team/access revokes existing sessions and credentials immediately. At least one active owner must remain. Tokens do not appear in user lists or audit records.

The default pilot offers deterministic explicit `SKU × quantity` quote suggestions and lexical/hash document retrieval. Free-form executive planning requires configured local inference; it never substitutes the Northline procurement fixture. Choose **Commercial proposals / Коммерческие предложения** for the complete no-model path: upload catalog → review positions → calculate → select a named employee and deadline → approve → track the task.

For local models, prepare Ollama and the selected model/embedding files, then use `make pilot-local`. The Compose overlay runs CrewAI in a separate image with no business-data mount; a restricted model gateway provides inference access. Missing runtime fails visibly. See [model providers](model-providers.md) and [dependency findings](DEPENDENCY_REVIEW.md). Four SDK-side ChromaDB advisories remain; isolation does not mean they are fixed or that this is a production security certification.

`make pilot-down` stops the pilot and preserves its volumes. `make demo` remains separate at port 8090. Do not switch an existing database between demo and pilot; use separate Compose projects/volumes. A matching-mode guard rejects accidental reuse. Recover an existing user's token locally with `make pilot-credential ROLE=<actor-id>`; identifiers are shown in authenticated user API records. This is a local administrator action, not a public token recovery endpoint.

Manual encrypted backup and restore are implemented with an offline maintenance lock. Follow the exact stop/backup/restore/reindex procedure in [PILOT_BACKUP_RESTORE.md](continuity/PILOT_BACKUP_RESTORE.md). Keep the passphrase separately. An initial pilot cannot be backed up before owner setup is complete.

## Reproducible browser evidence

`scripts/pilot_demo.py` targets a **fresh test-only** project `ai-office-pilot-validation` at port 8092, not the user's pilot. It creates explicitly synthetic test input, tests setup, two employees, disabled access, a document/catalog, an approved quote and assigned overdue task. Override `AI_OFFICE_PILOT_BASE` and `AI_OFFICE_PILOT_PROJECT` together when selecting another isolated test installation. Run it only against a fresh workspace; it never resets a completed company. Credentials stay in private `.runtime` output and are excluded from screenshots and reports.

Target device status remains **Target hardware; not yet validated on device.** Local AI Station 96–128 GB is a proposed capacity range, not a tested device configuration.
