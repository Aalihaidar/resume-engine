"""Typed schema for resume.yaml and cover_letter.yaml.

Keeping this as a Pydantic model means malformed data (missing fields, wrong
types) fails loudly at build time instead of silently breaking the PDF layout
— important once an AI agent starts editing the YAML unattended.

Strictness
----------
Every model rejects unknown keys (`extra="forbid"`). Without that, a typo such
as `experiance:` or `bulets:` validates fine and the content is silently
dropped from the PDF. Strings and lists also carry generous length limits: they
never trip on real content, but they bound how much work a single request to
the public, no-auth API (api.py) can make the renderer do.

Visibility model
-----------------
Two independent layers of control, both additive (both must be true for
something to render):

1. `sections` — one master boolean per top-level section. Turns the whole
   section off (e.g. no Certifications block at all) without touching its
   data.
2. `include` on each list entry (experience job, education entry, skill
   group, certification, language) — drop a single entry (e.g. one job)
   while keeping the section itself and every other entry.

This lets an AI agent (or you) tailor a resume per job application by
flipping booleans instead of deleting/re-adding content.

Photo validation
-----------------
`Resume.photo` accepts two forms (see render.py for how each is resolved):
  - a `data:image/{png,jpeg,webp};base64,...` URI — validated here for MIME
    type, size, that the payload is well-formed base64, and that the decoded
    bytes really start with the signature of the declared image type, since
    this is a no-auth public endpoint (api.py) and nothing else stops a
    caller from POSTing an oversized or malformed value.
  - a plain filename referencing an image inside STATIC_DIR (the original
    CLI workflow) — validated here to reject path separators and '..' so it
    can never be used to reference a file outside STATIC_DIR. render.py
    re-derives the basename and re-checks containment independently, so this
    stays safe even if a Resume is ever constructed without going through
    this validator. The HTTP API additionally refuses this form altogether.
"""

from __future__ import annotations

import base64
import re
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
    model_validator,
)

_PLACEHOLDER_RE = re.compile(r"\[[A-Z][A-Z0-9 _-]*\]")

# --- Photo constraints -------------------------------------------------
# Applied in Resume._validate_photo below.
_DATA_URI_RE = re.compile(r"^data:image/(png|jpeg|webp);base64,")
MAX_PHOTO_DECODED_BYTES = 3 * 1024 * 1024  # 3MB decoded image
MAX_PHOTO_FILENAME_LEN = 255

# --- Size limits -------------------------------------------------------
# Far above anything a real resume needs; they exist to bound render work.
ShortText = Annotated[str, StringConstraints(max_length=200)]
LongText = Annotated[str, StringConstraints(max_length=2_000)]
Paragraph = Annotated[str, StringConstraints(max_length=5_000)]
MAX_ENTRIES = 50
MAX_BULLETS = 30


def _has_image_signature(kind: str, data: bytes) -> bool:
    """True when `data` starts with the magic bytes of the declared image type."""
    if kind == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if kind == "jpeg":
        return data.startswith(b"\xff\xd8\xff")
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"  # webp


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SectionToggles(_StrictModel):
    """Master on/off switch for each top-level section of the resume."""

    summary: bool = True
    experience: bool = True
    projects: bool = True
    education: bool = True
    skills: bool = True
    certifications: bool = True
    languages: bool = True
    photo: bool = True


class Contact(_StrictModel):
    location: ShortText
    phone: ShortText
    email: EmailStr
    linkedin_display: ShortText
    linkedin_url: HttpUrl
    github_display: ShortText | None = None
    github_url: HttpUrl | None = None


class ExperienceEntry(_StrictModel):
    include: bool = True
    title: ShortText
    company: ShortText
    location: ShortText
    start: ShortText
    end: ShortText
    bullets: list[LongText] = Field(max_length=MAX_BULLETS)


class ProjectLink(_StrictModel):
    """A single external link attached to a project (repo, live demo, model card, etc.)."""

    label: ShortText
    url: HttpUrl


