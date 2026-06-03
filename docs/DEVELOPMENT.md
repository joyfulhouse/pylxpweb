# Development

How to set up a development environment for pylxpweb.

## Prerequisites

- Python 3.13+ and [`uv`](https://docs.astral.sh/uv/).

## Setup

```bash
git clone https://github.com/joyfulhouse/pylxpweb.git
cd pylxpweb
uv sync
```

## Quality Checks

```bash
uv run pytest          # tests
uv run ruff check      # lint
uv run ruff format     # format
uv run mypy            # type check
```

Run all of these before opening a pull request. See
[CONTRIBUTING](https://github.com/joyfulhouse/.github/blob/main/CONTRIBUTING.md)
for the contribution workflow.

## Releasing

Releases are published to PyPI via the `release.yml` workflow on a tagged
version. Bump the version in `pyproject.toml`, update `CHANGELOG.md`, tag, and
push.
