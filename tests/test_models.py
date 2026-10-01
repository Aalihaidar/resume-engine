from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from helpers import data_uri
from resume_builder.models import (
    MAX_BULLETS,
    MAX_ENTRIES,
    MAX_PHOTO_DECODED_BYTES,
    CoverLetter,
    Resume,
)


def _errors(exc: pytest.ExceptionInfo[ValidationError]) -> str:
    return str(exc.value)


# --- strictness -----------------------------------------------------------


def test_unknown_top_level_field_is_rejected(resume_payload: dict[str, Any]) -> None:
    resume_payload["experiance"] = []  # the typo that used to be silently dropped
    with pytest.raises(ValidationError, match="experiance"):
        Resume.model_validate(resume_payload)


def test_unknown_nested_field_is_rejected(resume_payload: dict[str, Any]) -> None:
    resume_payload["experience"] = [
        {
            "title": "t",
            "company": "c",
            "location": "l",
            "start": "s",
            "end": "e",
            "bulets": ["typo"],
            "bullets": [],
        }
    ]
    with pytest.raises(ValidationError, match="bulets"):
        Resume.model_validate(resume_payload)


def test_unknown_cover_letter_field_is_rejected(cover_letter_payload: dict[str, Any]) -> None:
    cover_letter_payload["body_paragraph"] = ["typo"]
    with pytest.raises(ValidationError, match="body_paragraph"):
        CoverLetter.model_validate(cover_letter_payload)


def test_defaults_are_not_shared_between_instances(resume_payload: dict[str, Any]) -> None:
    first = Resume.model_validate(resume_payload)
    second = Resume.model_validate(resume_payload)
    first.sections.summary = False
    assert second.sections.summary is True


# --- size limits ----------------------------------------------------------


def test_overlong_string_is_rejected(resume_payload: dict[str, Any]) -> None:
    resume_payload["name"] = "x" * 201
    with pytest.raises(ValidationError, match="name"):
        Resume.model_validate(resume_payload)


def test_too_many_entries_are_rejected(resume_payload: dict[str, Any]) -> None:
    resume_payload["skills"] = [{"category": "c", "items": ["i"]}] * (MAX_ENTRIES + 1)
    with pytest.raises(ValidationError, match="skills"):
        Resume.model_validate(resume_payload)


def test_too_many_bullets_are_rejected(resume_payload: dict[str, Any]) -> None:
    job = {"title": "t", "company": "c", "location": "l", "start": "s", "end": "e"}
    resume_payload["experience"] = [{**job, "bullets": ["b"] * (MAX_BULLETS + 1)}]
    with pytest.raises(ValidationError, match="bullets"):
        Resume.model_validate(resume_payload)


# --- photo ----------------------------------------------------------------


@pytest.mark.parametrize("value", [None, ""])
def test_empty_photo_is_allowed(resume_payload: dict[str, Any], value: str | None) -> None:
    resume_payload["photo"] = value
    assert Resume.model_validate(resume_payload).photo == value


def test_valid_png_data_uri_is_accepted(resume_payload: dict[str, Any], png_data_uri: str) -> None:
    resume_payload["photo"] = png_data_uri
    assert Resume.model_validate(resume_payload).photo == png_data_uri


@pytest.mark.parametrize(
    ("mime", "payload"),
    [
        ("jpeg", b"\xff\xd8\xff\xe0" + b"\x00" * 16),
        ("webp", b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 12),
    ],
)
def test_other_supported_formats_are_accepted(
    resume_payload: dict[str, Any], mime: str, payload: bytes
) -> None:
    resume_payload["photo"] = data_uri(mime, payload)
    Resume.model_validate(resume_payload)


def test_photo_with_wrong_magic_bytes_is_rejected(resume_payload: dict[str, Any]) -> None:
    # Declared as PNG, but the bytes are a script: the MIME type is caller-controlled.
    resume_payload["photo"] = data_uri("png", b"<script>alert(1)</script>")
    with pytest.raises(ValidationError, match="not a valid png image"):
        Resume.model_validate(resume_payload)


def test_photo_png_declared_but_jpeg_bytes_is_rejected(resume_payload: dict[str, Any]) -> None:
    resume_payload["photo"] = data_uri("png", b"\xff\xd8\xff\xe0" + b"\x00" * 16)
    with pytest.raises(ValidationError, match="not a valid png image"):
        Resume.model_validate(resume_payload)


@pytest.mark.parametrize("mime", ["gif", "svg+xml", "jpg", "bmp"])
def test_unsupported_image_type_is_rejected(resume_payload: dict[str, Any], mime: str) -> None:
    resume_payload["photo"] = f"data:image/{mime};base64,AAAA"
    with pytest.raises(ValidationError, match="must start with one of"):
        Resume.model_validate(resume_payload)


def test_malformed_base64_is_rejected(resume_payload: dict[str, Any]) -> None:
    resume_payload["photo"] = "data:image/png;base64,@@@@"
    with pytest.raises(ValidationError, match="not valid base64"):
        Resume.model_validate(resume_payload)


def test_oversized_photo_is_rejected_before_decoding(resume_payload: dict[str, Any]) -> None:
    resume_payload["photo"] = "data:image/png;base64," + "A" * (MAX_PHOTO_DECODED_BYTES * 2)
    with pytest.raises(ValidationError, match="too large"):
        Resume.model_validate(resume_payload)


