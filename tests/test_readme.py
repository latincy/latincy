"""README model grid must match src/latincy/models.json (release gate rule 8)."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = json.loads((ROOT / "src" / "latincy" / "models.json").read_text())["models"]
README = (ROOT / "README.md").read_text()


def test_model_grid_matches_table():
    rows = {}
    for line in README.splitlines():
        m = re.match(r"\| (sm|md|lg|trf) \| `([^`]+)` (\S+) \| \[([^\]]+)\]\(([^)]+)\) \| (\S+) \| (\d+) MB \|", line)
        if m:
            rows[m.group(1)] = m.groups()[1:]
    assert set(rows) == set(TABLE)
    for size, (pkg, pypi_v, repo, url, model_v, mb) in rows.items():
        e = TABLE[size]
        assert pkg == e["dist"].replace("_", "-")
        assert pypi_v == e.get("pypi_version", e["version"])
        assert repo == e["repo"] and url == f"https://huggingface.co/{e['repo']}"
        assert model_v == e["version"]
        assert int(mb) == round(e["bytes"] / 1e6)


def test_no_placeholders():
    assert "<<PJB" not in README
