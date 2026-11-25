"""Install and load the LatinCy spaCy pipelines.

    pip install latincy            # code + la_core_web_sm
    pip install "latincy[lg]"      # adds la_core_web_lg (also: md, trf)

    import latincy
    nlp = latincy.load("lg")
"""

from __future__ import annotations

import json
import warnings
from importlib import metadata, resources

__all__ = ["load", "installed", "MODELS", "SmallModelWarning"]
__version__ = metadata.version("latincy")

MODELS: dict[str, dict] = json.loads(
    resources.files(__name__).joinpath("models.json").read_text(encoding="utf-8")
)["models"]


class SmallModelWarning(UserWarning):
    """latincy.load() was called without a size and loaded the default sm pipeline."""


def install_command(size: str) -> str:
    return "pip install latincy" if size == "sm" else f'pip install "latincy[{size}]"'


def installed() -> dict[str, str]:
    """Installed LatinCy pipelines as {size: version}."""
    found = {}
    for size, entry in MODELS.items():
        try:
            found[size] = metadata.version(entry["dist"])
        except metadata.PackageNotFoundError:
            pass
    return found


def _default_message() -> str:
    larger = [s for s in installed() if s != "sm"]
    if larger:
        hint = f"Installed and more accurate: {', '.join(larger)}; use latincy.load({larger[-1]!r})."
    else:
        hint = f"For the more accurate pipelines: {install_command('lg')} or {install_command('trf')}."
    return (
        f"Loaded {MODELS['sm']['dist']}, the smallest LatinCy pipeline. {hint} "
        "Pass size='sm' to silence this warning."
    )


def load(size: str | None = None, **kwargs):
    """Load a LatinCy pipeline by size (sm, md, lg, trf); kwargs go to spacy.load."""
    import spacy

    if size is None:
        size = "sm"
        warnings.warn(_default_message(), SmallModelWarning, stacklevel=2)
    if size not in MODELS:
        raise ValueError(f"Unknown LatinCy size {size!r}; choose one of {', '.join(MODELS)}.")
    if size not in installed():
        raise OSError(f"{MODELS[size]['dist']} is not installed. Install it with: {install_command(size)}")
    return spacy.load(MODELS[size]["dist"], **kwargs)
