from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from helpers import data_uri
from resume_builder import api
from resume_builder.middleware import MAX_BODY_BYTES, SECURITY_HEADERS


def _assert_pdf(response: Any, filename: str) -> None:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == f'attachment; filename="{filename}"'
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(b"%PDF-")


def _locations(response: Any) -> list[list[str]]:
    return [item["loc"] for item in response.json()["detail"]]


# --- happy paths ----------------------------------------------------------


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert client.head("/healthz").status_code == 200


def test_resume_pdf(client: TestClient, resume_payload: dict[str, Any]) -> None:
    _assert_pdf(client.post("/api/resume/pdf", json=resume_payload), "resume.pdf")


def test_resume_pdf_with_inline_photo(
    client: TestClient, resume_payload: dict[str, Any], png_data_uri: str
) -> None:
    resume_payload["photo"] = png_data_uri
    _assert_pdf(client.post("/api/resume/pdf", json=resume_payload), "resume.pdf")


def test_cover_letter_pdf(client: TestClient, cover_letter_payload: dict[str, Any]) -> None:
    _assert_pdf(client.post("/api/cover-letter/pdf", json=cover_letter_payload), "cover_letter.pdf")


def test_index_serves_the_ui_with_a_strict_csp(client: TestClient) -> None:
    for response in (client.get("/"), client.head("/")):
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        policy = response.headers["content-security-policy"]
        assert "default-src 'self'" in policy
        assert "frame-ancestors 'none'" in policy
        assert "unsafe-inline" not in policy
        assert "unsafe-eval" not in policy
        assert "http" not in policy  # nothing from third parties


