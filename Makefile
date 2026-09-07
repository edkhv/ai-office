.PHONY: demo local down credential test lint integration-test eval-demo smoke doctor screenshots customer-demo check-publication pilot pilot-setup-token pilot-credential pilot-down pilot-local pilot-demo pilot-lifecycle
ROLE ?= owner
PILOT = docker compose -p ai-office-pilot -f compose.yaml -f compose.pilot.yaml

demo:
	docker compose up -d --build --wait --wait-timeout 180
	@echo 'Open http://127.0.0.1:8090 · Generate a private login token with: make credential'
local:
	docker compose -p ai-office-local -f compose.yaml -f compose.local.yaml up -d --build --wait --wait-timeout 240
credential:
	@docker compose exec -T app python -m app.cli credential $(ROLE)
down:
	docker compose down
test:
	uv run --frozen pytest -m 'not integration and not local_llm' --junitxml=.runtime/test-results.xml --cov=app --cov-report=term-missing
lint:
	uv run --frozen ruff check .
	uv run --frozen ruff format --check .
	uv run --frozen mypy
integration-test:
	uv run --frozen python scripts/integration.py
eval-demo:
	uv run --frozen python -m evals.run
smoke:
	uv run --frozen python scripts/smoke.py
doctor:
	docker compose exec -T app python -m app.cli doctor
screenshots:
	uv run --frozen python scripts/screenshots.py
customer-demo:
	uv run --frozen python scripts/customer_demo.py
check-publication:
	uv run --frozen python scripts/check_publication.py

pilot:
	$(PILOT) up -d --build --wait --wait-timeout 180
	@echo 'Open http://127.0.0.1:8091 · Retrieve the private setup token with: make pilot-setup-token'
pilot-setup-token:
	@$(PILOT) exec -T app python -m app.cli setup-token
pilot-credential:
	@$(PILOT) exec -T app python -m app.cli credential $(ROLE)
pilot-down:
	$(PILOT) down
pilot-local:
	$(PILOT) -f compose.local.yaml up -d --build --wait --wait-timeout 240
pilot-demo:
	uv run --frozen python scripts/pilot_demo.py

pilot-lifecycle:
	uv run --frozen python scripts/pilot_lifecycle.py
