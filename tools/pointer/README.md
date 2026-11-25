# $dist $version

The LatinCy $size spaCy pipeline for Latin.

```bash
pip install $install_name
```

```python
import spacy

nlp = spacy.load("$dist")
```

It is also installed by `$latincy_install`, part of [latincy](https://github.com/latincy/latincy).

## How it is installed

The model is hosted on Hugging Face at [$repo](https://huggingface.co/$repo). This package contains no model: when pip or uv installs it, it downloads the model wheel (`$dist` $wheel_version) from Hugging Face at a pinned commit, checks its sha256, and installs it. A wheel whose checksum does not match is refused.

The PyPI version ($version) is the LatinCy release; `nlp.meta["version"]` reports the model's own version ($wheel_version).

To install without network access to Hugging Face, download `$filename` and set `LATINCY_WHEELHOUSE` to its folder; the checksum is still checked.

Model card, evaluation and license: https://huggingface.co/$repo
