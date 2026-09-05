# Contributing

Discuss scope with the owner before contributing while the distribution license is undecided. Keep changes small and include a reproducible test for business or security behavior. Run `make lint`, `make test` and relevant integration checks. Describe implementation and validation separately.

Use synthetic data only. Model output is a proposal; preserve server-side validation and durable approval. Database changes require a new Alembic revision: `app/schema_v1.py` is the frozen first migration. Review dependency and telemetry changes, not just direct API changes.

Do not add external integrations, deployment credentials or licensing terms without the owner's instruction.
