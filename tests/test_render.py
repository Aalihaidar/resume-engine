from pathlib import Path

import pytest
from markupsafe import escape

from resume_builder.models import Resume
from resume_builder.render import build, load_resume, render_html

REPO_ROOT = Path(__file__).parent.parent
DATA_FILE = REPO_ROOT / "data" / "resume.yaml"


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


def test_full_build_produces_pdf(tmp_path: Path) -> None:
    out_pdf = tmp_path / "resume.pdf"
    out_html = tmp_path / "resume.html"
    build(data_path=DATA_FILE, output_pdf=out_pdf, output_html=out_html)

    assert out_pdf.exists()
    assert out_pdf.stat().st_size > 1000, "PDF suspiciously small - likely a rendering failure"
    assert out_html.exists()


def test_missing_required_field_fails_validation(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("name: 'Test'\n", encoding="utf-8")
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
        load_resume(bad_yaml)