class ProjectEntry(_StrictModel):
    """One personal/academic/freelance project.

    Distinct from `ExperienceEntry` because projects are typically unpaid,
    tied to an organization only loosely (e.g. "Associated with X
    University"), and benefit from an explicit `technologies` list and
    clickable `links` (repo, live demo, published model, etc.) that a job
    doesn't need.
    """

    include: bool = True
    name: ShortText
    organization: ShortText | None = None
    start: ShortText
    end: ShortText
    bullets: list[LongText] = Field(default_factory=list, max_length=MAX_BULLETS)
    technologies: list[ShortText] = Field(default_factory=list, max_length=MAX_ENTRIES)
    links: list[ProjectLink] = Field(default_factory=list, max_length=MAX_BULLETS)


class EducationEntry(_StrictModel):
    include: bool = True
    degree: ShortText
    institution: ShortText
    location: ShortText
    start: ShortText
    end: ShortText
    details: list[LongText] = Field(default_factory=list, max_length=MAX_BULLETS)


class SkillGroup(_StrictModel):
    include: bool = True
    category: ShortText
    items: list[ShortText] = Field(max_length=MAX_ENTRIES)


class Certification(_StrictModel):
    include: bool = True
    name: ShortText
    issuer: ShortText
    date: ShortText


class Language(_StrictModel):
    include: bool = True
    name: ShortText
    level: ShortText


