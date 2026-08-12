# resume-engine

Data-driven, ATS-safe CV builder. Content lives in `data/resume.yaml`; layout
lives in `src/resume_builder/templates/`. Edit the YAML (by hand, or via an
AI agent), rebuild, get a polished PDF. No Word/Europass wrestling required.

## Why this structure

- **Content/design separation** — an AI agent (or you) only ever edits
  `data/resume.yaml`, a plain structured file. The HTML/CSS template stays
  untouched, so formatting can never break from a bad edit.
- **Validated data** — `resume.yaml` is validated against a Pydantic schema
  (`src/resume_builder/models.py`) before rendering, so a missing field or
  wrong type fails the build loudly instead of corrupting the PDF silently.
  A matching JSON Schema (`schema/resume.schema.json`) is generated from the
  same models for editor autocomplete/validation.
- **Tailorable per application** — every section has a master on/off switch,
  and every entry (job, degree, skill group, cert, language) has its own
  `include` flag, so a résumé can be tailored per job posting without
  deleting content. See [Tailoring sections](#tailoring-sections-per-application).
- **ATS-safe by construction** — the template is single-column, no tables,
  no text boxes, no floats — the layout style that parses reliably across
  Workday / Greenhouse / Lever / iCIMS / Taleo.
- **Reproducible** — everything runs in a pinned Docker image via a VS Code
  Dev Container, so "it works on my machine" isn't a variable.
- **CI-built PDF** — push a change to `data/resume.yaml` and GitHub Actions
  rebuilds `output/resume.pdf` automatically (see below).

## Quick start (local, with uv)

```bash
uv sync
uv run resume-build render --data data/resume.yaml --out output/resume.pdf
```

### Makefile shortcuts

| Command | Does |
|---|---|
| `make render` | Render `data/resume.yaml` → `output/resume.pdf` |
| `make render-html` | Same, plus `output/resume.html` for a quick preview |
| `make lint` | `ruff check` + `ruff format --check` |
| `make format` | `ruff format` + `ruff check --fix` |
| `make typecheck` | `mypy src` |
| `make test` | `pytest` with coverage |
| `make schema` | Regenerate `schema/resume.schema.json` from `models.py` |
| `make ci` | `lint` + `typecheck` + `test`, same as CI runs |
| `make clean` | Remove build output and tool caches |

### VS Code tasks

`.vscode/tasks.json` wires the Makefile targets into VS Code's task runner:

- **Ctrl+Shift+B** (**Cmd+Shift+B** on macOS) — runs the default build task,
  **Render Resume (PDF)** (`make render`), straight away with no menu.
- **Ctrl+Shift+P** → **Tasks: Run Test Task** — runs the default test task,
  **Test** (`make test`).
- **Ctrl+Shift+P** → **Tasks: Run Task** — lists everything else: *Render
  Resume (PDF + HTML)*, *Lint*, *Format*, *Typecheck*, *CI*.

## Quick start (VS Code Dev Container)

1. Open this folder in VS Code.
2. Install the **Dev Containers** extension if you don't have it.
3. `Cmd/Ctrl+Shift+P` → **Dev Containers: Reopen in Container**.
4. Once inside: `uv run resume-build render`.

Your SSH agent and `~/.gitconfig` are forwarded into the container (see
`.devcontainer/devcontainer.json`), so `git push`/`git pull` and any GitHub
CLI usage work exactly as they do on the host — no keys copied into the
container, no extra setup.

## Quick start (Docker Compose, no VS Code)

```bash
docker compose run --rm app uv run resume-build render
```

## Production image

`docker/Dockerfile.dev` and `docker/Dockerfile.prod` are two separate,
purpose-built images:

| | `Dockerfile.dev` | `Dockerfile.prod` |
|---|---|---|
| Used by | VS Code Dev Container, `docker-compose.yml` | CI publish, `docker-compose.prod.yml` |
| User | root | non-root (`uid 1000`) |
| Contains | compilers, git, ssh, `gh` CLI | only the render runtime |
| Purpose | interactive local development | the artifact that actually ships |

The production image is what `.github/workflows/docker.yml` builds,
SBOM/provenance-signs, Trivy-scans, and publishes to
`ghcr.io/<owner>/resume-engine` on every merge to `main`.

Run it locally without touching VS Code or `uv`:

```bash
docker compose -f docker-compose.prod.yml run --rm resume-engine
```

or, once published:

```bash
docker run --rm \
  -v "$(pwd)/data:/app/data:ro" \
  -v "$(pwd)/output:/app/output" \
  ghcr.io/<owner>/resume-engine:latest
```

## Editing your resume

Everything is in `data/resume.yaml` — start from `data/resume.template.yaml`
for a blank, commented starting point. Sections: `contact`, `summary`,
`experience`, `education`, `skills`, `certifications`, `languages`, plus a
`photo` field (filename inside `src/resume_builder/static/`, or `null` to
omit the photo entirely).

Change something, rebuild, check `output/resume.pdf`. Push to `main` and CI
rebuilds and commits the PDF automatically — see `.github/workflows/build-resume.yml`.

### Tailoring sections per application

Two independent, additive controls in `resume.yaml`:

- **`sections:`** — a master boolean per top-level section (`summary`,
  `experience`, `education`, `skills`, `certifications`, `languages`,
  `photo`). Set one to `false` to drop that whole section from the PDF.
- **`include:`** — every entry in `experience`, `education`, `skills`,
  `certifications`, and `languages` carries its own `include: true|false`.
  Set to `false` to hide a single entry (e.g. an older job) while keeping
  the rest of the section and the data itself.

An entry only renders when both its section's master switch and its own
`include` flag are true — nothing is ever deleted, just toggled off.

## Schema

`schema/resume.schema.json` is a JSON Schema generated from the Pydantic
models in `src/resume_builder/models.py`, useful for editor autocomplete
and validating `resume.yaml` outside of a full render. Regenerate it after changing `models.py`:

```bash
make schema   # or: uv run python scripts/generate_schema.py
```

## Testing & linting

```bash
make test        # pytest, smoke-tests the render pipeline (tests/test_render.py)
make lint         # ruff check + ruff format --check
make typecheck    # mypy src
make ci           # all three, same checks CI runs
```

`.pre-commit-config.yaml` wires these into a pre-commit hook — run
`pre-commit install` once per clone to get them on every commit.

## Using an AI agent to edit this

Point an agent at `data/resume.yaml` with instructions to only modify that
file (never the templates). A sensible workflow:

1. Agent reads `data/resume.yaml` + a target job description.
2. Agent proposes edits to `bullets`/`skills`/`summary`, and toggles
   `include`/`sections` flags to fit the role, without inventing new facts.
3. `uv run resume-build render` to preview locally, or open a PR — CI will
   build a fresh PDF automatically so you can review before merging.

## Project layout

```
.
├── .devcontainer/devcontainer.json   # VS Code Dev Container config
├── .vscode/tasks.json                # Ctrl+Shift+B → make render, + other task shortcuts
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                    # lint, typecheck, test, security, dockerfile scan
│   │   ├── docker.yml                # build, scan & push production image to GHCR
│   │   └── build-resume.yml          # render PDF on data changes, commit back
│   └── dependabot.yml
├── src/resume_builder/
│   ├── models.py                     # Pydantic schema for resume.yaml
│   ├── render.py                     # YAML -> HTML (Jinja2) -> PDF (WeasyPrint)
│   ├── cli.py                        # `resume-build render ...`
│   ├── templates/                    # resume.html.j2 + resume.css
│   └── static/                       # optional photo lives here
├── data/
│   ├── resume.yaml                   # <-- edit this
│   └── resume.template.yaml          # blank starting point
├── schema/resume.schema.json         # JSON Schema generated from models.py
├── scripts/
│   ├── generate_schema.py            # regenerates schema/resume.schema.json
│   ├── entrypoint.dev.sh
│   └── welcome.sh
├── docker/
│   ├── Dockerfile.dev                # dev container image (VS Code / docker compose)
│   └── Dockerfile.prod               # production image (published to GHCR)
├── tests/test_render.py              # smoke tests for the render pipeline
├── output/                           # generated resume.pdf / resume.html
├── Makefile                          # shortcuts for common commands
├── docker-compose.yml                # dev container service
└── docker-compose.prod.yml           # run the production image locally
```

## Formats

- **PDF** (`output/resume.pdf`) — the deliverable you send to employers.
- **HTML** (`output/resume.html`, optional) — useful for quick visual
  review without regenerating the whole PDF.