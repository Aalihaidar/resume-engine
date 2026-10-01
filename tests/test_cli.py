from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from resume_builder import __version__
from resume_builder.cli import app

REPO_ROOT = Path(__file__).parent.parent
runner = CliRunner()


def test_version_command_and_flag() -> None:
    for args in (["version"], ["--version"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0
        assert result.output.strip() == __version__


def test_render_writes_pdf_and_html(tmp_path: Path) -> None:
    out = tmp_path / "out" / "resume.pdf"
    html = tmp_path / "out" / "resume.html"
    result = runner.invoke(
        app,
        [
            "render",
            "--data",
            str(REPO_ROOT / "data" / "resume.yaml"),
            "--out",
            str(out),
            "--html",
            str(html),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.read_bytes().startswith(b"%PDF-")
    assert html.exists()
    assert str(out) in result.output


def test_cover_letter_writes_pdf(tmp_path: Path) -> None:
    out = tmp_path / "letter.pdf"
    data = REPO_ROOT / "data" / "cover_letter.yaml"
    result = runner.invoke(app, ["cover-letter", "-d", str(data), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_bytes().startswith(b"%PDF-")


def test_missing_input_file_is_a_clean_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["render", "--data", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 1
    assert "file not found" in result.output
    assert "Traceback" not in result.output


def test_malformed_yaml_is_a_clean_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: [unclosed\n", encoding="utf-8")
    result = runner.invoke(app, ["render", "--data", str(bad), "--out", str(tmp_path / "x.pdf")])
    assert result.exit_code == 1
    assert "not valid YAML" in result.output
    assert "Traceback" not in result.output


def test_validation_errors_list_each_field(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("\n".join(["name: Test", "experiance: []"]), encoding="utf-8")
    result = runner.invoke(app, ["render", "--data", str(bad), "--out", str(tmp_path / "x.pdf")])

    assert result.exit_code == 1
    assert "failed validation" in result.output
    assert "headline: Field required" in result.output
    assert "experiance: Extra inputs are not permitted" in result.output
    assert "Traceback" not in result.output
    assert not (tmp_path / "x.pdf").exists()


@pytest.mark.parametrize("content", ["", "- just\n- a list\n"])
def test_non_mapping_yaml_is_a_clean_error(tmp_path: Path, content: str) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(content, encoding="utf-8")
    result = runner.invoke(app, ["render", "--data", str(bad), "--out", str(tmp_path / "x.pdf")])
    assert result.exit_code == 1
    assert "failed validation" in result.output


def test_unfilled_cover_letter_placeholder_is_reported(tmp_path: Path) -> None:
    template = (REPO_ROOT / "data" / "cover_letter.template.yaml").read_text(encoding="utf-8")
    bad = tmp_path / "letter.yaml"
    bad.write_text(template.replace("Dear Hiring Manager,", "Dear [NAME],"), encoding="utf-8")
    result = runner.invoke(app, ["cover-letter", "-d", str(bad), "-o", str(tmp_path / "x.pdf")])
    assert result.exit_code == 1
    assert "salutation" in result.output
