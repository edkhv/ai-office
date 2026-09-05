FROM python:3.11.15-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 UV_COMPILE_BYTECODE=0 \
    OTEL_SDK_DISABLED=true CREWAI_DISABLE_TELEMETRY=true CREWAI_TRACING_ENABLED=false DO_NOT_TRACK=1 \
    AI_OFFICE_DATA_DIR=/data
RUN pip install --no-cache-dir uv==0.11.33 && useradd --uid 10001 --create-home office && mkdir /data && chown office:office /data
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY --chown=office:office app ./app
COPY --chown=office:office migrations ./migrations
COPY --chown=office:office examples ./examples
COPY --chown=office:office alembic.ini ./
RUN uv sync --frozen --no-dev
ENV PATH="/srv/.venv/bin:$PATH"
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
