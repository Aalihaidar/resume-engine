from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from markupsafe import escape
from pydantic import ValidationError

from resume_builder import render as render_module
from resume_builder.models import CoverLetter, Resume
from resume_builder.render import (
    STATIC_DIR,
    TEMPLATES_DIR,
    _LocalResourceFetcher,
    _resolve_photo_path,
    build,
    build_cover_letter,
    load_cover_letter,
    load_resume,
    render_cover_letter_html,
    render_html,
    render_pdf,
    render_pdf_bytes,
)

REPO_ROOT = Path(__file__).parent.parent
DATA_FILE = REPO_ROOT / "data" / "resume.yaml"
COVER_LETTER_FILE = REPO_ROOT / "data" / "cover_letter.yaml"


def test_resume_yaml_loads_and_validates() -> None:
    """Loads resume.yaml and confirms it validates against the schema.

    Every optional section (experience, projects, education, skills,
    certifications, languages) is allowed to be an empty list -- the
    schema only requires top-level identity fields (name, headline) to
    be present. This mirrors the `sections:` visibility switches, which
    let a section be toggled off entirely regardless of whether it has
    entries.
    """
    resume = load_resume(DATA_FILE)
    assert isinstance(resume, Resume)
    assert resume.name
    assert isinstance(resume.experience, list)
    assert isinstance(resume.projects, list)
    assert isinstance(resume.education, list)
    assert isinstance(resume.skills, list)
    assert isinstance(resume.certifications, list)
    assert isinstance(resume.languages, list)


def test_cover_letter_yaml_loads_and_validates() -> None:
    letter = load_cover_letter(COVER_LETTER_FILE)
    assert isinstance(letter, CoverLetter)


def test_render_html_contains_key_fields() -> None:
    """Checks the rendered HTML actually contains the resume's own data.

    Compares against markupsafe-escaped copies of the source values rather
    than hardcoded strings, so this test verifies whatever resume.yaml
    currently holds — Jinja2 autoescapes '&', '<', '>', '"', and "'" in
    template variables, so a raw substring check would break on any
    headline/bullet containing those characters.
    """
    resume = load_resume(DATA_FILE)
    html = render_html(resume)

    assert str(escape(resume.name)) in html
    assert str(escape(resume.headline)) in html

    for job in resume.visible_experience:
        assert str(escape(job.title)) in html
        assert str(escape(job.company)) in html

    for project in resume.visible_projects:
        assert str(escape(project.name)) in html
        for tech in project.technologies:
            assert str(escape(tech)) in html

    for edu in resume.visible_education:
        assert str(escape(edu.degree)) in html
        assert str(escape(edu.institution)) in html

    for group in resume.visible_skills:
        assert str(escape(group.category)) in html


def test_hidden_entries_are_not_rendered(resume_payload: dict[str, Any]) -> None:
    resume_payload["experience"] = [
        {
            "title": "Visible Role",
            "company": "Shown Co",
            "location": "l",
            "start": "s",
            "end": "e",
            "bullets": [],
        },
        {
            "include": False,
            "title": "Hidden Role",
            "company": "Secret Co",
            "location": "l",
            "start": "s",
            "end": "e",
            "bullets": [],
        },
    ]
    resume_payload["sections"] = {"education": False}
    html = render_html(Resume.model_validate(resume_payload))

    assert "Visible Role" in html
    assert "Hidden Role" not in html
    assert "<h2>Education</h2>" not in html


def test_user_text_is_html_escaped(resume_payload: dict[str, Any]) -> None:
    resume_payload["name"] = "<script>alert(1)</script>"
    resume_payload["summary"] = "R&D <b>lead</b>"
    html = render_html(Resume.model_validate(resume_payload))

    assert "<script>alert(1)</script>" not in html
    assert "<b>lead</b>" not in html
    assert str(escape("<script>alert(1)</script>")) in html


def test_linkedin_is_optional_in_the_resume_header(resume_payload: dict[str, Any]) -> None:
    contact = resume_payload["contact"]
    linkedin = str(escape(contact["linkedin_display"]))
    assert linkedin in render_html(Resume.model_validate(resume_payload))

    del contact["linkedin_display"], contact["linkedin_url"]
    html = render_html(Resume.model_validate(resume_payload))
    assert linkedin not in html
    assert str(escape(contact["github_display"])) in html

    github = str(escape(contact.pop("github_display")))
    del contact["github_url"]
    html = render_html(Resume.model_validate(resume_payload))
    assert f">{github}</a>" not in html
    # The email still opens the second line, with no separator left dangling.
    email = re.escape(f'<span class="contact-item">{escape(contact["email"])}</span>')
    assert re.search(rf'contact-links">\s*{email}\s*</p>', html)


def test_linkedin_is_optional_in_the_cover_letter_header(
    cover_letter_payload: dict[str, Any],
) -> None:
    contact = cover_letter_payload["applicant_contact"]
    linkedin = str(escape(contact["linkedin_display"]))
    del contact["linkedin_display"], contact["linkedin_url"]
    html = render_cover_letter_html(CoverLetter.model_validate(cover_letter_payload))
    assert linkedin not in html


