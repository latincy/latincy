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

# Mirrors the real 3.9.x HF wheels' defects: a diyclassics Home-page, an HF
# model card (front matter + diyclassics Author link) as the description, and
# meta.json (two copies) whose single "url" is the dead diyclassics repo.
METADATA = (
    "Metadata-Version: 2.4\nName: la_core_web_xx\nVersion: 1.2.3\n"
    "Home-page: https://github.com/diyclassics/latincy\nAuthor-email: \n"
    "Requires-Dist: spacy<4\nDynamic: requires-dist\n\n"
    "---\ntags:\n- spacy\n---\nmodel card | [Author](https://github.com/diyclassics/latincy) |\n"
)
META_JSON = (
    '{\n  "lang":"la",\n  "name":"core_web_xx",\n  "version":"1.2.3",\n'
    '  "url":"https://github.com/diyclassics/latincy",\n  "vectors":{"width":0}\n}'
)
META_PATHS = ("la_core_web_xx/meta.json", "la_core_web_xx/la_core_web_xx-1.2.3/meta.json")
WEIGHTS = "la_core_web_xx/la_core_web_xx-1.2.3/tagger/model"
CARD = "la_core_web_xx/la_core_web_xx-1.2.3/README.md"
CARD_TEXT = "| **Author** | [A. Author](https://github.com/diyclassics/latincy) |\nsee latincy_ext\n"
CODE = "la_core_web_xx/functions.py"
CODE_TEXT = "# Ported from latincy_ext (github.com/diyclassics/latincy_ext).\n"


@pytest.fixture
def wheel(tmp_path):
    path = tmp_path / "house" / "la_core_web_xx-1.2.3-py3-none-any.whl"
    path.parent.mkdir()
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("la_core_web_xx/__init__.py", "")
        for p in META_PATHS:
            z.writestr(p, META_JSON)
        z.writestr(WEIGHTS, bytes(range(256)) * 64)
        z.writestr(CARD, CARD_TEXT)
        z.writestr(CODE, CODE_TEXT)
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
    assert (src / "METADATA").read_text() == pkg_info  # what PyPI shows is what installs
    assert "diyclassics" not in pkg_info
    assert "Home-page: https://huggingface.co/latincy/la_core_web_xx" in pkg_info
    assert "Project-URL: Source, https://github.com/latincy/latincy" in pkg_info
    assert "Dynamic:" not in pkg_info and "Author-email" not in pkg_info
    assert "Requires-Dist: spacy<4" in pkg_info
    assert "Description-Content-Type: text/markdown" in pkg_info
    body = pkg_info.split("\n\n", 1)[1]
    assert "model card" not in body and "tags:" not in body  # not the HF card
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
        for keep in ("la_core_web_xx/__init__.py", WEIGHTS, CODE):  # code stays byte-identical
            assert new.read(keep) == old.read(keep)
        assert new.read(CARD).decode() == CARD_TEXT.replace(
            "https://github.com/diyclassics/latincy", "https://huggingface.co/latincy/la_core_web_xx"
        )
        for p in META_PATHS:  # only the url value changes, byte for byte
            want = META_JSON.replace(
                '"https://github.com/diyclassics/latincy"', '"https://huggingface.co/latincy/la_core_web_xx"'
            )
            assert new.read(p).decode() == want
        installed_meta = new.read("la_core_web_xx-0.3.0.dist-info/METADATA").decode()
        assert installed_meta == (src / "METADATA").read_text()  # == prepared metadata
        assert "Version: 0.3.0" in installed_meta
        assert [n for n in names if b"diyclassics" in new.read(n)] == [CODE]  # code comment, by decision
        rows = list(csv.reader(io.StringIO(new.read("la_core_web_xx-0.3.0.dist-info/RECORD").decode())))
        assert {r[0] for r in rows} == names
        for path, digest, size in rows:
            if digest:
                data = new.read(path)
                assert digest == "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
                assert int(size) == len(data)


def test_meta_url_refuses_ambiguous(tmp_path, wheel, entry):
    src, backend = _unpack(make_pointer.make_pointer(entry, wheel, tmp_path / "dist"), tmp_path / "u")
    with pytest.raises(RuntimeError, match="exactly one"):
        backend._set_meta_url(b'{"url":"a","sources":[{"url":"b"}]}', "https://huggingface.co/x")
    assert backend._set_meta_url(b'{"url" : "a"}', "https://h/x") == b'{"url" : "https://h/x"}'
    with pytest.raises(RuntimeError, match="exactly one"):
        backend._set_card_link(b"https://github.com/diyclassics/latincy_ext only", "https://h/x")


def test_make_pointer_refuses_wrong_sha(tmp_path, wheel, entry):
    entry["sha256"] = "0" * 64
    with pytest.raises(SystemExit):
        make_pointer.make_pointer(entry, wheel, tmp_path / "dist")
