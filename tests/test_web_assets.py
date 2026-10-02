"""The web form is a static page; these tests keep it honest without a browser.

Its Content-Security-Policy (api.py) allows only same-origin scripts, styles and
fonts, so anything inline or third-party would silently break in production.
"""

from __future__ import annotations

import re
import struct
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

from resume_builder.models import CoverLetter, Resume
from resume_builder.render import render_cover_letter_html, render_html, render_pdf_bytes

WEB_STATIC = Path(__file__).parent.parent / "src" / "resume_builder" / "web_static"
ASSETS = WEB_STATIC / "assets"
INDEX = (WEB_STATIC / "index.html").read_text(encoding="utf-8")


class _Page(HTMLParser):
    """What the page's markup contains, read with a real parser (not regexes):
    tag and attribute names are case-insensitive and may be spaced oddly."""

    def __init__(self, markup: str) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attributes: list[tuple[str, str, str]] = []  # (tag, name, value)
        self.inline_scripts: list[str] = []
        self._in_inline_script = False
        self.feed(markup)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attributes.extend((tag, name, value or "") for name, value in attrs)
        self._in_inline_script = tag == "script" and all(name != "src" for name, _ in attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_inline_script = False

    def handle_data(self, data: str) -> None:
        if self._in_inline_script and data.strip():
            self.inline_scripts.append(data)


PAGE = _Page(INDEX)
URL_ATTRIBUTES = {"src", "href", "action", "srcset", "poster", "data"}
LOCAL_REFERENCES = sorted(
    value
    for _, name, value in PAGE.attributes
    if name in URL_ATTRIBUTES and value.startswith("/assets/")
)


def test_starter_resume_template_validates_and_renders() -> None:
    raw = yaml.safe_load((ASSETS / "templates" / "resume.yaml").read_text(encoding="utf-8"))
    resume = Resume.model_validate(raw)
    assert render_pdf_bytes(render_html(resume)).startswith(b"%PDF-")


def test_starter_cover_letter_template_validates_and_renders() -> None:
    raw = yaml.safe_load((ASSETS / "templates" / "cover-letter.yaml").read_text(encoding="utf-8"))
    letter = CoverLetter.model_validate(raw)
    assert render_pdf_bytes(render_cover_letter_html(letter)).startswith(b"%PDF-")


def test_index_has_no_third_party_references() -> None:
    remote = [
        value
        for _, name, value in PAGE.attributes
        if name in URL_ATTRIBUTES and value.strip().lower().startswith(("http:", "https:", "//"))
    ]
    assert remote == []


def test_index_is_csp_compatible() -> None:
    assert PAGE.inline_scripts == []
    assert "style" not in PAGE.tags
    assert [(tag, name) for tag, name, _ in PAGE.attributes if name == "style"] == []
    # onclick=, onload= and friends
    assert [(tag, name) for tag, name, _ in PAGE.attributes if name.startswith("on")] == []


def test_index_loads_its_own_script_and_styles() -> None:
    assert "/assets/app.js" in LOCAL_REFERENCES
    assert "/assets/app.css" in LOCAL_REFERENCES


@pytest.mark.parametrize("reference", LOCAL_REFERENCES)
def test_assets_referenced_by_index_exist(reference: str) -> None:
    assert (WEB_STATIC / reference.removeprefix("/")).is_file()


def test_index_has_a_tab_icon_and_a_link_preview_image() -> None:
    assert "/assets/favicon.svg" in LOCAL_REFERENCES
    previews = [
        value
        for tag, name, value in PAGE.attributes
        if tag == "meta" and name == "content" and value.endswith("/assets/social-preview.png")
    ]
    # Link previews need an absolute URL, so this one is checked by name and the file by header.
    assert len(previews) == 1
    assert previews[0].startswith("https://")
    header = (ASSETS / "social-preview.png").read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", header[16:24]) == (1200, 630)


def test_every_font_face_url_exists() -> None:
    css = (ASSETS / "app.css").read_text(encoding="utf-8")
    urls = re.findall(r'url\("?([^")]+\.woff2)"?\)', css)
    assert urls, "expected @font-face rules in app.css"
    for url in urls:
        assert (ASSETS / url).is_file(), url


def test_script_does_not_reach_third_parties() -> None:
    script = (ASSETS / "app.js").read_text(encoding="utf-8")
    assert not re.search(r"""["'`]https?://""", script)
