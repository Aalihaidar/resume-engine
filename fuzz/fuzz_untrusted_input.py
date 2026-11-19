"""Coverage-guided fuzzing of the code that takes untrusted input, with Atheris.

tests/test_fuzz.py states the properties with Hypothesis; this harness hands the
same entry points to libFuzzer, which mutates raw bytes and keeps any input that
reaches new code in resume_builder. The API is public and unauthenticated, so a
crash here is anything a caller could turn into a 500: an exception other than
`ValidationError`, a photo that resolves outside `static/`, or rendered HTML that
lost the user's text or stopped escaping it. libFuzzer saves the input that
caused it.

Atheris only ships Linux x86-64 wheels, hence the `fuzz` dependency group and
the dev container on other platforms:

    make fuzz                       # 60 seconds; FUZZ_SECONDS=600 make fuzz for longer
    uv run --group fuzz python fuzz/fuzz_untrusted_input.py output/fuzz/crash-<hash>
"""

from __future__ import annotations

import contextlib
import copy
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

import atheris
import yaml

with atheris.instrument_imports(include=["resume_builder"]):
    from markupsafe import escape
    from pydantic import ValidationError

    from resume_builder.models import CoverLetter, Resume
    from resume_builder.render import (
        STATIC_DIR,
        _resolve_photo_path,
        render_cover_letter_html,
        render_html,
    )

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATIC_ROOT = STATIC_DIR.resolve()

# Returned by _decode when the bytes are not JSON; None is a valid JSON value.
_NOT_JSON = object()


def _template(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = yaml.safe_load((DATA_DIR / name).read_text(encoding="utf-8"))
    return payload


RESUME_BASE = _template("resume.template.yaml")
RESUME_BASE["photo"] = None
COVER_LETTER_BASE = _template("cover_letter.template.yaml")


def _decode(text: str) -> object:
    try:
        return json.loads(text)
    # Deeply nested arrays exhaust the parser's recursion before validation sees them.
    except ValueError, RecursionError:
        return _NOT_JSON


def _value(fdp: atheris.FuzzedDataProvider) -> object:
    """The rest of the input, as a JSON value when it parses and as plain text otherwise."""
    text = fdp.ConsumeUnicodeNoSurrogates(fdp.remaining_bytes())
    value = _decode(text)
    return text if value is _NOT_JSON else value


def _mutate(base: dict[str, Any], fdp: atheris.FuzzedDataProvider) -> dict[str, Any]:
    """A copy of a known-good payload with one field, at any depth, replaced.

    Arbitrary JSON almost never validates, so this is what lets the fuzzer get past
    the models and into rendering.
    """
    payload = copy.deepcopy(base)
    node: Any = payload
    while True:
        keys = list(node) if isinstance(node, dict) else list(range(len(node)))
        key = keys[fdp.ConsumeIntInRange(0, len(keys) - 1)]
        child = node[key]
        if isinstance(child, dict | list) and child and fdp.ConsumeBool():
            node = child
            continue
        node[key] = _value(fdp)
        return payload


def _check_resume(payload: object) -> None:
    try:
        resume = Resume.model_validate(payload)
    except ValidationError:
        return
    html = render_html(resume)
    if str(escape(resume.name)) not in html:
        raise AssertionError(f"rendered resume lost or unescaped the name {resume.name!r}")


def _check_cover_letter(payload: object) -> None:
    try:
        letter = CoverLetter.model_validate(payload)
    except ValidationError:
        return
    render_cover_letter_html(letter)


def _check_photo(photo: str) -> None:
    resolved = _resolve_photo_path(photo)
    if resolved is not None and not photo.startswith("data:image"):
        target = Path(url2pathname(urlparse(resolved).path))
        if target.parent != STATIC_ROOT or target.name != photo:
            raise AssertionError(f"photo {photo!r} resolved outside static/: {resolved}")
    with contextlib.suppress(ValidationError):
        Resume.model_validate({**RESUME_BASE, "photo": photo})


def test_one_input(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    match fdp.ConsumeIntInRange(0, 4):
        case 0:
            _check_resume(_value(fdp))
        case 1:
            _check_cover_letter(_value(fdp))
        case 2:
            _check_resume(_mutate(RESUME_BASE, fdp))
        case 3:
            _check_cover_letter(_mutate(COVER_LETTER_BASE, fdp))
        case _:
            _check_photo(fdp.ConsumeUnicodeNoSurrogates(fdp.remaining_bytes()))


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