def test_every_phone_and_email_is_rendered(
    resume_payload: dict[str, Any], cover_letter_payload: dict[str, Any]
) -> None:
    phones = ["+49 151 23456789", "+1 415 555 0100"]
    emails = ["jane.doe@example.com", "jane@example.org"]
    resume_payload["contact"].update(phone=phones, email=emails)
    cover_letter_payload["applicant_contact"].update(phone=phones, email=emails)

    for html in (
        render_html(Resume.model_validate(resume_payload)),
        render_cover_letter_html(CoverLetter.model_validate(cover_letter_payload)),
    ):
        for value in phones + emails:
            assert f'<span class="contact-item">{escape(value)}</span>' in html
        # Phones share the location's line; emails open the next one.
        lines = html.split("</p>")
        assert any(phones[1] in line and emails[0] not in line for line in lines)
        assert any(emails[1] in line and phones[0] not in line for line in lines)


def test_render_cover_letter_html_contains_key_fields(cover_letter_payload: dict[str, Any]) -> None:
    letter = CoverLetter.model_validate(cover_letter_payload)
    html = render_cover_letter_html(letter)

    assert str(escape(letter.applicant_name)) in html
    assert str(escape(letter.role_title)) in html
    for paragraph in letter.body_paragraphs:
        assert str(escape(paragraph)) in html


def test_full_build_produces_pdf(tmp_path: Path) -> None:
    out_pdf = tmp_path / "resume.pdf"
    out_html = tmp_path / "resume.html"
    build(data_path=DATA_FILE, output_pdf=out_pdf, output_html=out_html)

    assert out_pdf.exists()
    assert out_pdf.stat().st_size > 1000, "PDF suspiciously small - likely a rendering failure"
    assert out_html.exists()


def test_cover_letter_build_creates_missing_directories(tmp_path: Path) -> None:
    out_pdf = tmp_path / "nested" / "dir" / "letter.pdf"
    out_html = tmp_path / "other" / "letter.html"
    build_cover_letter(COVER_LETTER_FILE, out_pdf, out_html)

    assert out_pdf.read_bytes().startswith(b"%PDF-")
    assert out_html.exists()


def test_render_pdf_writes_file_and_matches_bytes_api(tmp_path: Path) -> None:
    out = tmp_path / "x" / "doc.pdf"
    render_pdf("<p>hello</p>", out)
    assert out.read_bytes().startswith(b"%PDF-")
    assert render_pdf_bytes("<p>hello</p>").startswith(b"%PDF-")


def test_missing_required_field_fails_validation(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("name: 'Test'\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_resume(bad_yaml)


def test_generated_schemas_are_up_to_date() -> None:
    """Mirrors the CI drift check: models.py changed => `make schema` was run."""
    for filename, model in (
        ("resume.schema.json", Resume),
        ("cover_letter.schema.json", CoverLetter),
    ):
        on_disk = json.loads((REPO_ROOT / "schema" / filename).read_text(encoding="utf-8"))
        assert on_disk == model.model_json_schema(), f"{filename} is stale: run `make schema`"


# --- photo resolution (second, independent containment layer) -------------


def test_data_uri_photo_is_used_as_is(png_data_uri: str) -> None:
    assert _resolve_photo_path(png_data_uri) == png_data_uri


def test_existing_static_file_resolves_to_a_file_uri() -> None:
    resolved = _resolve_photo_path("headshot.jpg")
    assert resolved == (STATIC_DIR / "headshot.jpg").resolve().as_uri()


@pytest.mark.parametrize("name", ["missing.jpg", "", "/", "..", ".", ".gitkeep"])
def test_unknown_or_degenerate_photo_names_resolve_to_nothing(name: str) -> None:
    assert _resolve_photo_path(name) is None


@pytest.mark.parametrize(
    "name",
    [
        "../pyproject.toml",
        "../../etc/passwd",
        "/etc/passwd",
        "../static/headshot.jpg",  # even a path that leads back to a real file
        "static/headshot.jpg",
        "..\\headshot.jpg",
        "headshot.jpg/",
        "HEADSHOT.JPG",
    ],
)
def test_anything_but_an_exact_static_filename_has_no_match(name: str) -> None:
    # Even if a Resume skipped model validation, the string is only ever compared
    # with existing names; it is never used to build a path.
    assert _resolve_photo_path(name) is None


def test_a_symlink_leading_out_of_the_static_dir_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    static = tmp_path / "static"
    static.mkdir()
    secret = tmp_path / "secret.jpg"
    secret.write_bytes(b"\xff\xd8\xff")
    (static / "inside.jpg").write_bytes(b"\xff\xd8\xff")
    (static / "escape.jpg").symlink_to(secret)
    monkeypatch.setattr(render_module, "STATIC_DIR", static)

    assert _resolve_photo_path("inside.jpg") == (static / "inside.jpg").resolve().as_uri()
    assert _resolve_photo_path("escape.jpg") is None


# --- resource fetching ----------------------------------------------------


def test_fetcher_serves_templates_and_data_uris() -> None:
    fetcher = _LocalResourceFetcher()
    for url in ((TEMPLATES_DIR / "resume.css").as_uri(), "data:text/plain;base64,aGk="):
        response = fetcher.fetch(url)
        response.close()


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        (TEMPLATES_DIR.parent / "models.py").as_uri(),
        (TEMPLATES_DIR / ".." / ".." / ".." / "pyproject.toml").as_uri(),
        "http://127.0.0.1/",
        "https://example.com/logo.png",
        "ftp://example.com/x",
    ],
)
def test_fetcher_refuses_everything_else(url: str) -> None:
    with pytest.raises(ValueError, match=r"Refusing|disallowed protocol"):
        _LocalResourceFetcher().fetch(url)
