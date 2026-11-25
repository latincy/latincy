"""The pointer sdist round trip, on a fake model wheel (no network)."""

import hashlib
import importlib.util
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import make_pointer  # noqa: E402

METADATA = (
    "Metadata-Version: 2.4\nName: la_core_web_xx\nVersion: 1.2.3\n"
    "Home-page: https://github.com/diyclassics/latincy\n"
    "Requires-Dist: spacy<4\nDynamic: requires-dist\n\nmodel card\n"
)


@pytest.fixture
def wheel(tmp_path):
    path = tmp_path / "house" / "la_core_web_xx-1.2.3-py3-none-any.whl"
    path.parent.mkdir()
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("la_core_web_xx/__init__.py", "")
        z.writestr("la_core_web_xx-1.2.3.dist-info/METADATA", METADATA)
    return path


@pytest.fixture
def entry(wheel):
    return {
        "dist": "la_core_web_xx",
        "repo": "latincy/la_core_web_xx",
        "version": "1.2.3",
        "filename": wheel.name,
        "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "url": "https://invalid.example/never-fetched.whl",
    }


def _unpack(sdist, dest):
    with tarfile.open(sdist) as tar:
        tar.extractall(dest, filter="data")
    (src,) = dest.iterdir()
    spec = importlib.util.spec_from_file_location(f"fetch_{id(dest)}", src / "latincy_fetch.py")
    backend = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backend)
    return src, backend


def test_sdist_layout(tmp_path, wheel, entry):
    sdist = make_pointer.make_pointer(entry, wheel, tmp_path / "dist")
    assert sdist.name == "la_core_web_xx-1.2.3.tar.gz"
    src, _ = _unpack(sdist, tmp_path / "unpacked")
    pkg_info = (src / "PKG-INFO").read_text()
    for text in ((src / "METADATA").read_text(), pkg_info):
        assert "diyclassics" not in text
        assert "Home-page: https://huggingface.co/latincy/la_core_web_xx" in text
        assert "Project-URL: Source, https://github.com/latincy/latincy" in text
    assert "Dynamic:" not in pkg_info and "Requires-Dist: spacy<4" in pkg_info
    assert "Description-Content-Type: text/markdown" in pkg_info
    body = pkg_info.split("\n\n", 1)[1]
    assert "model card" not in body.splitlines()[0]  # not the HF card
    assert "la_core_web_xx 1.2.3" in body and "pip install la-core-web-xx" in body


def test_pkg_info_drops_empty_fields():
    text = make_pointer.pkg_info("Name: x\nAuthor-email: \nVersion: 1\n\nbody\n", "readme\n")
    assert "Author-email" not in text and text.endswith("\n\nreadme\n")


def test_readme_required(tmp_path, wheel, entry):
    with pytest.raises(SystemExit, match="rule 8"):
        make_pointer.make_pointer(entry, wheel, tmp_path / "dist", readme=tmp_path / "missing.md")


def test_build_wheel_from_wheelhouse(tmp_path, wheel, entry, monkeypatch):
    src, backend = _unpack(make_pointer.make_pointer(entry, wheel, tmp_path / "dist"), tmp_path / "u")
    monkeypatch.setenv("LATINCY_WHEELHOUSE", str(wheel.parent))
    out = tmp_path / "out"
    out.mkdir()
    name = backend.build_wheel(str(out))
    assert name == wheel.name  # same version: same filename
    with zipfile.ZipFile(out / name) as z:
        meta = z.read("la_core_web_xx-1.2.3.dist-info/METADATA").decode()
    assert "diyclassics" not in meta and "huggingface.co/latincy/la_core_web_xx" in meta
    md = tmp_path / "meta"
    md.mkdir()
    assert backend.prepare_metadata_for_build_wheel(str(md)) == "la_core_web_xx-1.2.3.dist-info"


def test_build_wheel_refuses_wrong_sha(tmp_path, wheel, entry, monkeypatch):
    src, backend = _unpack(make_pointer.make_pointer(entry, wheel, tmp_path / "dist"), tmp_path / "u")
    with zipfile.ZipFile(wheel, "a") as z:
        z.writestr("la_core_web_xx/tampered.py", "")
    monkeypatch.setenv("LATINCY_WHEELHOUSE", str(wheel.parent))
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(RuntimeError, match="does not match"):
        backend.build_wheel(str(out))
    assert not any(out.iterdir())


def test_pypi_version_rewrites_only_dist_metadata(tmp_path, wheel, entry, monkeypatch):
    import base64
    import csv
    import io

    entry["pypi_version"] = "0.3.0"
    sdist = make_pointer.make_pointer(entry, wheel, tmp_path / "dist")
    assert sdist.name == "la_core_web_xx-0.3.0.tar.gz"
    src, backend = _unpack(sdist, tmp_path / "u")
    assert "Version: 0.3.0" in (src / "PKG-INFO").read_text()
    meta = tmp_path / "meta"
    meta.mkdir()
    assert backend.prepare_metadata_for_build_wheel(str(meta)) == "la_core_web_xx-0.3.0.dist-info"
    monkeypatch.setenv("LATINCY_WHEELHOUSE", str(wheel.parent))
    out = tmp_path / "out"
    out.mkdir()
    name = backend.build_wheel(str(out))
    assert name == "la_core_web_xx-0.3.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as old, zipfile.ZipFile(out / name) as new:
        names = set(new.namelist())
        assert "la_core_web_xx-0.3.0.dist-info/RECORD" in names
        assert not any("1.2.3.dist-info" in n for n in names)
        assert new.read("la_core_web_xx/__init__.py") == old.read("la_core_web_xx/__init__.py")
        installed_meta = new.read("la_core_web_xx-0.3.0.dist-info/METADATA").decode()
        assert installed_meta == (src / "METADATA").read_text()  # == prepared metadata
        assert "Version: 0.3.0" in installed_meta and "diyclassics" not in installed_meta
        rows = list(csv.reader(io.StringIO(new.read("la_core_web_xx-0.3.0.dist-info/RECORD").decode())))
        assert {r[0] for r in rows} == names
        for path, digest, size in rows:
            if digest:
                data = new.read(path)
                assert digest == "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
                assert int(size) == len(data)


def test_make_pointer_refuses_wrong_sha(tmp_path, wheel, entry):
    entry["sha256"] = "0" * 64
    with pytest.raises(SystemExit):
        make_pointer.make_pointer(entry, wheel, tmp_path / "dist")
