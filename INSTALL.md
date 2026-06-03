# Installing pylxpweb

## Requirements

- Python 3.13 or newer.

## Install from PyPI

```bash
pip install pylxpweb
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add pylxpweb
```

## Install from Source

```bash
git clone https://github.com/joyfulhouse/pylxpweb.git
cd pylxpweb
uv sync
```

This installs the package with its development dependencies into a local virtual
environment.

## Verify the Installation

```bash
python -c "import pylxpweb; print(pylxpweb.__version__)"
```

You should see the installed version printed with no import errors.

## Next Steps

See the [README](README.md#quick-start) for a quick-start example and usage
guide.