@pytest.mark.parametrize(
    "path",
    [
        "/assets/app.css",
        "/assets/app.js",
        "/assets/js-yaml.min.js",
        "/assets/fonts/geist-latin-wght-normal.woff2",
    ],
)
def test_ui_assets_are_served(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.content


@pytest.mark.parametrize("path", ["/", "/assets/app.css", "/assets/app.js"])
def test_ui_is_revalidated_so_a_deploy_is_never_masked_by_a_stale_copy(
    client: TestClient, path: str
) -> None:
    first = client.get(path)
    assert first.headers["cache-control"] == "no-cache"
    if path != "/":
        again = client.get(path, headers={"If-None-Match": first.headers["etag"]})
        assert again.status_code == 304
        assert again.headers["cache-control"] == "no-cache"


def test_framing_is_refused_unless_development_embedding_is_enabled() -> None:
    assert "frame-ancestors 'none'" in api.content_security_policy()
    assert "frame-ancestors *" in api.content_security_policy(allow_embedding=True)
    assert api.ALLOW_EMBEDDING is False  # never on in the test / production environment


def test_security_headers_are_on_every_response(client: TestClient) -> None:
    for response in (client.get("/healthz"), client.get("/"), client.get("/nope")):
        for name, value in SECURITY_HEADERS.items():
            assert response.headers[name] == value


def test_openapi_describes_the_request_bodies(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    assert "Resume" in schemas
    assert "CoverLetter" in schemas
    assert schemas["Resume"]["additionalProperties"] is False
    assert spec["info"]["version"]


# --- validation errors are 422, never 500 --------------------------------


def test_missing_field_is_422(client: TestClient, resume_payload: dict[str, Any]) -> None:
    del resume_payload["summary"]
    response = client.post("/api/resume/pdf", json=resume_payload)
    assert response.status_code == 422
    assert ["body", "summary"] in _locations(response)


def test_unknown_field_is_422(client: TestClient, resume_payload: dict[str, Any]) -> None:
    resume_payload["experiance"] = []
    response = client.post("/api/resume/pdf", json=resume_payload)
    assert response.status_code == 422
    assert ["body", "experiance"] in _locations(response)


@pytest.mark.parametrize(
    "photo",
    [
        "data:image/png;base64,@@@@",  # custom validator error: used to crash with a 500
        data_uri("png", b"<script>alert(1)</script>"),
        "data:image/gif;base64,AAAA",
        "../../etc/passwd",
    ],
)
def test_invalid_photo_is_422_not_500(
    client: TestClient, resume_payload: dict[str, Any], photo: str
) -> None:
    resume_payload["photo"] = photo
    response = client.post("/api/resume/pdf", json=resume_payload)
    assert response.status_code == 422
    assert ["body", "photo"] in _locations(response)


def test_cover_letter_placeholder_is_422_not_500(
    client: TestClient, cover_letter_payload: dict[str, Any]
) -> None:
    cover_letter_payload["role_title"] = "[JOB TITLE]"
    response = client.post("/api/cover-letter/pdf", json=cover_letter_payload)
    assert response.status_code == 422
    assert "role_title" in response.text


def test_filename_photo_is_refused_over_http(
    client: TestClient, resume_payload: dict[str, Any]
) -> None:
    # headshot.jpg ships inside the package; a public endpoint must not embed it for strangers.
    resume_payload["photo"] = "headshot.jpg"
    response = client.post("/api/resume/pdf", json=resume_payload)
    assert response.status_code == 422
    assert ["body", "photo"] in _locations(response)


def test_validation_errors_do_not_echo_the_request(
    client: TestClient, resume_payload: dict[str, Any]
) -> None:
    # The framework default repeats the offending input once per error, which
    # lets a large body be multiplied into a much larger response.
    marker = "SENTINEL-" + "x" * 1000
    resume_payload["notes"] = marker
    del resume_payload["summary"]
    response = client.post("/api/resume/pdf", json=resume_payload)

    assert response.status_code == 422
    assert marker not in response.text
    assert len(response.content) < 2_000
    for error in response.json()["detail"]:
        assert set(error) <= {"type", "loc", "msg"}


def test_non_object_body_is_422(client: TestClient) -> None:
    assert client.post("/api/resume/pdf", json=[1, 2]).status_code == 422
    assert client.post("/api/resume/pdf", content=b"{not json").status_code == 422


# --- request size cap -----------------------------------------------------


def test_oversized_content_length_is_413(client: TestClient) -> None:
    response = client.post(
        "/api/resume/pdf",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}
    assert response.headers["x-content-type-options"] == "nosniff"


def test_oversized_chunked_body_is_413_too(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(MAX_BODY_BYTES // (1024 * 1024) + 1):
            yield b"x" * (1024 * 1024)

    # No Content-Length: only the streaming check can catch this one.
    response = client.post(
        "/api/resume/pdf", content=chunks(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}


# --- render concurrency ---------------------------------------------------


def test_busy_renderer_answers_503_with_retry_after(
    client: TestClient, resume_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    slots = threading.BoundedSemaphore(1)
    slots.acquire()  # the only slot is taken by a "running" render
    monkeypatch.setattr(api, "_render_slots", slots)
    monkeypatch.setattr(api, "_RENDER_QUEUE_TIMEOUT_SECONDS", 0.05)

    response = client.post("/api/resume/pdf", json=resume_payload)
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


def test_slot_is_released_after_a_render(
    client: TestClient, resume_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(api, "_render_slots", slots)

    for _ in range(2):
        assert client.post("/api/resume/pdf", json=resume_payload).status_code == 200
    assert slots.acquire(blocking=False)  # would be False if a slot had leaked


def test_slot_is_released_when_rendering_fails(
    client: TestClient, resume_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(api, "_render_slots", slots)

    def boom(_: str) -> bytes:
        raise RuntimeError("renderer crashed")

    monkeypatch.setattr(api, "render_pdf_bytes", boom)
    with pytest.raises(RuntimeError):
        client.post("/api/resume/pdf", json=resume_payload)
    assert slots.acquire(blocking=False)


@pytest.mark.parametrize(
    ("value", "expected"), [(None, 2), ("5", 5), ("0", 1), ("-3", 1), ("lots", 2), ("", 2)]
)
def test_concurrency_setting_is_parsed_defensively(
    monkeypatch: pytest.MonkeyPatch, value: str | None, expected: int
) -> None:
    if value is None:
        monkeypatch.delenv("RESUME_MAX_CONCURRENT_RENDERS", raising=False)
    else:
        monkeypatch.setenv("RESUME_MAX_CONCURRENT_RENDERS", value)
    assert api._max_concurrent_renders() == expected
