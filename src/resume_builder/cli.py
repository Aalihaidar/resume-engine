"""CLI: resume-build render [--data data/resume.yaml] [--out output/resume.pdf]
resume-build cover-letter [--data data/cover_letter.yaml] [--out output/cover_letter.pdf]

Problems with the input (missing file, malformed YAML, schema violations) are
reported as one line per problem and exit code 1 — no traceback. Typer's rich
tracebacks are also configured not to dump local variables, since in this tool
those hold the contents of the CV.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from resume_builder import __version__
from resume_builder.render import build, build_cover_letter

app = typer.Typer(
    help="Build an ATS-safe PDF resume and cover letter from YAML data",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def _fail(message: str) -> typer.Exit:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


@contextmanager
def _friendly_errors(data: Path) -> Iterator[None]:
    try:
        yield
    except FileNotFoundError as exc:
        raise _fail(f"file not found: {exc.filename or data}") from exc
    except yaml.YAMLError as exc:
        raise _fail(f"{data} is not valid YAML:\n{exc}") from exc
    except ValidationError as exc:
        lines = [f"{data} failed validation:"]
        for err in exc.errors(include_url=False, include_context=False):
            location = ".".join(str(part) for part in err["loc"]) or "(root)"
            lines.append(f"  {location}: {err['msg']}")
        raise _fail("\n".join(lines)) from exc


def _show_version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_show_version,
        is_eager=True,
        help="Print the resume_builder package version and exit",
    ),
) -> None:
    """Build an ATS-safe PDF resume and cover letter from YAML data."""


def _run(builder: Callable[..., None], data: Path, out: Path, html: Path | None) -> None:
    with _friendly_errors(data):
        builder(data_path=data, output_pdf=out, output_html=html)


@app.command()
def render(
    data: Path = typer.Option(Path("data/resume.yaml"), "--data", "-d", help="Path to resume.yaml"),
    out: Path = typer.Option(Path("output/resume.pdf"), "--out", "-o", help="Path to output PDF"),
    html: Path | None = typer.Option(
        None, "--html", help="Optional path to also save the intermediate HTML"
    ),
) -> None:
    """Render resume.yaml into a PDF (and optionally HTML) file."""
    _run(build, data, out, html)
    typer.echo(f"Resume built: {out}")


@app.command(name="cover-letter")
def cover_letter(
    data: Path = typer.Option(
        Path("data/cover_letter.yaml"), "--data", "-d", help="Path to cover_letter.yaml"
    ),
    out: Path = typer.Option(
        Path("output/cover_letter.pdf"), "--out", "-o", help="Path to output PDF"
    ),
    html: Path | None = typer.Option(
        None, "--html", help="Optional path to also save the intermediate HTML"
    ),
) -> None:
    """Render cover_letter.yaml into a PDF (and optionally HTML) file."""
    _run(build_cover_letter, data, out, html)
    typer.echo(f"Cover letter built: {out}")


@app.command()
def version() -> None:
    """Print the resume_builder package version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
