"""python -m latincy: list LatinCy pipelines, installed or not."""

from latincy import MODELS, __version__, install_command, installed

have = installed()
print(f"latincy {__version__}")
for size, entry in MODELS.items():
    mb = entry["bytes"] / 1e6
    if size in have:
        state = f"installed {have[size]}"
    else:
        state = install_command(size)
    print(f"  {size:<4} {entry['dist']:<16} {entry['version']:<8} {mb:7.0f} MB  {state}")
