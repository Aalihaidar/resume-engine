"""Property-based tests for the code that takes untrusted input.

The API is public and unauthenticated, so the useful properties are about what
must *never* happen whatever the caller sends: validation either accepts the
payload or raises `ValidationError` (never another exception), the photo
resolver never leaves `static/`, rendering never drops or unescapes user text,
and the HTTP layer answers 4xx rather than 500. Hypothesis generates the
inputs; the template files provide a known-good payload to mutate.
"""

from __future__ import annotations

import base64
import contextlib
import copy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

import pytest
import yaml
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from markupsafe import escape
from pydantic import ValidationError

from helpers import png_bytes
from resume_builder.api import app
from resume_builder.models import CoverLetter, Resume
from resume_builder.render import STATIC_DIR, _resolve_photo_path, render_html

DATA_DIR = Path(__file__).parent.parent / "data"

# Rendering and validation are pure CPU work, so a missing deadline only matters on a
# slow CI runner; the example count keeps the whole module to a few seconds.
settings.register_profile(
    "resume-engine",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("resume-engine")

client = TestClient(app)


def _template(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = yaml.safe_load((DATA_DIR / name).read_text(encoding="utf-8"))
    return payload


RESUME_BASE = _template("resume.template.yaml")
RESUME_BASE["photo"] = None
COVER_LETTER_BASE = _template("cover_letter.template.yaml")

# Any JSON document: what a hostile client can put in a request body.
json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(),
    lambda children: st.lists(children, max_size=4) | st.dictionaries(st.text(), children),
    max_leaves=25,
)


def _resume_with(**overrides: Any) -> dict[str, Any]:
    payload = copy.deepcopy(RESUME_BASE)
    payload.update(overrides)
    return payload


# --- validation never fails any other way -----------------------------------


@given(payload=json_values)
def test_arbitrary_json_is_accepted_or_rejected_cleanly(payload: object) -> None:
    for model in (Resume, CoverLetter):
        with contextlib.suppress(ValidationError):
            model.model_validate(payload)


@given(key=st.text(min_size=1), value=json_values)
def test_a_known_good_resume_with_one_field_replaced_fails_cleanly(key: str, value: object) -> None:
    payload = copy.deepcopy(RESUME_BASE)
    payload[key] = value
    with contextlib.suppress(ValidationError):
        Resume.model_validate(payload)


# --- photo handling -----------------------------------------------------------


@given(photo=st.text())
def test_photo_validation_never_raises_anything_but_validation_error(photo: str) -> None:
    with contextlib.suppress(ValidationError):
        Resume.model_validate(_resume_with(photo=photo))


@given(
    mime=st.sampled_from(["png", "jpeg", "webp", "gif", "svg+xml", ""]),
    body=st.binary(max_size=64),
    corrupt=st.text(alphabet="!@# \n=", max_size=4),
)
def test_data_uri_photos_must_be_real_images_in_valid_base64(
    mime: str, body: bytes, corrupt: str
) -> None:
    uri = f"data:image/{mime};base64,{base64.b64encode(body).decode()}{corrupt}"
    try:
        resume = Resume.model_validate(_resume_with(photo=uri))
    except ValidationError:
        return
    # Accepted only when the declared type is allowed, the bytes carry that type's
    # signature and the base64 was clean.
    assert mime in {"png", "jpeg", "webp"}
    assert not corrupt
    assert resume.photo == uri


@given(photo=st.text() | st.sampled_from(["..", "../x", "a/b", "a\\b", "/etc/passwd", ".env"]))
def test_resolved_photo_path_never_leaves_static_dir(photo: str) -> None:
    resolved = _resolve_photo_path(photo)
    if resolved is None:
        return
    if photo.startswith("data:image"):
        assert resolved == photo
    else:
        target = Path(url2pathname(urlparse(resolved).path))
        assert resolved.startswith("file:")
        assert target.parent == STATIC_DIR.resolve()
        assert target.name == photo


def test_a_genuine_png_data_uri_is_accepted() -> None:
    uri = f"data:image/png;base64,{base64.b64encode(png_bytes()).decode()}"
    assert Resume.model_validate(_resume_with(photo=uri)).photo == uri


# --- rendering ----------------------------------------------------------------

# Anything printable; control characters are legal in YAML/JSON but meaningless in a CV.
safe_text = st.text(
    alphabet=st.characters(
        # Surrogates, control characters and the Unicode line/paragraph separators.
        blacklist_categories=("Cs", "Cc", "Zl", "Zp"),
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: s == s.strip())


@given(name=safe_text, headline=safe_text, summary=safe_text)
def test_rendered_html_contains_user_text_escaped(name: str, headline: str, summary: str) -> None:
    resume = Resume.model_validate(_resume_with(name=name, headline=headline, summary=summary))
    html = render_html(resume)
    for value in (name, headline, summary):
        assert str(escape(value)) in html
    # Text that would be markup if it leaked through unescaped never appears raw.
    for value in (name, headline, summary):
        if "<" in value:
            assert value not in html


@given(
    sections=st.fixed_dictionaries({}, optional={k: st.booleans() for k in RESUME_BASE["sections"]})
)
def test_every_section_toggle_combination_renders(sections: dict[str, bool]) -> None:
    payload = _resume_with()
    payload["sections"] = {**RESUME_BASE["sections"], **sections}
    assert render_html(Resume.model_validate(payload))


# --- cover letter placeholders --------------------------------------------------


@given(
    word=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789_-", min_size=0, max_size=20),
    start=st.sampled_from(["A", "Z"]),
)
def test_bracketed_placeholders_are_always_rejected(word: str, start: str) -> None:
    payload = copy.deepcopy(COVER_LETTER_BASE)
    payload["body_paragraphs"] = [f"Hello [{start}{word}] world"]
    with pytest.raises(ValidationError, match="Unfilled template placeholder"):
        CoverLetter.model_validate(payload)


@given(
    paragraph=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="[]"),
        max_size=200,
    )
)
def test_text_without_square_brackets_is_never_mistaken_for_a_placeholder(paragraph: str) -> None:
    payload = copy.deepcopy(COVER_LETTER_BASE)
    payload["body_paragraphs"] = [paragraph]
    CoverLetter.model_validate(payload)


# --- HTTP layer ---------------------------------------------------------------


@settings(max_examples=50)
@given(payload=json_values)
def test_api_answers_422_not_500_for_arbitrary_json(payload: object) -> None:
    for path in ("/api/resume/pdf", "/api/cover-letter/pdf"):
        response = client.post(path, json=payload)
        assert response.status_code == 422


@settings(max_examples=50)
@given(body=st.binary(max_size=2_000))
def test_api_rejects_arbitrary_bytes_without_a_server_error(body: bytes) -> None:
    for path in ("/api/resume/pdf", "/api/cover-letter/pdf"):
        response = client.post(path, content=body, headers={"content-type": "application/json"})
        assert 400 <= response.status_code < 500
