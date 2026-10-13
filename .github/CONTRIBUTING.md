# Contributing & repository operations

Source of truth for **branching, protection rules, CI/CD and dependency
automation**. Some pieces live in GitHub / Render settings rather than in the
repo; those are called out as one-time setup. The project overview and local
commands are in the root [`README.md`](../README.md).

---

## 1. Branching model

```text
feat/* | fix/* | chore/* | docs/* | ci/*  ─PR─▶  develop  ─PR─▶  main  ─▶  Render
```

| Branch      | Role                                         | Direct push? | Accepts PRs from              |
| ----------- | -------------------------------------------- | ------------ | ----------------------------- |
| `main`      | Production — Render deploys it once CI is green | ❌ (PR only) | `develop` **only**            |
| `develop`   | Integration branch; Dependabot targets it    | ❌ (PR only) | feature branches, Dependabot  |
| feature     | Short-lived work branches off `develop`      | ✅           | —                             |

```bash
git fetch origin
git switch -c feat/short-name origin/develop
git branch --unset-upstream          # don't let a bare `git push` target develop
# ...work, then:
make ci
git push -u origin feat/short-name   # open a PR into develop
```

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
`feat(web): …`, `fix(api): …`, `ci: …`, `chore(deps): …`, imperative, subject
≤ 72 characters, body explains *why*.

Changing the web form's styling (`web/`, or the classes in `index.html` / `app.js`) needs
`make web-assets` (Node 20+) to regenerate the committed CSS; no other workflow needs Node.

Install the hooks once per clone with `make hooks` (the dev container does it on every start, and
re-checks before each `git commit`). Besides
ruff, cspell and whitespace fixers, a local hook re-renders `output/resume.pdf` when
`data/resume.yaml` or a template changes — if it modifies files the commit
stops once; re-stage and commit again.

### Spelling

[`cspell.json`](../cspell.json) is the one config used by CI, the pre-commit
hook, `make spell` and the VS Code *Code Spell Checker* extension. When it
flags a word that is correct, add it — don't disable the check:

| Word is… | Add it to |
| --- | --- |
| A tool, package, env var or code identifier | [`.cspell/project-words.txt`](../.cspell/project-words.txt) |
| A name, organization or term from the resume / cover letter | [`.cspell/resume-words.txt`](../.cspell/resume-words.txt) — only applies under `data/` |
| A one-off in a single file | an inline `cspell:ignore word` comment in that file |

Keep both lists sorted. Words that only appear in machine-maintained strings
(action pins, extension IDs, label colors) are skipped by patterns in
`cspell.json` instead of being listed.

---

## 2. GitHub settings (one-time setup)

Some of the rules above live in GitHub's settings, not in the repository.
[`SETTINGS.md`](SETTINGS.md) lists every one of them: General, Actions
permissions, Environments, Advanced Security, secrets and the two rulesets
(importable from [`rulesets/`](rulesets/)). In short:

- `develop` is the default branch. Neither `develop` nor `main` accepts a
  direct push: both require a pull request and a green **`ci-passed`**.
- `main` additionally requires **`verify-pr-source`**, which is how "only
  `develop` may open PRs into `main`" is enforced.
- **Merge commits** are the only merge method, for feature PRs and release
  PRs alike. Auto-merge is on, and head branches are deleted after merging.

---

## 3. Workflows

Every workflow sets least-privilege `permissions` (read-only at the top, write
scopes granted per job), per-job `timeout-minutes`, a `concurrency` group that
cancels superseded PR runs only, `persist-credentials: false` on checkout,
and pins **every action to a full commit SHA** with a `# vX.Y.Z` comment that
Dependabot keeps current. Event values (branch names, PR titles) reach `run:`
scripts only through `env:`, never as `${{ }}` inside the script, so a
crafted branch name can't inject shell. Jobs run on an explicit
`ubuntu-24.04` image rather than `ubuntu-latest`, so the OS only changes in a
reviewed PR.

### [`ci.yml`](workflows/ci.yml) — the merge gate

Runs on PRs, pushes to `main` / `develop`, and manual dispatch.

