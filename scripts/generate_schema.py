"""Generate a JSON Schema from the Resume Pydantic model.

VS Code's YAML extension uses this to validate data/resume.yaml and offer
autocomplete — against this project's actual schema, instead of the public
"JSON Resume" schema it auto-detects by filename (which is a different,
unrelated standard).

Regenerate any time models.py changes:
    make schema
"""

from __future__ import annotations

import json
from pathlib import Path

from resume_builder.models import Resume

SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "resume.schema.json"


def main() -> None:
    schema = Resume.model_json_schema()
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"✅ Wrote schema to {SCHEMA_PATH}")


if __name__ == "__main__":
    main()
