# resume-engine

Data-driven, ATS-safe CV and cover letter builder. Content lives in
`data/resume.yaml` and `data/cover_letter.yaml`; layout lives in
`src/resume_builder/templates/`. Edit the YAML (by hand, or via an AI
agent), rebuild, get polished PDFs. No Word/Europass wrestling required.

## Why this structure

- **Content/design separation** — an AI agent (or you) only ever edits
  `data/resume.yaml` or `data/cover_letter.yaml`, plain structured files.
  The HTML/CSS templates stay untouched, so formatting can never break from
  a bad edit.
- **Validated data** — both YAML files are validated against Pydantic
  schemas (`src/resume_builder/models.py`) before rendering, so a missing
  field or wrong type fails the build loudly instead of corrupting the PDF
  silently. A matching JSON Schema (`schema/resume.schema.json`) is
  generated from the same models for editor autocomplete/validation.
- **Tailorable per application** — the resume's every section has a master
  on/off switch, and every entry (job, degree, skill group, cert, language)
  has its own `include` flag, so it can be tailored per job posting without
  deleting content. The cover letter is *designed* to be edited per
  application — `role_title`, `recipient`, and `body_paragraphs` are
  expected to change for every job. See
  [Tailoring sections](#tailoring-sections-per-application).
- **ATS-safe by construction** — both templates are single-column, no
  tables, no text boxes, no floats — the layout style that parses reliably
  across Workday / Greenhouse / Lever / iCIMS / Taleo.
- **Reproducible** — everything runs in a pinned Docker image via a VS Code
  Dev Container, so "it works on my machine" isn't a variable.
- **CI-built PDFs** — push a change to `data/resume.yaml` or
  `data/cover_letter.yaml` and GitHub Actions rebuilds both `output/resume.pdf`
  and `output/cover_letter.pdf` automatically (see below).

## Quick start (local, with uv)

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
  Resume (PDF + HTML)*, *Render Cover Letter (PDF)*, *Render Cover Letter
  (PDF + HTML)*, *Lint*, *Format*, *Typecheck*, *CI*.

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

## Quick start (Docker Compose, no VS Code)

```bash
docker compose run --rm app uv run resume-build render
docker compose run --rm app uv run resume-build cover-letter
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
`experience`, `projects`, `education`, `skills`, `certifications`,
`languages`, plus a `photo` field (filename inside
`src/resume_builder/static/`, or `null` to omit the photo entirely).

`projects` is for personal, academic, freelance, or open-source work that
isn't a paid job — each entry supports an optional `organization` (e.g.
"Associated with X University"), achievement `bullets`, a `technologies`
keyword list, and clickable `links` (repo, live demo, published model,
etc.). Add a new list item under `projects:` any time you ship something
new; nothing else needs to change.

Change something, rebuild, check `output/resume.pdf`. Push to `develop` and
CI rebuilds and commits the PDF automatically — see
`.github/workflows/build-resume.yml`.

### Tailoring sections per application

Two independent, additive controls in `resume.yaml`:

- **`sections:`** — a master boolean per top-level section (`summary`,
  `experience`, `projects`, `education`, `skills`, `certifications`,
  `languages`, `photo`). Set one to `false` to drop that whole section from
  the PDF.
- **`include:`** — every entry in `experience`, `projects`, `education`,
  `skills`, `certifications`, and `languages` carries its own
  `include: true|false`.
  Set to `false` to hide a single entry (e.g. an older job) while keeping
  the rest of the section and the data itself.

An entry only renders when both its section's master switch and its own
`include` flag are true — nothing is ever deleted, just toggled off.

## Editing your cover letter

Everything is in `data/cover_letter.yaml` — start from
`data/cover_letter.template.yaml` for a blank, commented starting point.
Fields: `applicant_name`, `applicant_contact` (reuses the same shape as the
resume's `contact`), `date`, `recipient` (name/title/company/address),
`role_title`, `salutation`, `body_paragraphs`, and `closing`.

Unlike the resume, a cover letter is meant to change **every application**
— `role_title`, `recipient`, and `body_paragraphs` should be rewritten per
job, not toggled on/off. `sections.date` and `sections.recipient` can be set
to `false` if you don't have that information for a given application (e.g.
no named recipient).

Change something, rebuild, check `output/cover_letter.pdf`. Push to
`develop` and CI rebuilds and commits the PDF automatically — see
`.github/workflows/build-resume.yml`.

## Schema

`schema/resume.schema.json` is a JSON Schema generated from the Pydantic
models in `src/resume_builder/models.py` (covering both the `Resume` and
`CoverLetter` models), useful for editor autocomplete and validating either
YAML file outside of a full render. Regenerate it after changing
`models.py`:

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

Point an agent at `data/resume.yaml` and/or `data/cover_letter.yaml` with
instructions to only modify those files (never the templates). A sensible
workflow:

1. Agent reads `data/resume.yaml` and/or `data/cover_letter.yaml` + a
   target job description.
2. For the resume: agent proposes edits to `bullets`/`skills`/`summary`,
   and toggles `include`/`sections` flags to fit the role, without
   inventing new facts. For the cover letter: agent fills in `role_title`,
   `recipient`, and rewrites `body_paragraphs` for the specific
   application, again without inventing facts.
3. `uv run resume-build render` and/or `uv run resume-build cover-letter`
   to preview locally, or open a PR — CI will build fresh PDFs
   automatically so you can review before merging.

## Project layout

```
.
├── .devcontainer/devcontainer.json   # VS Code Dev Container config
├── .vscode/tasks.json                # Ctrl+Shift+B → make render, + other task shortcuts
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                    # lint, typecheck, test, security, dockerfile scan
│   │   ├── docker.yml                # build, scan & push production image to GHCR
│   │   └── build-resume.yml          # render PDFs on data changes, commit back
│   └── dependabot.yml
├── src/resume_builder/
│   ├── models.py                     # Pydantic schema for resume.yaml + cover_letter.yaml
│   ├── render.py                     # YAML -> HTML (Jinja2) -> PDF (WeasyPrint)
│   ├── cli.py                        # `resume-build render / cover-letter ...`
│   ├── templates/                    # resume.html.j2 + resume.css, cover_letter.html.j2 + cover_letter.css
│   └── static/                       # optional photo lives here
├── data/
│   ├── resume.yaml                   # <-- edit this
│   ├── resume.template.yaml          # blank starting point
│   ├── cover_letter.yaml             # <-- edit this per application
│   └── cover_letter.template.yaml    # blank starting point
├── schema/resume.schema.json         # JSON Schema generated from models.py
├── scripts/
│   ├── generate_schema.py            # regenerates schema/resume.schema.json
│   ├── entrypoint.dev.sh
│   └── welcome.sh
├── docker/
│   ├── Dockerfile.dev                # dev container image (VS Code / docker compose)
│   └── Dockerfile.prod               # production image (published to GHCR)
├── tests/test_render.py              # smoke tests for the render pipeline
├── output/                           # generated resume.pdf / resume.html / cover_letter.pdf / cover_letter.html
├── Makefile                          # shortcuts for common commands
├── docker-compose.yml                # dev container service
└── docker-compose.prod.yml           # run the production image locally
```

## Formats

- **PDF** (`output/resume.pdf`, `output/cover_letter.pdf`) — the
  deliverables you send to employers.
- **HTML** (`output/resume.html`, `output/cover_letter.html`, optional) —
  useful for quick visual review without regenerating the whole PDF.