import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = json.loads((ROOT / "src" / "latincy" / "models.json").read_text())["models"]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]


def _pin(reqs):
    (req,) = reqs
    name, version = req.split("==")
    return name, version


def test_sizes():
    assert list(TABLE) == ["sm", "md", "lg", "trf"]


def test_entries_complete():
    for size, e in TABLE.items():
        assert e["dist"] == f"la_core_web_{size}"
        assert re.fullmatch(r"[0-9a-f]{64}", e["sha256"])
        assert re.fullmatch(r"[0-9a-f]{40}", e["revision"])
        assert e["filename"] == f"{e['dist']}-{e['version']}-py3-none-any.whl"
        assert e["repo"] == f"latincy/{e['dist']}"


def test_pyproject_pins_match_table():
    pins = {"sm": _pin(PROJECT["dependencies"])}
    pins.update({k: _pin(v) for k, v in PROJECT["optional-dependencies"].items()})
    assert set(pins) == set(TABLE)
    for size, (name, version) in pins.items():
        assert name.replace("-", "_") == TABLE[size]["dist"]
        assert version == TABLE[size].get("pypi_version", TABLE[size]["version"])
