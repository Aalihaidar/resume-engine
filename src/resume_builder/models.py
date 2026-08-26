"""Typed schema for resume.yaml.

Keeping this as a Pydantic model means malformed data (missing fields, wrong
types) fails loudly at build time instead of silently breaking the PDF layout
— important once an AI agent starts editing the YAML unattended.

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
    type, size, and that the payload is actually well-formed base64, since
    this is a no-auth public endpoint (api.py) and nothing else stops a
    caller from POSTing an oversized or malformed value.
  - a plain filename referencing an image inside STATIC_DIR (the original
    CLI workflow) — validated here to reject path separators and '..' so it
    can never be used to reference a file outside STATIC_DIR. render.py
    re-derives the basename and re-checks containment independently, so this
    stays safe even if a Resume is ever constructed without going through
    this validator.
"""

from __future__ import annotations

import base64
import re

from pydantic import BaseModel, EmailStr, HttpUrl, field_validator, model_validator

_PLACEHOLDER_RE = re.compile(r"\[[A-Z][A-Z0-9 _-]*\]")

# --- Photo constraints -------------------------------------------------
# Applied in Resume._validate_photo below.
_DATA_URI_RE = re.compile(r"^data:image/(png|jpeg|jpg|webp);base64,")
MAX_PHOTO_DECODED_BYTES = 3 * 1024 * 1024  # 3MB decoded image
MAX_PHOTO_FILENAME_LEN = 255


class SectionToggles(BaseModel):
    """Master on/off switch for each top-level section of the resume."""

    summary: bool = True
    experience: bool = True
    projects: bool = True
    education: bool = True
    skills: bool = True
    certifications: bool = True
    languages: bool = True
    photo: bool = True


class Contact(BaseModel):
    location: str
    phone: str
    email: EmailStr
    linkedin_display: str
    linkedin_url: HttpUrl
    github_display: str | None = None
    github_url: HttpUrl | None = None


class ExperienceEntry(BaseModel):
    include: bool = True
    title: str
    company: str
    location: str
    start: str
    end: str
    bullets: list[str]


class ProjectLink(BaseModel):
    """A single external link attached to a project (repo, live demo, model card, etc.)."""

    label: str
    url: HttpUrl


class ProjectEntry(BaseModel):
    """One personal/academic/freelance project.

    Distinct from `ExperienceEntry` because projects are typically unpaid,
    tied to an organization only loosely (e.g. "Associated with X
    University"), and benefit from an explicit `technologies` list and
    clickable `links` (repo, live demo, published model, etc.) that a job
    doesn't need.
    """

    include: bool = True
    name: str
    organization: str | None = None
    start: str
    end: str
    bullets: list[str] = []
    technologies: list[str] = []
    links: list[ProjectLink] = []


class EducationEntry(BaseModel):
    include: bool = True
    degree: str
    institution: str
    location: str
    start: str
    end: str
    details: list[str] = []


class SkillGroup(BaseModel):
    include: bool = True
    category: str
    items: list[str]


class Certification(BaseModel):
    include: bool = True
    name: str
    issuer: str
    date: str


class Language(BaseModel):
    include: bool = True
    name: str
    level: str


class Resume(BaseModel):
    name: str
    headline: str
    contact: Contact
    photo: str | None = None
    sections: SectionToggles = SectionToggles()
    summary: str
    experience: list[ExperienceEntry] = []
    projects: list[ProjectEntry] = []
    education: list[EducationEntry] = []
    skills: list[SkillGroup] = []
    certifications: list[Certification] = []
    languages: list[Language] = []

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
                base64.b64decode(b64_data, validate=True)
            except Exception as exc:
                raise ValueError("photo data URI is not valid base64") from exc

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


class CoverLetterSectionToggles(BaseModel):
    """Master on/off switch for each part of the cover letter."""

    date: bool = True
    recipient: bool = True
    body: bool = True


class CoverLetterRecipient(BaseModel):
    name: str | None = None
    title: str | None = None
    company: str
    company_address: str | None = None


class CoverLetter(BaseModel):
    applicant_name: str
    applicant_contact: Contact
    date: str
    recipient: CoverLetterRecipient
    role_title: str
    salutation: str = "Dear Hiring Manager,"
    sections: CoverLetterSectionToggles = CoverLetterSectionToggles()
    body_paragraphs: list[str] = []
    closing: str = "Sincerely,"

    @model_validator(mode="after")
    def _no_leftover_placeholders(self) -> CoverLetter:
        """Fail the build if a [BRACKET] template placeholder was never
        filled in — e.g. role_title left as "[JOB TITLE]" or a recipient
        company left as "[COMPANY NAME]". Without this, an unfilled
        placeholder renders straight into the PDF silently.
        """
        candidates = {
            "role_title": self.role_title,
            "recipient.company": self.recipient.company,
            "recipient.name": self.recipient.name,
            "recipient.title": self.recipient.title,
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
