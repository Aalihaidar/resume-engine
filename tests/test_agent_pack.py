"""The AI briefing file must stay in step with the models, the API and the web form."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from resume_builder.api import app
from resume_builder.models import CoverLetter, Resume

REPO_ROOT = Path(__file__).parent.parent
WEB_STATIC = REPO_ROOT / "src" / "resume_builder" / "web_static"
WEB_INDEX = WEB_STATIC / "index.html"
WEB_TEMPLATES = WEB_STATIC / "assets" / "templates"


@pytest.fixture(scope="module")
def pack_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_agent_pack", REPO_ROOT / "scripts" / "build_agent_pack.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pack(pack_module: ModuleType) -> str:
    return str(
        pack_module.build_pack(
            REPO_ROOT / "data" / "resume.yaml",
            REPO_ROOT / "data" / "cover_letter.yaml",
            "https://example.test/",
        )
    )


def _fenced(pack: str, language: str, heading: str) -> str:
    match = re.search(rf"### {re.escape(heading)}\n.*?```{language}\n(.*?)\n```", pack, re.DOTALL)
    assert match, f"no {language} block under {heading}"
    return match.group(1)


def test_base_url_is_filled_in_everywhere(pack: str) -> None:
    assert "{{" not in pack
    assert "https://example.test/api/resume/pdf" in pack
    assert "example.test//" not in pack  # trailing slash was trimmed


def test_embedded_data_validates_and_never_carries_a_photo(pack: str) -> None:
    resume = Resume.model_validate(yaml.safe_load(_fenced(pack, "yaml", "resume.yaml")))
    assert resume.photo is None
    CoverLetter.model_validate(yaml.safe_load(_fenced(pack, "yaml", "cover_letter.yaml")))


def test_pack_embeds_the_web_form_templates_verbatim(pack: str) -> None:
    for heading, filename in (
        ("Resume template", "resume.yaml"),
        ("Cover letter template", "cover-letter.yaml"),
    ):
        site = (WEB_TEMPLATES / filename).read_text(encoding="utf-8").strip()
        assert _fenced(pack, "yaml", heading) == site


def test_embedded_schemas_match_the_models(pack: str) -> None:
    assert json.loads(_fenced(pack, "json", "Resume")) == Resume.model_json_schema()
    assert json.loads(_fenced(pack, "json", "CoverLetter")) == CoverLetter.model_json_schema()


def test_guide_routes_exist_in_the_api(pack: str) -> None:
    documented = set(re.findall(r"`(/(?:api/[a-z/-]+|healthz))`", pack))
    assert {"/api/resume/pdf", "/api/cover-letter/pdf", "/healthz"} <= documented
    assert documented <= set(app.openapi()["paths"])


def test_guide_element_ids_exist_in_the_web_form(pack: str) -> None:
    html = WEB_INDEX.read_text(encoding="utf-8")
    for element_id in ("yamlInput", "downloadBtn", "status"):
        assert f"#{element_id}" in pack or element_id in pack
        assert f'id="{element_id}"' in html


def test_main_writes_the_requested_file(pack_module: ModuleType, tmp_path: Path) -> None:
    out = tmp_path / "nested" / "pack.md"
    pack_module.main(["--out", str(out)])
    assert out.read_text(encoding="utf-8").startswith("# Resume and cover letter playbook")
