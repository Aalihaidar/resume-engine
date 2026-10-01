"""Generate the JSON Schemas for the Resume and CoverLetter Pydantic models.

VS Code's YAML extension uses these to validate data/resume.yaml and
data/cover_letter.yaml and offer autocomplete — against this project's actual
schema, instead of the public "JSON Resume" schema it auto-detects by filename
(which is a different, unrelated standard). The same files describe the JSON
bodies the HTTP API accepts.

Regenerate any time models.py changes:
    make schema
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel

from resume_builder.models import CoverLetter, Resume

SCHEMA_DIR = Path(__file__).parent.parent / "schema"
SCHEMAS: dict[str, type[BaseModel]] = {
    "resume.schema.json": Resume,
    "cover_letter.schema.json": CoverLetter,
}


def main() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        path = SCHEMA_DIR / filename
        path.write_text(json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8")
        sys.stdout.write(f"Wrote schema to {path}\n")


if __name__ == "__main__":
    main()
