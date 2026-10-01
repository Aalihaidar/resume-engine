"""resume_builder: data-driven, ATS-safe CV rendering (YAML -> HTML -> PDF)."""

from importlib.metadata import PackageNotFoundError, version

try:
    # pyproject.toml is the single source of truth for the version.
    __version__ = version("resume-engine")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"