@pytest.mark.parametrize(
    "value",
    ["../secret.jpg", "a/b.jpg", "..\\secret.jpg", "/etc/passwd", "..", ".", "C:\\x.jpg"],
)
def test_photo_filename_cannot_be_a_path(resume_payload: dict[str, Any], value: str) -> None:
    resume_payload["photo"] = value
    with pytest.raises(ValidationError, match="path separators"):
        Resume.model_validate(resume_payload)


def test_photo_filename_length_is_bounded(resume_payload: dict[str, Any]) -> None:
    resume_payload["photo"] = "a" * 300 + ".jpg"
    with pytest.raises(ValidationError, match="too long"):
        Resume.model_validate(resume_payload)


def test_plain_photo_filename_is_accepted(resume_payload: dict[str, Any]) -> None:
    resume_payload["photo"] = "headshot.jpg"
    assert Resume.model_validate(resume_payload).photo == "headshot.jpg"


# --- visibility (section switch AND entry flag) ---------------------------


def _resume_with_one_of_everything(resume_payload: dict[str, Any]) -> dict[str, Any]:
    resume_payload.update(
        experience=[
            {
                "title": "A",
                "company": "c",
                "location": "l",
                "start": "s",
                "end": "e",
                "bullets": [],
            },
            {
                "include": False,
                "title": "B",
                "company": "c",
                "location": "l",
                "start": "s",
                "end": "e",
                "bullets": [],
            },
        ],
        projects=[
            {"name": "P", "start": "s", "end": "e"},
            {"include": False, "name": "Q", "start": "s", "end": "e"},
        ],
        education=[
            {"degree": "D", "institution": "i", "location": "l", "start": "s", "end": "e"},
            {
                "include": False,
                "degree": "E",
                "institution": "i",
                "location": "l",
                "start": "s",
                "end": "e",
            },
        ],
        skills=[
            {"category": "K", "items": ["x"]},
            {"include": False, "category": "L", "items": ["y"]},
        ],
        certifications=[
            {"name": "N", "issuer": "i", "date": "d"},
            {"include": False, "name": "O", "issuer": "i", "date": "d"},
        ],
        languages=[{"name": "En", "level": "C2"}, {"include": False, "name": "De", "level": "B1"}],
    )
    return resume_payload


def test_entry_flag_hides_single_entries(resume_payload: dict[str, Any]) -> None:
    resume = Resume.model_validate(_resume_with_one_of_everything(resume_payload))
    assert [e.title for e in resume.visible_experience] == ["A"]
    assert [p.name for p in resume.visible_projects] == ["P"]
    assert [e.degree for e in resume.visible_education] == ["D"]
    assert [s.category for s in resume.visible_skills] == ["K"]
    assert [c.name for c in resume.visible_certifications] == ["N"]
    assert [lang.name for lang in resume.visible_languages] == ["En"]


@pytest.mark.parametrize(
    "section",
    ["experience", "projects", "education", "skills", "certifications", "languages"],
)
def test_section_switch_hides_whole_section(resume_payload: dict[str, Any], section: str) -> None:
    payload = _resume_with_one_of_everything(resume_payload)
    payload["sections"] = {section: False}
    resume = Resume.model_validate(payload)
    assert getattr(resume, f"visible_{section}") == []


def test_summary_and_photo_switches(resume_payload: dict[str, Any], png_data_uri: str) -> None:
    resume_payload["photo"] = png_data_uri
    resume = Resume.model_validate(resume_payload)
    assert resume.show_summary
    assert resume.show_photo

    resume_payload["sections"] = {"summary": False, "photo": False}
    resume = Resume.model_validate(resume_payload)
    assert not resume.show_summary
    assert not resume.show_photo


# --- cover letter ---------------------------------------------------------


def test_cover_letter_template_is_valid(cover_letter_payload: dict[str, Any]) -> None:
    letter = CoverLetter.model_validate(cover_letter_payload)
    assert letter.show_date
    assert letter.show_recipient
    assert letter.visible_body == letter.body_paragraphs


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("role_title", "role_title"),
        ("applicant_name", "applicant_name"),
        ("salutation", "salutation"),
        ("closing", "closing"),
        ("date", "date"),
    ],
)
def test_unfilled_placeholder_fails_the_build(
    cover_letter_payload: dict[str, Any], field: str, expected: str
) -> None:
    cover_letter_payload[field] = "[JOB TITLE]"
    with pytest.raises(ValidationError, match=expected):
        CoverLetter.model_validate(cover_letter_payload)


def test_placeholder_in_recipient_or_body_fails_the_build(
    cover_letter_payload: dict[str, Any],
) -> None:
    cover_letter_payload["recipient"]["company"] = "[COMPANY NAME]"
    cover_letter_payload["body_paragraphs"] = ["Fine.", "Hello [NAME], welcome."]
    with pytest.raises(ValidationError) as exc:
        CoverLetter.model_validate(cover_letter_payload)
    assert "recipient.company" in _errors(exc)
    assert "body_paragraphs[1]" in _errors(exc)


def test_lowercase_brackets_are_not_placeholders(cover_letter_payload: dict[str, Any]) -> None:
    cover_letter_payload["body_paragraphs"] = ["See reference [1] and [a note]."]
    CoverLetter.model_validate(cover_letter_payload)


def test_cover_letter_switches(cover_letter_payload: dict[str, Any]) -> None:
    cover_letter_payload["sections"] = {"date": False, "recipient": False, "body": False}
    letter = CoverLetter.model_validate(cover_letter_payload)
    assert not letter.show_date
    assert not letter.show_recipient
    assert letter.visible_body == []
