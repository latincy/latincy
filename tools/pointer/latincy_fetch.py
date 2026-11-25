"""PEP 517 build backend for a LatinCy model pointer package.

The sdist on PyPI holds no model. Building its wheel downloads the pinned
wheel from Hugging Face, checks its sha256, and hands it to the installer.
When the PyPI version or metadata differs from the HF wheel's (LatinCy release
numbers on PyPI, e.g. 0.3.0, vs model versions, e.g. 3.9.8; public URLs set
from the release table), only the distribution metadata is changed: the
.dist-info name, METADATA and RECORD. Every other file, including the model's
meta.json and data directory, is copied byte for byte.

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


def _revision(src: Path, wheel_directory: Path) -> str:
    """Copy the wheel under PIN['version'], changing only its distribution metadata:
    the .dist-info name, METADATA (this sdist's: version and public URLs) and RECORD."""
    dist, old, new = PIN["dist"], PIN["wheel_version"], PIN["version"]
    old_di, new_di = f"{dist}-{old}.dist-info/", f"{dist}-{new}.dist-info/"
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
            if arc == new_di + "METADATA":
                data = (HERE / "METADATA").read_bytes()  # version + public URLs, as resolved
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
        with zipfile.ZipFile(tmp_wheel) as z:
            shipped = z.read(f"{PIN['dist']}-{PIN['wheel_version']}.dist-info/METADATA")
        if PIN["version"] != PIN["wheel_version"] or shipped != (HERE / "METADATA").read_bytes():
            return _revision(tmp_wheel, Path(wheel_directory))
        shutil.move(str(tmp_wheel), Path(wheel_directory) / name)
    return name


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
