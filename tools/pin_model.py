"""Pin one size in src/latincy/models.json to a wheel already published on HF.

    uv run python tools/pin_model.py lg la_core_web_lg-3.10.0-py3-none-any.whl

Reads the repo's current commit and the file's LFS sha256 and size from the
HF API. Then update the matching pin in pyproject.toml (tests check they agree).
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "src" / "latincy" / "models.json"


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "latincy-fetch"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main(argv=None) -> int:
    size, filename = (argv or sys.argv[1:])[:2]
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    entry = table["models"][size]
    m = re.fullmatch(rf"{entry['dist']}-([^-]+)-py3-none-any\.whl", filename)
    if not m:
        raise SystemExit(f"{filename} is not a {entry['dist']} wheel")
    api = f"https://huggingface.co/api/models/{entry['repo']}"
    revision = _get(api)["sha"]
    files = {f["path"]: f for f in _get(f"{api}/tree/{revision}")}
    if filename not in files:
        raise SystemExit(f"{filename} not in {entry['repo']} at {revision}")
    f = files[filename]
    entry.update(version=m.group(1), revision=revision, filename=filename,
                 sha256=f["lfs"]["oid"], bytes=f["size"])
    TABLE.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
    print(f"{size}: {filename} @ {revision[:12]} sha256 {entry['sha256'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
