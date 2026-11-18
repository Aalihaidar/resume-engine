"""Build one self-contained briefing file that any AI assistant can work from.

The file combines a hand-written guide (rules, workflow, how to get the PDFs from the
API or the web form) with everything generated from this repo: the two JSON Schemas, the
web form's starter templates and the owner's current resume and cover letter. Give it to
an assistant together with a job posting and it has what it needs to tailor both documents.

It holds real personal details, so it is written to the gitignored `output/` folder and
must never be committed or served. Standard library only, so it runs without `uv sync`.

    make agent-pack
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEFAULT_BASE_URL = "https://resume-engine-sud4.onrender.com"
GUIDE = Path(__file__).with_name("agent_guide.md")
# The starter documents the web form loads: the exact shape the owner expects back.
SITE_TEMPLATES = ROOT / "src/resume_builder/web_static/assets/templates"

# The API refuses filename photos (inline data URIs only) and a base64 blob would swamp the
# file, so the embedded data always says `photo: null`; the owner adds a photo in the web form.
_PHOTO_LINE = re.compile(r"^photo:.*$", re.MULTILINE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _fence(language: str, body: str) -> str:
    return f"```{language}\n{body}\n```"


def _compact_schema(path: Path) -> str:
    return json.dumps(json.loads(_read(path)), separators=(",", ":"), ensure_ascii=False)


def build_pack(resume: Path, cover_letter: Path, base_url: str = DEFAULT_BASE_URL) -> str:
    """Return the briefing as Markdown text."""
    base_url = base_url.rstrip("/")
    guide = _read(GUIDE).replace("{{BASE_URL}}", base_url)
    resume_text = _PHOTO_LINE.sub("photo: null", _read(resume))

    parts = [
        guide,
        "## 5. Current data (the only facts you may use)",
        "### resume.yaml\n\n"
        "The owner's full resume. This is the source to tailor from. `photo` is shown as "
        "`null` on purpose (rule 4).\n\n" + _fence("yaml", resume_text),
        "### cover_letter.yaml\n\n"
        "The owner's previous cover letter. Use it as a style and facts reference only: "
        "rewrite it for each new job.\n\n" + _fence("yaml", _read(cover_letter)),
        "## 6. Templates (the starter documents of the web form)",
        "Return each document in exactly this shape: same keys, same order, same style. "
        "Comments explain every field.",
        "### Resume template\n\n" + _fence("yaml", _read(SITE_TEMPLATES / "resume.yaml")),
        "### Cover letter template\n\n"
        + _fence("yaml", _read(SITE_TEMPLATES / "cover-letter.yaml")),
        "## 7. JSON Schemas (authoritative: names, types, limits)",
        "Unknown keys are rejected. Strings and lists have length limits, shown as "
        "`maxLength` and `maxItems`.",
        "### Resume\n\n" + _fence("json", _compact_schema(ROOT / "schema/resume.schema.json")),
        "### CoverLetter\n\n"
        + _fence("json", _compact_schema(ROOT / "schema/cover_letter.schema.json")),
    ]
    return "\n\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--resume", type=Path, default=ROOT / "data/resume.yaml")
    parser.add_argument("--cover-letter", type=Path, default=ROOT / "data/cover_letter.yaml")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="where the API is deployed")
    parser.add_argument("--out", type=Path, default=ROOT / "output/agent-pack.md")
    args = parser.parse_args(argv)

    pack = build_pack(args.resume, args.cover_letter, args.base_url)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(pack, encoding="utf-8")
    sys.stdout.write(f"Wrote {args.out} ({len(pack):,} characters)\n")


if __name__ == "__main__":
    main()
