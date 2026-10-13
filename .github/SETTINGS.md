# GitHub settings (one-time setup)

Everything here lives in GitHub's settings, not in the repository, so it can't
be reviewed in a PR. The rulesets are the exception: they are kept as JSON in
[`rulesets/`](rulesets/) and imported. Each section says where to click, what
to set and why. The branching model these settings enforce is in
[CONTRIBUTING.md](CONTRIBUTING.md).

All paths below start at the repository's **Settings** tab.

| Order | Section | Why this order |
| --- | --- | --- |
| 1 | [General](#1-general--settings--general) | Merge methods must be set before the rulesets narrow them |
| 2 | [Actions](#2-actions--settings--actions--general) | Workflows must be allowed to run before they can be required |
| 3 | [Advanced Security](#3-advanced-security--settings--advanced-security) | Independent of the rest |
| 4 | [Rulesets](#4-rulesets--settings--rules--rulesets) | Last, so the checks they require already exist |
| 5 | [Verify](#8-verify-it-works) | Proves the rules bite |

---

## 1. General — Settings → General

| Setting | Value | Why |
| --- | --- | --- |
| Default branch | **`develop`** (the ⇄ button next to the branch name) | New PRs target it, Dependabot reads its config from it, scheduled workflows and Scorecard run on it |
| Template repository | ❌ | |
| Release immutability | Optional ✅ | Published releases can't be edited afterwards; harmless if you never publish releases |
| **Features** → Wikis | ❌ | Docs live in the repo, where they are reviewed |
| Features → Issues | ✅ | The issue forms in [`ISSUE_TEMPLATE/`](ISSUE_TEMPLATE/) need it |
| Features → Sponsorships, Discussions, Projects | ❌ | Not used |
| Features → Preserve this repository | ✅ | Harmless |
| Features → Pull requests | ✅, creation allowed by **All users** | |
| **Pull Requests** → Allow merge commits | ✅ — Default commit message: **Pull request title and description** | The only merge method used: feature → `develop` and `develop` → `main` |
| Allow squash merging | ❌ | Squashing would rewrite `develop`'s commits, so `main` and `develop` would never line up |
| Allow rebase merging | ❌ | Same reason |
| Always suggest updating pull request branches | ✅ | Shows "Update branch" when `develop` has moved; `protect-develop` requires an up-to-date branch |
| Allow auto-merge | ✅ | Lets a PR merge itself once `ci-passed` is green (the PR page's "Enable auto-merge" button) |
| Automatically delete head branches | ✅ | Feature and Dependabot branches disappear after merge. `develop` is the default branch and is protected from deletion by its ruleset |
| **Commits** → Require contributors to sign off on web-based commits | ❌ | No DCO policy |
| Commits → Allow comments on individual commits | Either | |
| Archives → Include Git LFS objects | ❌ | No LFS |
| Pushes → Limit branches and tags updated in a single push | ❌ | |
| Issues → Auto-close issues with merged linked pull requests | ✅ | "Closes #123" in a PR closes the issue |

Leave the **Danger Zone** alone. Never use "Disable branch protection rules":
it turns the rulesets off for everyone.

> **Merge methods must agree in two places.** The repository setting above
> says which buttons exist; each ruleset's *Allowed merge methods* picks from
> them. If a ruleset allows only a method the repository has turned off, no
> PR can merge into that branch. Both rulesets here allow **Merge** only,
> matching this page.

---

## 2. Actions — Settings → Actions → General

### Actions permissions

Choose **Allow _owner_, and select non-_owner_, actions and reusable
workflows**, then:

| Setting | Value |
| --- | --- |
| Allow actions created by GitHub | ✅ (covers `actions/*` and `github/codeql-action/*`) |
| Allow actions by Marketplace verified creators | ❌ — everything else is listed explicitly instead |
| Allow or block specified actions and reusable workflows | the list below |
| Require actions to be pinned to a full-length commit SHA | ✅ — every workflow already pins this way, and an unpinned `uses:` fails the run |

Paste into *Allow or block specified actions and reusable workflows* (one
line, comma-separated), then **Save**:

```text
aquasecurity/setup-trivy@*, aquasecurity/trivy-action@*, astral-sh/setup-uv@*, codecov/codecov-action@*, crazy-max/ghaction-github-labeler@*, docker/build-push-action@*, docker/setup-buildx-action@*, ossf/scorecard-action@*, streetsidesoftware/cspell-action@*, zizmorcore/zizmor-action@*
```

**This list must stay in step with the workflows.** An action that isn't on
it fails with "action is not allowed". When a PR adds a new `uses:` line, add
the action here first; Dependabot only bumps versions, so it doesn't need
list changes.

The list must also cover actions that other actions call. `trivy-action` is a
composite action that calls `aquasecurity/setup-trivy`, which never appears in
a workflow file, so it has to be listed on its own. Nested actions created by
GitHub (`actions/cache`, `actions/github-script`, `github/codeql-action`) are
already covered by *Allow actions created by GitHub*. The workflow files show
the direct ones:

```bash
grep -rhoE "uses: [^ @]+" .github/workflows | sort -u
```

For the nested ones, read the `action.yml` of each third-party action at the
SHA the workflows pin, and look for `uses:` lines. When a run fails with "The
action … is not allowed", the error names the exact action to add.

### Check, workflow run, status, artifact and log retention

**30 days** is fine (maximum 90). The only artifact is Scorecard's SARIF file,
which the workflow keeps for 5 days anyway.

### Cache

Retention **7 days**, eviction limit **10 GB**: the defaults. CI's caches
(uv and the Docker layers) are small and rebuild quickly.

### Approval for running fork pull request workflows from contributors

Choose **Require approval for all external contributors**. A fork's PR can
change a workflow file, so nobody who isn't a member of the repository gets
a CI run until you have read the diff. (The default, "first-time
contributors", trusts anyone who has had one PR merged.)

### Workflow permissions

| Setting | Value |
| --- | --- |
| Default `GITHUB_TOKEN` permissions | **Read repository contents and packages permissions** |
| Allow GitHub Actions to create and approve pull requests | ❌ |

Every workflow also declares its own `permissions:` and grants write scopes
per job (`security-events`, `issues`, `id-token`), so this default only
matters to a workflow that forgets to.

---

## 3. Advanced Security — Settings → Advanced Security

| Feature | State | Notes |
| --- | --- | --- |
| Private vulnerability reporting | **Enabled** | The [security policy](SECURITY.md) and the issue chooser both point reporters here |
| Dependency graph | **On** | Needed by Dependabot alerts |
| Automatic dependency submission | Disabled | The lock files are already read directly |
| Dependabot alerts | **On** | |
| Malware alerts | **On** | |
| Dependabot auto-triage rules | Keep GitHub's preset rule enabled | |
| Dependabot security updates | **On** | Opens a PR for an alert that has a patch |
| Grouped security updates | **On** | One security PR per ecosystem. [`dependabot.yml`](dependabot.yml) also defines `*-security` groups; GitHub says to turn this toggle off only if you want that file to be the sole source of grouping |
| Dependabot version updates | Driven by the file | The weekly PRs come from [`dependabot.yml`](dependabot.yml) on `develop`; the **Edit dependabot.yml** button just opens it |
| CodeQL analysis | **Advanced setup** | The scan is [`workflows/security.yml`](workflows/security.yml). **Never switch to Default setup**: GitHub then rejects the advanced workflow's uploads, and Trivy and Scorecard results stop appearing |
| AI Scan for pull requests | Optional (Off) | Preview feature; CodeQL already covers the Python and workflow code |
| Copilot Autofix | On or Off | Only suggests fixes on CodeQL alerts; nothing is applied without you |
| Code scanning → Check runs failure threshold | Security alert severity: **High or higher**; standard alert severity: **Only errors** | Decides when a code scanning check run fails on a PR |
| Secret protection (secret scanning) | **Enabled** | |
| Push protection | **Enabled** | Rejects a push that contains a recognized secret |

### Code scanning alerts

Open alerts appear under **Security → Code scanning** (CodeQL, Trivy,
Scorecard). Most Scorecard findings are about repository settings, not code:

| Scorecard finding | What clears it |
| --- | --- |
| Branch-Protection | The rulesets in [section 4](#4-rulesets--settings--rules--rulesets). Scorecard's token can't read every ruleset detail, so it may still under-report |
| Code-Review | Needs a second reviewer; a solo maintainer can't meet it. Dismiss the alert with a reason rather than weakening the rules |
| Vulnerabilities | Merge the weekly Dependabot PRs |
| Maintained | Time: the repository needs 90 days of age and recent activity |
| Fuzzing, CII-Best-Practices | Optional extras (property-based tests; an OpenSSF Best Practices badge) |

A Trivy alert about a Debian package closes by itself once the base image or
`apt-get upgrade` picks up the fix; re-run the **Security** workflow to
refresh it. If no fix exists yet, dismiss the alert as *won't fix*.

---

## 4. Rulesets — Settings → Rules → Rulesets

Import both files: **New ruleset ▾ → Import a ruleset**, choose the file,
check the preview, **Create**.

- [`rulesets/protect-main.json`](rulesets/protect-main.json)
- [`rulesets/protect-develop.json`](rulesets/protect-develop.json)

If a ruleset is later edited in the UI, export it again (**⋯ → Export
ruleset**) and commit the file so the repository and GitHub don't drift.
Changing a file here does **not** update an existing ruleset: edit the ruleset
in the UI, or delete it and re-import.

Both rulesets are **Active** with an **empty bypass list**. With an admin
bypass, the owner could still push to `main` directly, which defeats the
point.

| Rule | `protect-main` | `protect-develop` | Effect |
| --- | --- | --- | --- |
| Restrict deletions | ✅ | ✅ | The branch can't be deleted |
| Block force pushes | ✅ | ✅ | History can't be rewritten |
| Require a pull request before merging | ✅ | ✅ | **This is what stops direct pushes.** 0 approvals, because you can't approve your own PR; raise it (and enable *Require review from Code Owners*) once there's a second maintainer |
| Required approvals | 0 | 0 | |
| Require conversation resolution | ✅ | ✅ | |
| Allowed merge methods | **Merge** | **Merge** | Must match [General](#1-general--settings--general) |
| Require status checks to pass | `ci-passed`, `verify-pr-source` | `ci-passed` | |
| Require branches to be up to date | ❌ | ✅ | See below |
| Restrict creations / Restrict updates | ❌ | ❌ | With an empty bypass list these would also block the PR merge itself |

**Why `main` isn't required to be up to date.** Release PRs are merge
commits, so `main` always has one commit `develop` doesn't. Requiring an
up-to-date branch would force a merge of `main` back into `develop` before
every release. The merge still fails on a real conflict.

**Why `develop` is.** Each PR is tested against the `develop` it will land on.
Combined with auto-merge, that means a green PR can only merge onto the tip it
was tested on.

**"Only `develop` may open PRs into `main`"** can't be expressed as a ruleset:
GitHub has no source-branch rule. The `verify-pr-source` job in
[`workflows/ci.yml`](workflows/ci.yml) fails any PR into `main` whose head
isn't this repository's `develop`, and requiring it is what makes that
binding.

**Why `ci-passed`.** It is the one aggregate check. It waits for every other
job (skipped counts as passing), so adding a job to CI never means editing
the ruleset.

Optional extra, deliberately not included: *Require code scanning results*.
It makes a PR wait for CodeQL, and bot PRs may not be able to upload results.
Add it only after watching a few Dependabot PRs upload CodeQL results
successfully.

---

## 5. Environments — Settings → Environments

**None.** Nothing in Actions deploys: Render builds `main` itself
(`autoDeployTrigger: checksPass` in [`render.yaml`](../render.yaml)), and no
workflow uses a deployment secret.

Create a `production` environment only if a deploy job is ever added to a
workflow. Then limit *Deployment branches* to `main`, keep secrets on the
environment rather than the repository, and decide whether to require a
reviewer.

---

## 6. Secrets and variables — Settings → Secrets and variables

| Where | Name | Used by | Notes |
| --- | --- | --- | --- |
| Actions → Secrets | `CODECOV_TOKEN` | `ci.yml` → `test` | Optional; an upload failure doesn't fail CI |
| Dependabot → Secrets | `CODECOV_TOKEN` | same job on Dependabot PRs | Optional. Dependabot PRs can't read the Actions secrets; without it the upload is skipped and CI still passes |

`GITHUB_TOKEN` is automatic. There are no variables. Nothing else is needed:
Render builds the image itself.

---

## 7. Everything else

| Setting | State | Notes |
| --- | --- | --- |
| Collaborators and teams | Just you | Add a second maintainer, then raise the required approvals |
| Branches (legacy branch protection) | **Empty** | The rulesets replace it; two systems at once is confusing |
| Pages | Off | |
| Webhooks | None | |
| GitHub Apps | Render (deploys `main`); Codecov if you use it | Render waits for the commit's checks before deploying (`checksPass`) |
| Actions → Runners | None | Jobs run on GitHub-hosted `ubuntu-24.04` |

---

## 8. Verify it works

After importing the rulesets:

```bash
# A direct push to a protected branch must be rejected
git switch -c tmp/push-test origin/develop
git commit --allow-empty -m "test: direct push"
git push origin tmp/push-test:develop    # expect: rejected, changes must be made through a pull request
git switch develop && git branch -D tmp/push-test
```

Then on github.com:

1. **A PR from a feature branch into `develop`** shows `ci-passed` as a
   required check and offers only **Create a merge commit** (and
   **Enable auto-merge**).
2. **A PR from `develop` into `main`** shows `ci-passed` and
   `verify-pr-source` as required.
3. **A PR from a feature branch into `main`** (open one and close it) fails
   `verify-pr-source` and can't be merged.
4. **Settings → Rules → Insights** lists the pushes the rulesets blocked.
