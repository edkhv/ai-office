# ADR 0001: preserve the stack, separate decisions from actions

Accepted for alpha. Retain Python 3.11, FastAPI/Pydantic, CrewAI, Ollama, LangChain/Qdrant and pytest. Add SQLAlchemy/Alembic/SQLite for business state and one separate worker. Use Jinja2 plus local vanilla JS/CSS. Demo replaces generation and embeddings, not state or policy.

Rationale: the source is a small document assistant. Durable local workflows and verifiable figures add business value without introducing another agent framework or a distributed control plane. CrewAI is confined to bounded proposal/review tasks; SQL owns permissions, approval, execution and audit.

Tradeoffs: a single worker and SQLite serialize writes; no high availability. Compatible HTTP requires a verified contract; no automatic cloud fallback. Documents support only Markdown/TXT. Hash demo retrieval is deliberately limited. Revisit PostgreSQL/multi-worker scheduling, sparse/dense retrieval, connectors and backup only through separately tested increments.
