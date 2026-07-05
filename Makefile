.PHONY: install dev test verify neo4j-up neo4j-down

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e 'apps/api[dev]'
	npm --prefix apps/web install
	npm --prefix tests/e2e install

dev:
	@echo "Run the API and web app in separate terminals:"
	@echo ".venv/bin/uvicorn app.main:app --app-dir apps/api/src --reload"
	@echo "npm --prefix apps/web run dev"

test:
	.venv/bin/python -m pytest apps/api/tests -v
	npm --prefix apps/web test -- --run

verify: neo4j-up
	.venv/bin/python scripts/import_core_graph.py
	RUN_NEO4J_INTEGRATION=1 .venv/bin/python -m pytest apps/api/tests -v
	npm --prefix apps/web test -- --run
	npm --prefix apps/web run typecheck
	npm --prefix apps/web run build
	.venv/bin/python scripts/import_core_graph.py --validate-only
	npm --prefix tests/e2e test

neo4j-up:
	docker compose up -d neo4j

neo4j-down:
	docker compose down
