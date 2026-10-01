# Security Policy

## Reporting a vulnerability

Report security issues **privately** using GitHub's
[Report a vulnerability](https://github.com/Aalihaidar/resume-engine/security/advisories/new)
form (repository **Security → Advisories → Report a vulnerability**).

Please do **not** open a public issue or PR for anything security-sensitive.
I aim to acknowledge a report within 3 business days and to agree a
disclosure timeline with you.

## Supported versions

Only the latest commit on `main` — the version deployed to Render — is
supported. There are no tagged releases.

| Version | Supported |
| ------- | --------- |
| `main`  | ✅        |
| other   | ❌        |

## Scope

In scope — the public, unauthenticated API and web form
(`POST /api/resume/pdf`, `POST /api/cover-letter/pdf`, `GET /`), for example:

- bypassing the request body-size limit or the photo size / MIME / base64
  validation;
- reading files outside `src/resume_builder/static/` through the `photo`
  field (path traversal);
- making the renderer fetch remote or local resources it shouldn't (SSRF,
  local file disclosure through HTML/CSS in resume fields);
- script injection in the rendered HTML or the web form.

Out of scope:

- denial of service by volume against the free-tier deployment;
- dependency and container-image CVEs without a working exploit path specific
  to this project — Dependabot, `pip-audit` and Trivy track those
  automatically;
- the personal details in `data/*.yaml` and the rendered PDFs, which are
  published on purpose.
