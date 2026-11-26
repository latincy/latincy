"""PEP 517 build backend for a LatinCy model pointer package.

The sdist on PyPI holds no model. Building its wheel downloads the pinned
wheel from Hugging Face, checks its sha256, and repackages it under the
LatinCy release version (e.g. 0.3.0 for model 3.9.8). What changes:

- the .dist-info name, METADATA (this sdist's: version, public URLs, the
  pointer README as description) and RECORD;
- the top-level "url" value in the model's two meta.json copies, and the one
  dead https://github.com/diyclassics/latincy link in the bundled model card
  (README.md in the model directory), each set to the model's Hugging Face
  repo. Only those bytes change.

Every other file, including weights, vectors, code (functions.py) and the
rest of meta.json and README.md, is copied byte for byte.

Standard library only: the build needs no requirements.

LATINCY_WHEELHOUSE: a folder to take the wheel from instead of downloading
(offline or cluster installs). The sha256 is checked either way.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN = json.loads((HERE / "latincy_pin.json").read_text(encoding="utf-8"))
SDIST_FILES = ("PKG-INFO", "pyproject.toml", "latincy_fetch.py", "latincy_pin.json", "METADATA")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(dest: Path) -> None:
    house = os.environ.get("LATINCY_WHEELHOUSE")
    if house:
        local = Path(house) / PIN["filename"]
        if local.is_file():
            shutil.copyfile(local, dest)
            return
    req = urllib.request.Request(PIN["url"], headers={"User-Agent": "latincy-fetch"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, dest.open("wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
    except OSError as e:
        raise RuntimeError(
            f"Could not download {PIN['url']} ({e}). Download {PIN['filename']} "
            "by hand and set LATINCY_WHEELHOUSE to the folder that holds it."
        ) from e


def get_requires_for_build_wheel(config_settings=None):
    return []


def get_requires_for_build_sdist(config_settings=None):
    return []


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    dist_info = Path(metadata_directory) / f"{PIN['dist']}-{PIN['version']}.dist-info"
    dist_info.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / "METADATA", dist_info / "METADATA")
    return dist_info.name


_URL_FIELD = re.compile(rb'("url"\s*:\s*)"[^"]*"')


def _set_meta_url(raw: bytes, url: str) -> bytes:
    """Replace the value of meta.json's single "url" key, leaving every other byte."""
    if len(_URL_FIELD.findall(raw)) != 1:
        raise RuntimeError('meta.json: expected exactly one "url" key; refusing to guess.')
    out = _URL_FIELD.sub(lambda m: m.group(1) + json.dumps(url).encode(), raw)
    if json.loads(out).get("url") != url:
        raise RuntimeError("meta.json: url rewrite did not take; refusing to install.")
    return out


_DEAD_LINK = re.compile(rb"https://github\.com/diyclassics/latincy(?![\w/-])")


def _set_card_link(raw: bytes, url: str) -> bytes:
    """Replace the bundled model card's one dead diyclassics link, leaving every other byte."""
    if len(_DEAD_LINK.findall(raw)) != 1:
        raise RuntimeError("README.md: expected exactly one dead diyclassics link; refusing to guess.")
    return _DEAD_LINK.sub(url.encode(), raw)


def _revision(src: Path, wheel_directory: Path) -> str:
    """Copy the wheel under PIN['version']; see the module docstring for what changes."""
    dist, old, new = PIN["dist"], PIN["wheel_version"], PIN["version"]
    old_di, new_di = f"{dist}-{old}.dist-info/", f"{dist}-{new}.dist-info/"
    metas = {f"{dist}/meta.json", f"{dist}/{dist}-{old}/meta.json"}
    card = f"{dist}/{dist}-{old}/README.md"
    name = f"{dist}-{new}-py3-none-any.whl"
    record = io.StringIO()
    rows = csv.writer(record, lineterminator="\n")
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
        Path(wheel_directory) / name, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for info in zin.infolist():
            if info.is_dir():
                continue
            arc = new_di + info.filename[len(old_di):] if info.filename.startswith(old_di) else info.filename
            if arc == new_di + "RECORD":
                continue
            out = zipfile.ZipInfo(arc, date_time=info.date_time)
            out.external_attr, out.compress_type = info.external_attr, zipfile.ZIP_DEFLATED
            h, size = hashlib.sha256(), 0
            data = None
            if arc == new_di + "METADATA":
                data = (HERE / "METADATA").read_bytes()
            elif arc in metas:
                data = _set_meta_url(zin.read(info), PIN["model_url"])
                metas.discard(arc)
            elif arc == card:
                data = _set_card_link(zin.read(info), PIN["model_url"])
            if data is not None:
                zout.writestr(out, data)
                h.update(data)
                size = len(data)
            else:
                with zin.open(info) as fin, zout.open(out, "w", force_zip64=True) as fout:
                    for chunk in iter(lambda: fin.read(1 << 20), b""):
                        fout.write(chunk)
                        h.update(chunk)
                        size += len(chunk)
            rows.writerow([arc, "sha256=" + base64.urlsafe_b64encode(h.digest()).rstrip(b"=").decode(), size])
        if metas:
            raise RuntimeError(f"wheel is missing {sorted(metas)}; refusing to install.")
        rows.writerow([new_di + "RECORD", "", ""])
        zout.writestr(new_di + "RECORD", record.getvalue())
    return name


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    name = PIN["filename"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_wheel = Path(tmp) / name
        _fetch(tmp_wheel)
        digest = _sha256(tmp_wheel)
        if digest != PIN["sha256"]:
            raise RuntimeError(
                f"{name}: sha256 {digest} does not match the pinned {PIN['sha256']}; refusing to install."
            )
        return _revision(tmp_wheel, Path(wheel_directory))


def build_sdist(sdist_directory, config_settings=None):
    base = f"{PIN['dist']}-{PIN['version']}"
    out = Path(sdist_directory) / f"{base}.tar.gz"
    with tarfile.open(out, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        for fn in SDIST_FILES:
            info = tar.gettarinfo(HERE / fn, arcname=f"{base}/{fn}")
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            with (HERE / fn).open("rb") as f:
                tar.addfile(info, f)
    return out.name
