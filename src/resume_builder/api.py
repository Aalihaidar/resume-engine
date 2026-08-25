"""
resume_builder.api
-------------------
Thin HTTP layer around the existing render pipeline.

Reuses the same Pydantic models (Resume, CoverLetter) and the same
render_html/render_pdf functions the CLI uses — no logic is duplicated.

Endpoints:
  POST /api/resume/pdf         body: Resume JSON      -> returns application/pdf
  POST /api/cover-letter/pdf   body: CoverLetter JSON  -> returns application/pdf
  GET  /healthz                -> {"status": "ok"}
  GET  /                        -> serves static/index.html (manual JSON-fill UI)

Any app or AI agent can call the two POST endpoints directly with a JSON
body matching schema/resume.schema.json — no auth, no YAML step.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from resume_builder.models import CoverLetter, Resume
from resume_builder.render import render_cover_letter_html, render_html

APP_DIR = Path(__file__).parent
WEB_STATIC_DIR = APP_DIR / "web_static"

app = FastAPI(
    title="resume-engine API",
    description="POST a resume or cover letter as JSON, get back a PDF.",
    version="1.0.0",
)


def _pdf_response(html_content: str, filename: str) -> StreamingResponse:
    buf = io.BytesIO()
    # render_pdf() writes to a path, so we hand it a temp path via BytesIO
    # by reusing the same WeasyPrint call it wraps internally.
    from weasyprint import HTML

    HTML(string=html_content, base_url=str(APP_DIR / "templates")).write_pdf(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/resume/pdf")
def resume_pdf(payload: dict[str, Any]) -> StreamingResponse:
    try:
        resume = Resume.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    html_content = render_html(resume)
    return _pdf_response(html_content, "resume.pdf")


@app.post("/api/cover-letter/pdf")
def cover_letter_pdf(payload: dict[str, Any]) -> StreamingResponse:
    try:
        letter = CoverLetter.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    html_content = render_cover_letter_html(letter)
    return _pdf_response(html_content, "cover_letter.pdf")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    index_file = WEB_STATIC_DIR / "index.html"
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


# Serves /schema/resume.schema.json etc. if you copy them in; safe to omit.
if (WEB_STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_STATIC_DIR / "assets")), name="assets")
