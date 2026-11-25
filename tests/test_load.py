import sys
import types

import pytest

import latincy


@pytest.fixture
def fake_spacy(monkeypatch):
    loaded = []
    monkeypatch.setitem(sys.modules, "spacy", types.SimpleNamespace(load=lambda name, **kw: loaded.append(name) or name))
    return loaded


def _have(monkeypatch, sizes):
    monkeypatch.setattr(latincy, "installed", lambda: {s: "x" for s in sizes})


def test_default_loads_sm_and_warns(monkeypatch, fake_spacy):
    _have(monkeypatch, ["sm"])
    with pytest.warns(latincy.SmallModelWarning, match=r'latincy\[lg\]'):
        assert latincy.load() == "la_core_web_sm"


def test_default_warning_names_installed_larger(monkeypatch, fake_spacy):
    _have(monkeypatch, ["sm", "lg"])
    with pytest.warns(latincy.SmallModelWarning, match=r"latincy.load\('lg'\)"):
        latincy.load()


def test_explicit_sm_is_silent(monkeypatch, fake_spacy, recwarn):
    _have(monkeypatch, ["sm"])
    latincy.load("sm")
    assert not [w for w in recwarn if issubclass(w.category, latincy.SmallModelWarning)]


def test_missing_size_says_how_to_install(monkeypatch, fake_spacy):
    _have(monkeypatch, ["sm"])
    with pytest.raises(OSError, match=r'pip install "latincy\[trf\]"'):
        latincy.load("trf")


def test_unknown_size(monkeypatch, fake_spacy):
    with pytest.raises(ValueError):
        latincy.load("xl")
