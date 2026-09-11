.PHONY: setup dev demo test build lint
setup:            ## install api + web deps (needs uv + node)
	cd api && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
	cd web && npm install
dev:              ## api on :4800 (reload) + vite on :5173 (proxies /api)
	(cd api && .venv/bin/uvicorn tacit.main:app --reload --port 4800) & (cd web && npm run dev)
demo:             ## seeded demo org on :4800
	cd web && npm run build && cd ../api && .venv/bin/python -m tacit.cli demo --db demo.db
test:             ## backend tests + typecheck
	cd api && .venv/bin/python -m pytest -q
	cd web && npx tsc -p tsconfig.app.json --noEmit
build:            ## production front end
	cd web && npm run build
migrate:          ## alembic upgrade head
	cd api && .venv/bin/alembic upgrade head
