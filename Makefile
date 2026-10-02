.PHONY: render render-html cover-letter cover-letter-html lint format typecheck test spell audit schema web-assets hooks serve-api repomix ci clean

render:
	uv run resume-build render --data data/resume.yaml --out output/resume.pdf

render-html:
	uv run resume-build render --data data/resume.yaml --out output/resume.pdf --html output/resume.html

cover-letter:
	uv run resume-build cover-letter --data data/cover_letter.yaml --out output/cover_letter.pdf

cover-letter-html:
	uv run resume-build cover-letter --data data/cover_letter.yaml --out output/cover_letter.pdf --html output/cover_letter.html

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy src

test:
	uv run pytest --cov=resume_builder --cov-report=term-missing

spell:
	uv run pre-commit run cspell --all-files

audit:
	bash scripts/audit.sh runtime
	bash scripts/audit.sh dev

schema:
	uv run python scripts/generate_schema.py

# Rebuilds the committed CSS / fonts / js-yaml under src/resume_builder/web_static/assets/.
# Needs Node 20+; only required after changing web/ or index.html / app.js classes.
web-assets:
	cd web && npm ci && npm run build

# Turns on the git hooks in this clone (the dev container does this on every start).
hooks:
	uv run pre-commit install --install-hooks

serve-api:
	uv run uvicorn resume_builder.api:app --host 0.0.0.0 --port 8000 --reload --reload-dir src

repomix:
	npx --yes repomix@latest

ci: lint typecheck test spell

clean:
	rm -rf output/*.pdf output/*.html .pytest_cache .ruff_cache .mypy_cache .coverage
