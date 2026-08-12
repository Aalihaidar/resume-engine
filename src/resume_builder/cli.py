"""CLI: resume-build render [--data data/resume.yaml] [--out output/resume.pdf]"""

from __future__ import annotations

from pathlib import Path

import typer

from resume_builder.render import build

app = typer.Typer(help="Build an ATS-safe PDF resume from resume.yaml", no_args_is_help=True)


@app.command()
def render(
    data: Path = typer.Option(Path("data/resume.yaml"), "--data", "-d", help="Path to resume.yaml"),
    out: Path = typer.Option(Path("output/resume.pdf"), "--out", "-o", help="Path to output PDF"),
    html: Path | None = typer.Option(
        None, "--html", help="Optional path to also save the intermediate HTML"
    ),
) -> None:
    """Render resume.yaml into a PDF (and optionally HTML) file."""
    build(data_path=data, output_pdf=out, output_html=html)
    typer.echo(f"✅ Resume built: {out}")


@app.command()
def version() -> None:
    """Print the resume_builder package version."""
    from resume_builder import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