class Resume(_StrictModel):
    name: ShortText
    headline: LongText
    contact: Contact
    photo: str | None = None
    sections: SectionToggles = Field(default_factory=SectionToggles)
    summary: Paragraph
    experience: list[ExperienceEntry] = Field(default_factory=list, max_length=MAX_ENTRIES)
    projects: list[ProjectEntry] = Field(default_factory=list, max_length=MAX_ENTRIES)
    education: list[EducationEntry] = Field(default_factory=list, max_length=MAX_ENTRIES)
    skills: list[SkillGroup] = Field(default_factory=list, max_length=MAX_ENTRIES)
    certifications: list[Certification] = Field(default_factory=list, max_length=MAX_ENTRIES)
    languages: list[Language] = Field(default_factory=list, max_length=MAX_ENTRIES)

    @field_validator("photo")
    @classmethod
    def _validate_photo(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v

        if v.startswith("data:image"):
            match = _DATA_URI_RE.match(v)
            if not match:
                raise ValueError(
                    "photo data URI must start with one of: "
                    "data:image/png;base64,  data:image/jpeg;base64,  "
                    "data:image/webp;base64,"
                )

            b64_data = v[match.end() :]

            # Base64 expands data by ~4/3 — reject on the *encoded* length
            # first (cheap, no decode) so an oversized payload never gets
            # fully decoded just to be rejected.
            approx_decoded_bytes = len(b64_data) * 3 // 4
            if approx_decoded_bytes > MAX_PHOTO_DECODED_BYTES:
                raise ValueError(
                    f"photo is too large (~{approx_decoded_bytes / 1024 / 1024:.1f}MB "
                    f"decoded, max {MAX_PHOTO_DECODED_BYTES / 1024 / 1024:.0f}MB). "
                    "Compress or downscale it before submitting."
                )

            # Confirms the payload is actually well-formed base64 — catches a
            # truncated/corrupt data URI here, with a clear error, instead of
            # failing deep inside WeasyPrint mid-render.
            try:
                decoded = base64.b64decode(b64_data, validate=True)
            except ValueError as exc:
                raise ValueError("photo data URI is not valid base64") from exc

            # The declared MIME type is caller-controlled; the bytes decide.
            if not _has_image_signature(match.group(1), decoded):
                raise ValueError(f"photo bytes are not a valid {match.group(1)} image")

            return v

        # Otherwise this is a plain filename referencing an image inside
        # STATIC_DIR (the CLI workflow) — never a path. Reject anything that
        # could traverse outside STATIC_DIR; render.py independently
        # re-derives the basename and re-checks containment too.
        if len(v) > MAX_PHOTO_FILENAME_LEN:
            raise ValueError(f"photo filename is too long (max {MAX_PHOTO_FILENAME_LEN} chars)")
        if "/" in v or "\\" in v or v in {".", ".."}:
            raise ValueError(
                "photo must be a data:image/... URI or a plain filename with no "
                "path separators or '..' (it's resolved inside the app's static "
                "images directory, not an arbitrary path)"
            )
        return v

    # --- Visibility helpers -------------------------------------------------
    # Centralizing the "section on AND entry included" logic here keeps the
    # template dumb (no boolean logic in Jinja) and keeps this logic unit
    # testable without rendering HTML.

    @property
    def show_summary(self) -> bool:
        return self.sections.summary and bool(self.summary)

    @property
    def show_photo(self) -> bool:
        return self.sections.photo and bool(self.photo)

    @property
    def visible_experience(self) -> list[ExperienceEntry]:
        if not self.sections.experience:
            return []
        return [e for e in self.experience if e.include]

    @property
    def visible_projects(self) -> list[ProjectEntry]:
        if not self.sections.projects:
            return []
        return [p for p in self.projects if p.include]

    @property
    def visible_education(self) -> list[EducationEntry]:
        if not self.sections.education:
            return []
        return [e for e in self.education if e.include]

    @property
    def visible_skills(self) -> list[SkillGroup]:
        if not self.sections.skills:
            return []
        return [s for s in self.skills if s.include]

    @property
    def visible_certifications(self) -> list[Certification]:
        if not self.sections.certifications:
            return []
        return [c for c in self.certifications if c.include]

    @property
    def visible_languages(self) -> list[Language]:
        if not self.sections.languages:
            return []
        return [lang for lang in self.languages if lang.include]


class CoverLetterSectionToggles(_StrictModel):
    """Master on/off switch for each part of the cover letter."""

    date: bool = True
    recipient: bool = True
    body: bool = True


class CoverLetterRecipient(_StrictModel):
    name: ShortText | None = None
    title: ShortText | None = None
    company: ShortText
    company_address: LongText | None = None


class CoverLetter(_StrictModel):
    applicant_name: ShortText
    applicant_contact: Contact
    date: ShortText
    recipient: CoverLetterRecipient
    role_title: ShortText
    salutation: ShortText = "Dear Hiring Manager,"
    sections: CoverLetterSectionToggles = Field(default_factory=CoverLetterSectionToggles)
    body_paragraphs: list[Paragraph] = Field(default_factory=list, max_length=MAX_BULLETS)
    closing: ShortText = "Sincerely,"

    @model_validator(mode="after")
    def _no_leftover_placeholders(self) -> CoverLetter:
        """Fail the build if a [BRACKET] template placeholder was never
        filled in — e.g. role_title left as "[JOB TITLE]" or a recipient
        company left as "[COMPANY NAME]". Without this, an unfilled
        placeholder renders straight into the PDF silently.
        """
        candidates = {
            "applicant_name": self.applicant_name,
            "role_title": self.role_title,
            "salutation": self.salutation,
            "closing": self.closing,
            "recipient.company": self.recipient.company,
            "recipient.name": self.recipient.name,
            "recipient.title": self.recipient.title,
            "recipient.company_address": self.recipient.company_address,
            "date": self.date,
            **{f"body_paragraphs[{i}]": p for i, p in enumerate(self.body_paragraphs)},
        }
        offenders = [
            field for field, value in candidates.items() if value and _PLACEHOLDER_RE.search(value)
        ]
        if offenders:
            raise ValueError(
                "Unfilled template placeholder(s) found in cover_letter.yaml: "
                f"{', '.join(offenders)}. Replace the [BRACKETED] text with "
                "real content before building."
            )
        return self

    @property
    def show_date(self) -> bool:
        return self.sections.date and bool(self.date)

    @property
    def show_recipient(self) -> bool:
        return self.sections.recipient and bool(self.recipient.company)

    @property
    def visible_body(self) -> list[str]:
        return self.body_paragraphs if self.sections.body else []