| Job | What |
| --- | --- |
| `verify-pr-source` | Blocks PRs into `main` that don't come from `develop` |
| `Lint & format` | `ruff check` (inline PR annotations) + `ruff format --check` + a byte-compile of `src`, `tests` and `scripts` |
| `Spelling` | cspell over the whole repo with `cspell.json`; unknown words are annotated inline with suggestions |
| `Type check` | `mypy --strict` over `src` |
| `Test (3.12 / 3.13 / 3.14)` | pytest + coverage (the run fails below the `fail_under` threshold in `pyproject.toml`) on the `requires-python` floor, the version between and the production version; Codecov upload from 3.14 |
| `JSON Schema up to date` | Regenerates `schema/*.schema.json` and fails if any differs from the committed file |
| `Web assets up to date` | Rebuilds the web form's CSS, fonts and vendored js-yaml from `web/` and fails if they differ from the committed files in `src/resume_builder/web_static/assets/` |
| `Dependency audit` | [`scripts/audit.sh`](../scripts/audit.sh) (also `make audit`): `pip-audit` on `uv.lock`; runtime packages (what ships in the image) **block**, dev-only tooling is reported as a warning since Dependabot security PRs fix those. PyPI network errors are retried with backoff; a real finding fails at once |
| `npm audit (web/)` | [`web/audit.mjs`](../web/audit.mjs) (also run by `make audit`) audits `web/package-lock.json`. A HIGH or CRITICAL advisory in a package that ships in the committed assets (js-yaml, the fonts) **blocks**. Build-tooling advisories only warn, unless they are accepted with a reason in [`web/audit-exceptions.json`](../web/audit-exceptions.json) (today: `braces`, via Tailwind CLI's file watcher, which has no patched release). A new advisory warns; an accepted one that npm stops reporting is flagged for removal |
| `Docker build & smoke test` | Trivy config scan of both Dockerfiles (accepted exceptions in [`.trivyignore.yaml`](../.trivyignore.yaml)), builds `Dockerfile.prod`, boots it, and checks `/healthz`, `/`, the page's assets and its Content-Security-Policy header, a real PDF render from `data/resume.template.yaml`, and that an invalid photo is a clean `422` |
| `ci-passed` | Aggregate gate — the single required check (skipped jobs count as passing) |

### [`security.yml`](workflows/security.yml) — code scanning

On PRs, pushes to `main` / `develop` and weekly (Monday). Results go to
**Security → Code scanning**, where new alerts are flagged on the PR that
introduces them.

| Job | What |
| --- | --- |
| `CodeQL (python)` | `security-extended` queries over the application code |
| `CodeQL (actions)` | The workflow files themselves (injection, permissions) |
| `Workflow audit (zizmor)` | GitHub Actions security linter |
| `Image vulnerability scan (Trivy)` | Fixable CRITICAL/HIGH CVEs in the production image; the weekly run catches CVEs published against an unchanged image |

### [`scorecard.yml`](workflows/scorecard.yml) — OpenSSF Scorecard

Grades the repo's supply-chain practices on pushes to `develop` (the default
branch — Scorecard only publishes from it) and weekly, and
publishes the score behind the README badge. `publish_results: true`
restricts what that file may contain — see its header before editing.

### [`labels.yml`](workflows/labels.yml) — labels as code

Syncs [`labels.yml`](labels.yml) when it changes on `develop`; PRs get a dry
run. A label not listed in that file is **deleted** — add labels there, not in
the UI.

### Deploy

[`render.yaml`](../render.yaml) uses `autoDeployTrigger: checksPass`: Render
builds `docker/Dockerfile.prod` from `main` only after the commit's GitHub
checks pass, so a red CI run never reaches production.

---

## 4. Dependency automation — [`dependabot.yml`](dependabot.yml)

Five ecosystems, weekly (Monday 04:00 UTC), all opening PRs against
**`develop`**:

| Ecosystem | Scans |
| --- | --- |
| `uv` | `pyproject.toml` + `uv.lock` |
| `docker` | `FROM` lines in `docker/Dockerfile.*` — the Python base image and the `uv` stage, each pinned as `tag@sha256:…` (tag and digest bumped together) |
| `github-actions` | SHA pins + version comments in `.github/workflows/` |
| `devcontainers` | Features in `.devcontainer/devcontainer.json` (+ lock file) |
| `pre-commit` | Hook `rev`s in `.pre-commit-config.yaml` |

- Minor + patch bumps are **grouped** into one PR per ecosystem; **majors**
  arrive individually. Security updates are grouped separately.
- **7-day cooldown**: a release is proposed only once it's a week old, so a
  broken or compromised release is usually yanked upstream first. Security
  updates are never delayed.
- uv updates cover **transitive** packages too (`allow: dependency-type: all`),
  since `pip-audit` in CI fails on a vulnerable transitive dependency as well.
- `versioning-strategy: increase-if-necessary` on uv only raises a
  `pyproject.toml` floor when the current one can't satisfy the new version.
- The ruff pre-commit `rev` should match ruff in `uv.lock` — merge the
  pre-commit PR and the uv group PR from the same Monday together.
- Dependabot reads this file from the repository's **default branch**, so
  edits take effect once they reach it.
- Debian packages inside the images aren't a Dependabot ecosystem: the
  production image runs `apt-get upgrade` at build time so security fixes ship
  before the base image catches up, and the weekly Trivy image scan reports
  anything still fixable.
- The production image uninstalls the base image's `pip`. Nothing installs
  packages at runtime, and pip's vendored copies of `urllib3`, `msgpack` and
  setuptools' `pkg_resources` were otherwise the only Python CVEs in the image.

---

## 5. Files in `.github/`

| Path | Purpose |
| --- | --- |
| `CONTRIBUTING.md` | This document |
| `CODEOWNERS` | Review routing (`@Aalihaidar`) |
| `SECURITY.md` | Private vulnerability reporting and scope |
| `dependabot.yml` | Dependency update automation |
| `labels.yml` | Repository labels as code |
| `SETTINGS.md` | The GitHub settings to apply by hand, step by step |
| `rulesets/` | `protect-main.json` and `protect-develop.json`, importable in Settings → Rules |
| `pull_request_template.md` | PR checklist |
| `ISSUE_TEMPLATE/` | Issue forms; blank issues disabled |
| `workflows/` | `ci.yml`, `security.yml`, `scorecard.yml`, `labels.yml` |
