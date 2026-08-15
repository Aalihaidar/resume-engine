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
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, HttpUrl


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

    @property
    def show_date(self) -> bool:
        return self.sections.date and bool(self.date)

    @property
    def show_recipient(self) -> bool:
        return self.sections.recipient and bool(self.recipient.company)

    @property
    def visible_body(self) -> list[str]:
        return self.body_paragraphs if self.sections.body else []
