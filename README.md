# latincy

Install and load the [LatinCy](https://huggingface.co/latincy) spaCy pipelines for Latin.

## Install

```bash
pip install latincy            # la_core_web_sm
pip install "latincy[md]"
pip install "latincy[lg]"
pip install "latincy[trf]"
```

Each model can also be installed on its own, e.g. `pip install la-core-web-lg`.

## Models

| size | PyPI package | model on Hugging Face | model version | download |
|---|---|---|---|---|
| sm | `la-core-web-sm` 0.3.0 | [latincy/la_core_web_sm](https://huggingface.co/latincy/la_core_web_sm) | 3.9.8 | 19 MB |
| md | `la-core-web-md` 0.3.0 | [latincy/la_core_web_md](https://huggingface.co/latincy/la_core_web_md) | 3.9.8 | 73 MB |
| lg | `la-core-web-lg` 0.3.0 | [latincy/la_core_web_lg](https://huggingface.co/latincy/la_core_web_lg) | 3.9.8 | 297 MB |
| trf | `la-core-web-trf` 0.3.0 | [latincy/la_core_web_trf](https://huggingface.co/latincy/la_core_web_trf) | 3.9.9 | 1689 MB |

The PyPI version is the LatinCy release (0.3.0); `nlp.meta["version"]` reports the model's own version.

## Choosing a size

- **sm**, **md**, **lg** run on CPU without PyTorch; md and lg add floret word vectors.
- **trf** uses a Latin BERT encoder, needs PyTorch, and ran about 3× slower than lg in a CPU benchmark (203 vs 620 words/s); a GPU is recommended.
- Accuracy for each model is reported on its model card (links above).

## Use

```python
import latincy

nlp = latincy.load("lg")
doc = nlp("Gallia est omnis divisa in partes tres.")
```

`spacy.load("la_core_web_lg")` works as well. `python -m latincy` lists the four sizes and which are installed.

`latincy.load()` without a size loads sm and emits a `SmallModelWarning` with the command to install lg or trf (or, if a larger size is already installed, how to load it). Pass `size="sm"` to load sm without the warning.

## How the models are installed

The models are hosted on Hugging Face, not PyPI. Each `la-core-web-*` package on PyPI contains no model: when pip or uv installs it, it downloads the model wheel from Hugging Face at a pinned commit, checks its sha256, and installs it. A wheel whose checksum does not match is refused. The pins (commit, sha256, size) are in [`src/latincy/models.json`](https://github.com/latincy/latincy/blob/main/src/latincy/models.json).

The `la-core-web-*` packages are published as source distributions only, so installs restricted to prebuilt wheels (`--only-binary :all:`) cannot install them.

To install without network access to Hugging Face, download the wheels named in `models.json` from their Hugging Face repos (keep the file names) and point `LATINCY_WHEELHOUSE` at their folder; the checksum is still checked:

```bash
LATINCY_WHEELHOUSE=/path/to/wheels pip install "latincy[lg]"
```

## License

MIT
