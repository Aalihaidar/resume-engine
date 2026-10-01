"""Render resume.yaml -> resume.pdf and cover_letter.yaml -> cover_letter.pdf
via Jinja2 + WeasyPrint.

Every interface (CLI, HTTP API, web form) goes through the functions here, so
layout and safety rules live in exactly one place. In particular, WeasyPrint
is only ever given `_LocalResourceFetcher`: the templates need a stylesheet and
an optional headshot, nothing else, so a document may not make the renderer
reach out to the network or read arbitrary files.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML
from weasyprint.urls import URLFetcher

from resume_builder.models import CoverLetter, Resume

PACKAGE_DIR = Path(__file__).parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


class _LocalResourceFetcher(URLFetcher):  # type: ignore[misc]  # WeasyPrint is untyped
    """Serve only `data:` URIs and files inside the templates / static dirs."""

    _ALLOWED_ROOTS = (TEMPLATES_DIR.resolve(), STATIC_DIR.resolve())

    def __init__(self) -> None:
        super().__init__(allowed_protocols={"data", "file"})

    def fetch(self, url: str, headers: dict[str, str] | None = None) -> Any:
        if url.lower().startswith("file:"):
            path = Path(url2pathname(urlparse(url).path)).resolve()
            if not any(path.is_relative_to(root) for root in self._ALLOWED_ROOTS):
                raise ValueError(f"Refusing to read outside the template directories: {url}")
        return super().fetch(url, headers)


@cache
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )


def _read_yaml(data_path: Path) -> object:
    return yaml.safe_load(data_path.read_text(encoding="utf-8"))


def load_resume(data_path: Path) -> Resume:
    """Load and validate resume.yaml into a typed Resume object."""
    return Resume.model_validate(_read_yaml(data_path))


def _resolve_photo_path(photo: str) -> str | None:
    """Resolve `Resume.photo` into something usable as an <img src="...">.

    Accepts two forms:
      - a `data:image/...;base64,...` URI (the API/web-form workflow — the
        caller embeds the image bytes directly in the JSON payload, no
        server-side file needed; this is what the web form's photo picker
        produces) — used as-is.
      - a filename inside STATIC_DIR (the original CLI workflow — bake a
        headshot into the image/repo, reference it by name) — resolved to
        a `file://` URI.

    `Resume.photo` is already validated in models.py (MIME/size for data
    URIs; no path separators or '..' for filenames), but this function does
    not rely on that. The caller's string is never turned into a path at all:
    it is only compared, as a whole, with the names of the regular files that
    already exist in STATIC_DIR. Anything else — a directory part, '..', an
    absolute path, a dotfile, an unknown name — simply has no match. A file
    that is a symlink out of STATIC_DIR is refused as well. That keeps this
    safe even if it's ever called with a Resume-like object built outside the
    normal validated path.
    """
    if photo.startswith("data:image"):
        return photo

    static_root = STATIC_DIR.resolve()
    available = {
        entry.name: entry
        for entry in static_root.iterdir()
        if entry.is_file() and not entry.name.startswith(".")
    }

    match = available.get(photo)
    if match is None:
        return None

    resolved = match.resolve()
    return resolved.as_uri() if resolved.is_relative_to(static_root) else None


def render_html(resume: Resume, template_name: str = "resume.html.j2") -> str:
    """Render the resume data into an HTML string using the Jinja2 template."""
    template = _environment().get_template(template_name)

    photo_path = None
    if resume.show_photo and resume.photo is not None:
        photo_path = _resolve_photo_path(resume.photo)

    return template.render(resume=resume, photo_path=photo_path)


def render_pdf_bytes(html_content: str) -> bytes:
    """Convert rendered HTML to a print-ready, ATS-safe single-column PDF."""
    pdf: bytes = HTML(
        string=html_content,
        base_url=str(TEMPLATES_DIR),
        url_fetcher=_LocalResourceFetcher(),
    ).write_pdf()
    return pdf


def render_pdf(html_content: str, output_path: Path) -> None:
    """Write the PDF for `html_content` to `output_path`, creating parent dirs."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(render_pdf_bytes(html_content))


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
    return CoverLetter.model_validate(_read_yaml(data_path))


def render_cover_letter_html(
    letter: CoverLetter, template_name: str = "cover_letter.html.j2"
) -> str:
    """Render the cover letter data into an HTML string using the Jinja2 template."""
    return _environment().get_template(template_name).render(letter=letter)


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
