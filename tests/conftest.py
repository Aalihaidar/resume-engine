from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from helpers import data_uri, png_bytes
from resume_builder.api import app

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"


@pytest.fixture
def png_data_uri() -> str:
    return data_uri("png", png_bytes())


@pytest.fixture
def resume_payload() -> dict[str, Any]:
    """A valid resume as the plain dict an API client would POST."""
    payload: dict[str, Any] = yaml.safe_load(
        (DATA_DIR / "resume.template.yaml").read_text(encoding="utf-8")
    )
    payload["photo"] = None  # the template names a file; the API refuses file references
    return copy.deepcopy(payload)


@pytest.fixture
def cover_letter_payload() -> dict[str, Any]:
    payload: dict[str, Any] = yaml.safe_load(
        (DATA_DIR / "cover_letter.template.yaml").read_text(encoding="utf-8")
    )
    return copy.deepcopy(payload)


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)
