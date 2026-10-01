"""
resume_builder.api
-------------------
Thin HTTP layer around the existing render pipeline.

Reuses the same Pydantic models (Resume, CoverLetter) and the same
render_html/render_pdf_bytes functions the CLI uses — no logic is duplicated.

Endpoints:
  POST /api/resume/pdf         body: Resume JSON      -> returns application/pdf
  POST /api/cover-letter/pdf   body: CoverLetter JSON  -> returns application/pdf
  GET  /healthz                -> {"status": "ok"}
  GET  /                        -> serves web_static/index.html (manual YAML-fill UI;
                                    converts to JSON client-side before posting)
  GET  /assets/*               -> the UI's own CSS, script and fonts (self-hosted)

Any app or AI agent can call the two POST endpoints directly with a JSON
body matching schema/resume.schema.json — no auth, no YAML step.

Since there's no auth, several independent layers keep the service safe to
expose (none of them is relied on to cover for another):
  - MaxBodySizeMiddleware (middleware.py) caps request size before Pydantic
    validation ever runs;
  - the models (models.py) reject unknown fields, bound every string and
    list, and validate Resume.photo (MIME type, magic bytes, decoded size);
  - validation errors never echo the request back (the framework default repeats
    the whole offending input once per error, which would multiply a large body);
  - the filename form of `photo` references a file baked into the server, so
    it is refused here — over HTTP a photo has to be sent inline. (render.py's
    `_resolve_photo_path` still re-checks containment for the CLI path.);
  - rendering is CPU-heavy, so at most RESUME_MAX_CONCURRENT_RENDERS PDFs are
    produced at once and the rest get a 503 + Retry-After instead of piling up;
  - WeasyPrint may only read local template files (render.py).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from resume_builder import __version__
from resume_builder.middleware import (
    MAX_BODY_BYTES,
    MaxBodySizeMiddleware,
    SecurityHeadersMiddleware,
)
from resume_builder.models import CoverLetter, Resume
from resume_builder.render import render_cover_letter_html, render_html, render_pdf_bytes

APP_DIR = Path(__file__).parent
WEB_STATIC_DIR = APP_DIR / "web_static"

# Development only: lets an editor's embedded browser (VS Code's Simple Browser
# shows pages in an iframe) display the page. The dev container's start script
# sets it; production never does, and the page then refuses to be framed at all.
ALLOW_EMBEDDING = os.environ.get("RESUME_ALLOW_EMBEDDING") == "1"


def content_security_policy(allow_embedding: bool = False) -> str:
    """The page's policy. The UI is fully self-hosted (no CDN scripts, styles or
    fonts), so it can be closed by default. blob: covers the PDF the page just
    fetched (frame/object) and the photo it decodes client-side before
    downscaling it (img).
    """
    return "; ".join(
        [
            "default-src 'self'",
            "img-src 'self' data: blob:",
            "frame-src blob:",
            "object-src blob:",
            "base-uri 'none'",
            "form-action 'none'",
            "frame-ancestors *" if allow_embedding else "frame-ancestors 'none'",
        ]
    )


CONTENT_SECURITY_POLICY = content_security_policy(ALLOW_EMBEDDING)

_RENDER_QUEUE_TIMEOUT_SECONDS = 10.0


def _max_concurrent_renders() -> int:
    try:
        return max(1, int(os.environ.get("RESUME_MAX_CONCURRENT_RENDERS", "2")))
    except ValueError:
        return 2


_render_slots = threading.BoundedSemaphore(_max_concurrent_renders())

app = FastAPI(
    title="resume-engine API",
    description=(
        "POST a resume or cover letter as JSON, get back a PDF. "
        f"Request bodies are limited to {MAX_BODY_BYTES // 1024 // 1024} MB and unknown "
        "fields are rejected."
    ),
    version=__version__,
)

# Added last = outermost, so the headers also cover the 413 sent by the size cap.
app.add_middleware(MaxBodySizeMiddleware, max_bytes=MAX_BODY_BYTES)
app.add_middleware(SecurityHeadersMiddleware, allow_framing=ALLOW_EMBEDDING)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """422 with where/what for each problem, but without `input` and `ctx`."""
    detail = [
        {key: value for key, value in error.items() if key not in {"input", "ctx", "url"}}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detail})


_PDF_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {"content": {"application/pdf": {}}, "description": "The rendered PDF."},
    413: {"description": "Request body larger than the size cap."},
    503: {"description": "All render slots are busy; retry after the `Retry-After` delay."},
}


def _pdf_response(html_content: str, filename: str) -> Response:
    if not _render_slots.acquire(timeout=_RENDER_QUEUE_TIMEOUT_SECONDS):
        raise HTTPException(
            status_code=503,
            detail="Renderer is busy, retry shortly",
            headers={"Retry-After": "5"},
        )
    try:
        pdf = render_pdf_bytes(html_content)
    finally:
        _render_slots.release()

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # The body is someone's CV; keep it out of shared caches.
            "Cache-Control": "no-store",
        },
    )


@app.head("/healthz", include_in_schema=False)
@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/resume/pdf", response_class=Response, responses=_PDF_RESPONSES)
def resume_pdf(resume: Resume) -> Response:
    if resume.photo and not resume.photo.startswith("data:image"):
        # Same shape as the framework's own 422 items, so clients handle one format.
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "type": "value_error",
                    "loc": ["body", "photo"],
                    "msg": "photo must be an inline data:image/... URI over HTTP; "
                    "filename references are only available to the CLI",
                }
            ],
        )

    return _pdf_response(render_html(resume), "resume.pdf")


@app.post("/api/cover-letter/pdf", response_class=Response, responses=_PDF_RESPONSES)
def cover_letter_pdf(letter: CoverLetter) -> Response:
    return _pdf_response(render_cover_letter_html(letter), "cover_letter.pdf")


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(
        WEB_STATIC_DIR / "index.html",
        media_type="text/html",
        headers={"Content-Security-Policy": CONTENT_SECURITY_POLICY},
    )


app.mount("/assets", StaticFiles(directory=WEB_STATIC_DIR / "assets"), name="assets")
