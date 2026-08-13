.PHONY: render render-html cover-letter cover-letter-html lint format typecheck test schema repomix ci clean

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

schema:
	uv run python scripts/generate_schema.py

repomix:
	npx --yes repomix@latest

ci: lint typecheck test

clean:
	rm -rf output/*.pdf output/*.html .pytest_cache .ruff_cache .mypy_cache .coverage