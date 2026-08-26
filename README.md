# resume-engine

Data-driven, ATS-safe CV and cover letter builder. Content lives in
`data/resume.yaml` and `data/cover_letter.yaml`; layout lives in
`src/resume_builder/templates/`. The rendering pipeline (YAML/JSON →
Jinja2 HTML → WeasyPrint PDF) is shared by a CLI, a JSON API, and a web
form, so there's one source of truth for how a resume gets laid out.

**Live:** [resume-engine-sud4.onrender.com](https://resume-engine-sud4.onrender.com)

## Design

- **Content/design separation** — editing a resume means editing
  `data/resume.yaml` or `data/cover_letter.yaml`. The Jinja2/CSS templates
  are never touched for a content change, so formatting can't break from a
  bad edit.
- **Validated data** — `src/resume_builder/models.py` defines `Resume` and
  `CoverLetter` as Pydantic models. Both YAML files and every JSON payload
  sent to the API are validated against them before rendering; a missing
  field or wrong type fails with a clear error instead of corrupting the
  PDF silently. `schema/resume.schema.json` is a JSON Schema generated
  from the same models, for editor autocomplete.
- **Tailorable per application** — every top-level resume section has a
  master on/off switch (`sections:`), and every entry (job, degree, skill
  group, cert, language) has its own `include:` flag. Nothing is deleted
  to tailor a resume, just toggled. The cover letter is expected to change
  per application instead — see [Editing content](#editing-content).
- **ATS-safe by construction** — both templates are single-column, no
  tables, no text boxes, no floats.
- **Reproducible builds** — a pinned Docker image (`docker/Dockerfile.dev`)
  backs the VS Code Dev Container and `docker-compose.yml`.

## How it's exposed

| Interface | Entry point | Use |
|---|---|---|
| CLI | `uv run resume-build render \| cover-letter` | Local rendering, scripting |
| API | `POST /api/resume/pdf`, `POST /api/cover-letter/pdf` | Any app or AI agent — JSON in, PDF out |
| Web form | `GET /` | Paste/edit JSON by hand, download a PDF |

All three call the same `render_html()` / `render_cover_letter_html()` in
`src/resume_builder/render.py` and validate against the same Pydantic
models — there's no separate logic path for any of them.

### CLI

```bash
uv sync
uv run resume-build render --data data/resume.yaml --out output/resume.pdf
uv run resume-build cover-letter --data data/cover_letter.yaml --out output/cover_letter.pdf
```

### Makefile shortcuts

| Command | Does |
|---|---|
| `make render` | Render `data/resume.yaml` → `output/resume.pdf` |
| `make render-html` | Same, plus `output/resume.html` for a quick preview |
| `make cover-letter` | Render `data/cover_letter.yaml` → `output/cover_letter.pdf` |
| `make cover-letter-html` | Same, plus `output/cover_letter.html` for a quick preview |
| `make lint` | `ruff check` + `ruff format --check` |
| `make format` | `ruff format` + `ruff check --fix` |
| `make typecheck` | `mypy --strict src` |
| `make test` | `pytest` with coverage |
| `make schema` | Regenerate `schema/resume.schema.json` from `models.py` |
| `make ci` | `lint` + `typecheck` + `test` — same checks CI runs |
| `make clean` | Remove build output and tool caches |

### API

`src/resume_builder/api.py` (FastAPI):

| Route | Method | Purpose |
|---|---|---|
| `/api/resume/pdf` | `POST` | Body: JSON matching `Resume` → `application/pdf` |
| `/api/cover-letter/pdf` | `POST` | Body: JSON matching `CoverLetter` → `application/pdf` |
| `/healthz` | `GET` | Liveness check (Render's health check path) |
| `/` | `GET` | Serves `web_static/index.html` |

```bash
curl -X POST https://resume-engine-sud4.onrender.com/api/resume/pdf \
  -H "Content-Type: application/json" \
  -d @data/resume.json \
  -o resume.pdf
```

A bad payload returns `422` with the Pydantic validation errors.

Run locally: `uv run uvicorn resume_builder.api:app --reload --port 8000`

## Deployment

Deployed on Render's free tier, built from `docker/Dockerfile.prod` via
the `render.yaml` Blueprint at the repo root. Pushes to `main` auto-deploy
(`autoDeployTrigger: commit`).

Free-tier instances sleep after 15 minutes of inactivity; the first
request after that takes ~30-60s to wake the container.

## Docker images

| | `Dockerfile.dev` | `Dockerfile.prod` |
|---|---|---|
| Used by | VS Code Dev Container, `docker-compose.yml` | Render, `docker-compose.prod.yml` |
| User | root | non-root (`uid 1000`) |
| Contains | compilers, git, ssh, `gh` CLI | only the API/web runtime |
| Purpose | interactive local development | serves the live API + web form |

```bash
docker compose -f docker-compose.prod.yml up --build   # http://localhost:8000
```

## Quick start (VS Code Dev Container)

1. Open this folder in VS Code.
2. Install the **Dev Containers** extension if you don't have it.
3. `Cmd/Ctrl+Shift+P` → **Dev Containers: Reopen in Container**.
4. Once inside: `uv run resume-build render` (and/or
   `uv run resume-build cover-letter`).

Your SSH agent and `~/.gitconfig` are forwarded into the container (see
`.devcontainer/devcontainer.json`), so `git push`/`git pull` and any GitHub
CLI usage work exactly as they do on the host — no keys copied into the
container, no extra setup.

`.vscode/tasks.json` wires Makefile targets into VS Code's task runner —
default build task (`Ctrl+Shift+B`) is `make render`; default test task
is `make test`; `Tasks: Run Task` lists the rest.

## Quick start (Docker Compose, no VS Code)

```bash
docker compose run --rm app uv run resume-build render
docker compose run --rm app uv run resume-build cover-letter
```

## Editing content

`data/resume.yaml` (start from `data/resume.template.yaml`): `contact`,
`summary`, `experience`, `projects`, `education`, `skills`,
`certifications`, `languages`, `photo`. `projects` covers personal,
academic, freelance, or open-source work — `organization`, `bullets`,
`technologies`, `links`.

Section visibility: `sections:` is a master boolean per top-level
section; every entry additionally carries its own `include: true|false`.
An entry renders only when both are true.

`data/cover_letter.yaml` (start from `data/cover_letter.template.yaml`):
`applicant_name`, `applicant_contact`, `date`, `recipient`, `role_title`,
`salutation`, `body_paragraphs`, `closing`. Unlike the resume, this is
meant to be rewritten per application — `role_title`, `recipient`, and
`body_paragraphs` change every time, they aren't toggled with `include`.
`sections.date` / `sections.recipient` can be set `false` when that
information isn't available for a given application.

Rebuild after any edit with `make render` / `make cover-letter`, or send
the edited JSON straight to the deployed API.

## Schema

`schema/resume.schema.json` is generated from `models.py` — covers both
`Resume` and `CoverLetter`, used for editor autocomplete and for
validating either YAML file outside a full render. Regenerate with
`make schema` after changing `models.py`.

## Testing & linting

Covered by the Makefile shortcuts above (`make test`, `make lint`,
`make typecheck`, `make ci`). `.pre-commit-config.yaml` wires the same
checks into a pre-commit hook (`pre-commit install` once per clone).

`.github/workflows/ci.yml` runs lint, typecheck, test, `pip-audit`, and a
Trivy config scan of `docker/Dockerfile.prod` on every push/PR.

## Project layout

```
.
├── .devcontainer/devcontainer.json   # VS Code Dev Container config
├── .vscode/tasks.json                # Makefile targets as VS Code tasks
├── .github/
│   ├── workflows/ci.yml              # lint, typecheck, test, security, dockerfile scan
│   └── dependabot.yml
├── src/resume_builder/
│   ├── models.py                     # Pydantic schema for resume.yaml + cover_letter.yaml
│   ├── render.py                     # YAML/JSON -> HTML (Jinja2) -> PDF (WeasyPrint)
│   ├── cli.py                        # `resume-build render / cover-letter ...`
│   ├── api.py                        # FastAPI: JSON -> PDF endpoints + web form
│   ├── templates/                    # resume.html.j2 + resume.css, cover_letter.html.j2 + cover_letter.css
│   ├── web_static/                   # index.html served at `/` by api.py
│   └── static/                       # optional photo lives here
├── data/
│   ├── resume.yaml
│   ├── resume.template.yaml
│   ├── cover_letter.yaml
│   └── cover_letter.template.yaml
├── schema/resume.schema.json         # JSON Schema generated from models.py
├── scripts/
│   ├── generate_schema.py
│   ├── entrypoint.dev.sh
│   └── welcome.sh
├── docker/
│   ├── Dockerfile.dev                # dev container image
│   └── Dockerfile.prod               # production image — deployed to Render
├── tests/test_render.py
├── output/                           # generated resume.pdf / resume.html / cover_letter.pdf / cover_letter.html
├── Makefile
├── render.yaml                       # Render Blueprint for the deployment
├── docker-compose.yml                # dev container service
└── docker-compose.prod.yml           # run the production image locally
```

## Formats

- **PDF** (`output/resume.pdf`, `output/cover_letter.pdf`) — the
  deliverables you send to employers.
- **HTML** (`output/resume.html`, `output/cover_letter.html`, optional) —
  useful for quick visual review without regenerating the whole PDF.
