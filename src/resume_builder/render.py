"""Render resume.yaml -> resume.pdf and cover_letter.yaml -> cover_letter.pdf
via Jinja2 + WeasyPrint."""

from __future__ import annotations

from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from resume_builder.models import CoverLetter, Resume

PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


def load_resume(data_path: Path) -> Resume:
    """Load and validate resume.yaml into a typed Resume object."""
    raw = yaml.safe_load(data_path.read_text(encoding="utf-8"))
    return Resume.model_validate(raw)


def render_html(resume: Resume, template_name: str = "resume.html.j2") -> str:
    """Render the resume data into an HTML string using the Jinja2 template."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template(template_name)

    photo_path = None
    if resume.show_photo and resume.photo is not None:
        candidate = STATIC_DIR / resume.photo
        if candidate.exists():
            photo_path = candidate.resolve().as_uri()

    return template.render(resume=resume, photo_path=photo_path)


def render_pdf(html_content: str, output_path: Path) -> None:
    """Convert rendered HTML to a print-ready, ATS-safe single-column PDF."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_content, base_url=str(TEMPLATES_DIR)).write_pdf(str(output_path))


def build(
    data_path: Path,
    output_pdf: Path,
    output_html: Path | None = None,
) -> None:
    """Full pipeline: resume.yaml -> validated model -> HTML -> PDF."""
    resume = load_resume(data_path)
    html_content = render_html(resume)

    if output_html:
        output_html.parent.mkdir(parents=True, exist_ok=True)
        output_html.write_text(html_content, encoding="utf-8")

    render_pdf(html_content, output_pdf)


def load_cover_letter(data_path: Path) -> CoverLetter:
    """Load and validate cover_letter.yaml into a typed CoverLetter object."""
    raw = yaml.safe_load(data_path.read_text(encoding="utf-8"))
    return CoverLetter.model_validate(raw)


def render_cover_letter_html(
    letter: CoverLetter, template_name: str = "cover_letter.html.j2"
) -> str:
    """Render the cover letter data into an HTML string using the Jinja2 template."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template(template_name)
    return template.render(letter=letter)


def build_cover_letter(
    data_path: Path,
    output_pdf: Path,
    output_html: Path | None = None,
) -> None:
    """Full pipeline: cover_letter.yaml -> validated model -> HTML -> PDF."""
    letter = load_cover_letter(data_path)
    html_content = render_cover_letter_html(letter)

    if output_html:
        output_html.parent.mkdir(parents=True, exist_ok=True)
        output_html.write_text(html_content, encoding="utf-8")

    render_pdf(html_content, output_pdf)
