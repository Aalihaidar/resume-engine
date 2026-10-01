"""The web form is a static page; these tests keep it honest without a browser.

Its Content-Security-Policy (api.py) allows only same-origin scripts, styles and
fonts, so anything inline or third-party would silently break in production.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from resume_builder.models import CoverLetter, Resume
from resume_builder.render import render_cover_letter_html, render_html, render_pdf_bytes

WEB_STATIC = Path(__file__).parent.parent / "src" / "resume_builder" / "web_static"
ASSETS = WEB_STATIC / "assets"
INDEX = (WEB_STATIC / "index.html").read_text(encoding="utf-8")


def test_starter_resume_template_validates_and_renders() -> None:
    raw = yaml.safe_load((ASSETS / "templates" / "resume.yaml").read_text(encoding="utf-8"))
    resume = Resume.model_validate(raw)
    assert render_pdf_bytes(render_html(resume)).startswith(b"%PDF-")


def test_starter_cover_letter_template_validates_and_renders() -> None:
    raw = yaml.safe_load((ASSETS / "templates" / "cover-letter.yaml").read_text(encoding="utf-8"))
    letter = CoverLetter.model_validate(raw)
    assert render_pdf_bytes(render_cover_letter_html(letter)).startswith(b"%PDF-")


def test_index_has_no_third_party_references() -> None:
    assert not re.findall(r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//""", INDEX)


def test_index_is_csp_compatible() -> None:
    inline_scripts = [
        body
        for body in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", INDEX, re.S)
        if body.strip()
    ]
    assert inline_scripts == []
    assert "<style" not in INDEX
    assert not re.search(r"\sstyle\s*=", INDEX)
    assert not re.search(r"\son[a-z]+\s*=", INDEX)  # onclick= and friends


@pytest.mark.parametrize("reference", re.findall(r'(?:src|href)="(/assets/[^"]+)"', INDEX))
def test_assets_referenced_by_index_exist(reference: str) -> None:
    assert (WEB_STATIC / reference.removeprefix("/")).is_file()


def test_every_font_face_url_exists() -> None:
    css = (ASSETS / "app.css").read_text(encoding="utf-8")
    urls = re.findall(r'url\("?([^")]+\.woff2)"?\)', css)
    assert urls, "expected @font-face rules in app.css"
    for url in urls:
        assert (ASSETS / url).is_file(), url


def test_script_does_not_reach_third_parties() -> None:
    script = (ASSETS / "app.js").read_text(encoding="utf-8")
    assert not re.search(r"""["'`]https?://""", script)
