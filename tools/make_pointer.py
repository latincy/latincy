"""Build the PyPI pointer sdist for one LatinCy model size.

    uv run python tools/make_pointer.py sm [--wheel PATH] [--out dist]

The sdist carries the HF wheel's own METADATA (so pip and uv resolve the
model's real dependencies without building), the pin, and the fetch backend.
Without --wheel the pinned wheel is downloaded once to read its METADATA.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import string
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "src" / "latincy" / "models.json"
BACKEND = ROOT / "tools" / "pointer" / "latincy_fetch.py"

PYPROJECT = """\
[build-system]
requires = []
build-backend = "latincy_fetch"
backend-path = ["."]
"""


def hf_url(entry: dict) -> str:
    return f"https://huggingface.co/{entry['repo']}/resolve/{entry['revision']}/{entry['filename']}"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wheel_metadata(wheel: Path, entry: dict) -> str:
    member = f"{entry['dist']}-{entry['version']}.dist-info/METADATA"
    with zipfile.ZipFile(wheel) as z:
        text = z.read(member).decode("utf-8")
    fields = dict(
        line.split(": ", 1) for line in text.split("\n\n", 1)[0].splitlines() if ": " in line
    )
    if fields.get("Name") != entry["dist"] or fields.get("Version") != entry["version"]:
        raise SystemExit(f"{wheel.name}: METADATA says {fields.get('Name')} {fields.get('Version')}")
    return text


README = ROOT / "tools" / "pointer" / "README.md"


SOURCE_URL = "https://github.com/latincy/latincy"


def set_version(metadata: str, version: str) -> str:
    head, sep, body = metadata.partition("\n\n")
    lines = [f"Version: {version}" if ln.startswith("Version:") else ln for ln in head.splitlines()]
    return "\n".join(lines) + sep + body


def set_urls(metadata: str, entry: dict) -> str:
    """Public links come from the table, never from the wheel: the 3.9.x wheels
    carry a github.com/diyclassics Home-page (release gate rule 6)."""
    head, sep, body = metadata.partition("\n\n")
    lines = [ln for ln in head.splitlines() if not ln.startswith(("Home-page:", "Project-URL:"))]
    lines += [
        f"Home-page: https://huggingface.co/{entry['repo']}",
        f"Project-URL: Model, https://huggingface.co/{entry['repo']}",
        f"Project-URL: Source, {SOURCE_URL}",
    ]
    return "\n".join(lines) + sep + body


def readme_text(entry: dict, template: Path = README) -> str:
    """The PyPI page for a pointer: its own README, never the HF model card
    (release gate rule 8). $dist/$version/$repo/$install_name are filled in so
    version strings always equal the version shipping."""
    if not template.is_file():
        raise SystemExit(f"{template}: a PyPI README is required (release gate rule 8)")
    size = entry["dist"].rsplit("_", 1)[-1]
    text = string.Template(template.read_text(encoding="utf-8")).substitute(
        dist=entry["dist"],
        size=size,
        version=entry.get("pypi_version", entry["version"]),
        wheel_version=entry["version"],
        filename=entry["filename"],
        repo=entry["repo"],
        install_name=entry["dist"].replace("_", "-"),
        latincy_install="pip install latincy" if size == "sm" else f'pip install "latincy[{size}]"',
    )
    return text


def pkg_info(metadata: str, readme: str) -> str:
    """PKG-INFO for the sdist: the wheel's METADATA header with the pointer's own README.

    The wheel is fixed, so nothing is dynamic. Empty fields are dropped (PyPI
    rejects an empty Author-email). The body is the pointer README, marked Markdown.
    """
    head = metadata.partition("\n\n")[0]
    lines = [
        line
        for line in head.splitlines()
        if not line.startswith(("Dynamic:", "Description-Content-Type:"))
        and line.split(":", 1)[-1].strip()
    ]
    lines.append("Description-Content-Type: text/markdown")
    return "\n".join(lines) + "\n\n" + readme


def make_pointer(entry: dict, wheel: Path, out_dir: Path, readme: Path = README) -> Path:
    digest = _sha256(wheel)
    if digest != entry["sha256"]:
        raise SystemExit(f"{wheel}: sha256 {digest} != pinned {entry['sha256']}")
    pypi_version = entry.get("pypi_version", entry["version"])
    header = set_urls(set_version(wheel_metadata(wheel, entry), pypi_version), entry)
    # One metadata for both: what PyPI shows (PKG-INFO) is what gets installed
    # (METADATA), never the HF model card (release gate rules 6, 8).
    metadata = pkg_info(header, readme_text(entry, readme))
    pin = {
        "dist": entry["dist"],
        "version": pypi_version,
        "wheel_version": entry["version"],
        "filename": entry["filename"],
        "sha256": entry["sha256"],
        "url": entry.get("url") or hf_url(entry),
        "model_url": f"https://huggingface.co/{entry['repo']}",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp)
        (src / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
        (src / "latincy_pin.json").write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
        (src / "METADATA").write_text(metadata, encoding="utf-8")
        (src / "PKG-INFO").write_text(metadata, encoding="utf-8")
        shutil.copyfile(BACKEND, src / "latincy_fetch.py")
        spec = importlib.util.spec_from_file_location(f"latincy_fetch_{entry['dist']}_{pypi_version}", src / "latincy_fetch.py")
        backend = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(backend)
        name = backend.build_sdist(str(out_dir))
    return out_dir / name


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("size")
    ap.add_argument("--wheel", type=Path, help="local copy of the pinned HF wheel")
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    args = ap.parse_args(argv)
    entry = json.loads(TABLE.read_text(encoding="utf-8"))["models"][args.size]
    if args.wheel:
        print(make_pointer(entry, args.wheel, args.out))
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        wheel = Path(tmp) / entry["filename"]
        req = urllib.request.Request(hf_url(entry), headers={"User-Agent": "latincy-fetch"})
        with urllib.request.urlopen(req, timeout=60) as r, wheel.open("wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        print(make_pointer(entry, wheel, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
