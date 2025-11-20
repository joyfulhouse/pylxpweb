# CI/CD Pipeline Implementation

**Date**: 2025-11-19
**Status**: Complete ✅

## Overview

Complete implementation of CI/CD pipelines for the pylxpweb project, following the reference implementation from [pythermacell](https://github.com/joyfulhouse/pythermacell).

## Implemented Files

### 1. CI Workflow (`.github/workflows/ci.yml`)

**Purpose**: Continuous integration for all pushes and pull requests

**Workflow Structure**:
```
Lint & Type Check (parallel) ─┐
Unit Tests (parallel)         ─┼─> Integration Tests ─> CI Success
                               │
                               └─> (all must pass)
```

**Triggers**:
- Push to `main` or `master` branches
- Pull requests
- Manual dispatch (`workflow_dispatch`)

**Jobs**:

1. **Lint & Type Check** (10 min timeout)
   - Actions: `checkout@v5`, `setup-uv@v7`
   - Python: 3.13 (via `uv python install 3.13`)
   - Steps:
     - `ruff check src/ tests/`
     - `ruff format --check src/ tests/`
     - `mypy --strict src/pylxpweb/`

2. **Unit Tests** (15 min timeout)
   - Actions: `checkout@v5`, `setup-uv@v7`
   - Python: 3.13 (via `uv python install 3.13`)
   - Steps:
     - `pytest tests/unit/ --cov=pylxpweb --cov-report=term-missing --cov-report=xml --cov-report=html -v`
     - Upload coverage to Codecov (`codecov-action@v5`)
     - Upload coverage HTML and pytest results (`upload-artifact@v5`, 30-day retention)

3. **Integration Tests** (20 min timeout)
   - Depends on: Lint & Unit Tests passing
   - Environment: `integration-test`
   - Skips for Dependabot PRs (no secret access)
   - Environment variables: `LUXPOWER_USERNAME`, `LUXPOWER_PASSWORD`, `LUXPOWER_BASE_URL`
   - Steps:
     - `pytest tests/integration/ -v -m integration`

4. **CI Success**
   - Depends on: All previous jobs
   - Validates all jobs passed (allows integration test to be skipped)

**Key Features**:
- Concurrency control: Cancel in-progress runs
- uv caching: Lock file-based dependency caching
- Artifact retention: 30 days for coverage and test results

---

### 2. Publish Workflow (`.github/workflows/publish.yml`)

**Purpose**: Build and publish package to TestPyPI and PyPI

**Workflow Structure**:
```
Lint ─┐
Test  ─┼─> Integration Tests ─> Build ─> TestPyPI ─> PyPI
       │
       └─> (all must pass)
```

**Triggers**:
- GitHub releases (`published` type)
- Manual dispatch with environment selection (`testpypi` or `pypi`)

**Permissions**:
- `contents: read`
- `id-token: write` (OIDC authentication for PyPI publishing)

**Jobs**:

1. **Lint & Type Check** (10 min timeout)
   - Same as CI workflow

2. **Unit Tests** (15 min timeout)
   - Actions: `checkout@v5`, `setup-uv@v7`
   - Python: 3.13
   - Steps:
     - `pytest tests/unit/ --cov=pylxpweb --cov-report=term-missing --cov-report=xml --junitxml=pytest.xml`

3. **Integration Tests** (20 min timeout)
   - Depends on: Lint & Unit Tests
   - Environment: `integration-tests`
   - Same setup as CI workflow

4. **Build Package** (10 min timeout)
   - Depends on: All quality checks passing
   - Steps:
     - `uv build` - Creates wheel and sdist
     - `uv run twine check dist/*` - Validates package metadata
     - Upload artifacts: `python-package-distributions` (`upload-artifact@v5`, 7-day retention)

5. **Publish to TestPyPI** (10 min timeout)
   - Depends on: Build
   - Environment: `testpypi`
   - Permissions: `id-token: write`
   - Actions: `download-artifact@v6`, `pypa/gh-action-pypi-publish@release/v1`
   - Repository: `https://test.pypi.org/legacy/`
   - Creates summary with test installation command

6. **Publish to PyPI** (10 min timeout)
   - Depends on: Build & TestPyPI success
   - Environment: `pypi`
   - Permissions: `id-token: write`
   - Actions: `download-artifact@v6`, `pypa/gh-action-pypi-publish@release/v1`
   - Creates summary with PyPI link and install command

**Key Features**:
- OIDC authentication: No API tokens required (trusted publisher setup)
- Staged publishing: TestPyPI first, then PyPI
- Rich summaries: Installation commands and package links
- Package validation: `twine check` before publishing
- Concurrency control: Only one publish at a time

---

### 3. Dependabot Configuration (`.github/dependabot.yml`)

**Purpose**: Automated dependency updates

**Update Schedules**:

1. **GitHub Actions** (Weekly, Mondays)
   - Package ecosystem: `github-actions`
   - Max open PRs: 5
   - Labels: `dependencies`, `github-actions`
   - Commit format: `chore(deps): update GitHub Actions`

2. **Python Dependencies** (Weekly, Mondays)
   - Package ecosystem: `uv` (modern approach)
   - Max open PRs: 10
   - Labels: `dependencies`, `python`
   - Commit format: `chore(deps): update Python dependencies`
   - Reviewer: `bryanli` (ensures uv compatibility)

**Dependency Grouping**:

Groups minor and patch updates together:

- **Development Dependencies**:
  - Dependency type: `development`
  - Update types: `minor`, `patch`
  - Includes: pytest, ruff, mypy, coverage, etc.

- **Production Dependencies**:
  - Dependency type: `production`
  - Update types: `minor`, `patch`
  - Includes: aiohttp, pydantic, etc.

**Key Features**:
- Native `uv` ecosystem support
- Smart grouping: Reduces PR volume
- Consistent commit messages: `chore(deps)` prefix
- Reviewer assignment: Ensures compatibility verification

---

## GitHub Actions Versions

All workflows use the latest stable versions:

- `actions/checkout@v5`
- `astral-sh/setup-uv@v7`
- `actions/upload-artifact@v5`
- `actions/download-artifact@v6`
- `codecov/codecov-action@v5`
- `pypa/gh-action-pypi-publish@release/v1`

---

## GitHub Configuration Requirements

### Secrets (Repository Settings)

Required for integration tests and publishing:

```bash
# Integration tests
LUXPOWER_USERNAME=<your_username>
LUXPOWER_PASSWORD=<your_password>
LUXPOWER_BASE_URL=https://monitor.eg4electronics.com

# Optional: Codecov token
CODECOV_TOKEN=<your_codecov_token>
```

**Setup via GitHub CLI**:
```bash
gh secret set LUXPOWER_USERNAME --body "$LUXPOWER_USERNAME"
gh secret set LUXPOWER_PASSWORD --body "$LUXPOWER_PASSWORD"
gh secret set LUXPOWER_BASE_URL --body "$LUXPOWER_BASE_URL"
gh secret set CODECOV_TOKEN --body "$CODECOV_TOKEN"
```

### Environments

Create the following environments in GitHub repository settings:

1. **integration-test**
   - Secrets: `LUXPOWER_USERNAME`, `LUXPOWER_PASSWORD`, `LUXPOWER_BASE_URL`
   - Protection rules: Optional

2. **integration-tests** (for publish workflow)
   - Same secrets as above
   - Protection rules: Optional

3. **testpypi**
   - No secrets required (uses OIDC)
   - Protection rules: Recommended (require approval)
   - Trusted publisher: Configure on test.pypi.org

4. **pypi**
   - No secrets required (uses OIDC)
   - Protection rules: Strongly recommended (require approval)
   - Trusted publisher: Configure on pypi.org

### PyPI Trusted Publishers (OIDC)

**TestPyPI Setup**:
1. Go to https://test.pypi.org/manage/account/publishing/
2. Add publisher:
   - PyPI Project Name: `pylxpweb`
   - Owner: `joyfulhouse`
   - Repository: `pylxpweb`
   - Workflow: `publish.yml`
   - Environment: `testpypi`

**PyPI Setup**:
1. Go to https://pypi.org/manage/account/publishing/
2. Add publisher:
   - PyPI Project Name: `pylxpweb`
   - Owner: `joyfulhouse`
   - Repository: `pylxpweb`
   - Workflow: `publish.yml`
   - Environment: `pypi`

---

## Usage

### Running CI

CI runs automatically on:
- Every push to `main`/`master`
- Every pull request
- Manual trigger via Actions tab

### Publishing Releases

**Automatic (Recommended)**:
1. Create a GitHub release (with tag like `v0.1.0`)
2. Publish the release
3. Workflow automatically:
   - Runs all quality checks
   - Builds package
   - Publishes to TestPyPI
   - Publishes to PyPI (if TestPyPI succeeds)

**Manual**:
1. Go to Actions → Publish to PyPI
2. Click "Run workflow"
3. Select environment: `testpypi` or `pypi`
4. Click "Run workflow"

---

## Validation

All YAML files validated with PyYAML:

```bash
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('✅ CI workflow YAML is valid')"
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/publish.yml')); print('✅ Publish workflow YAML is valid')"
uv run python -c "import yaml; yaml.safe_load(open('.github/dependabot.yml')); print('✅ Dependabot YAML is valid')"
```

**Result**: ✅ All workflows are syntactically valid

---

## Key Improvements Over Previous Implementation

1. **Modern uv Pattern**: Using `uv python install 3.13` instead of `setup-python` action
2. **Latest Actions**: All GitHub Actions updated to v5/v6/v7
3. **Better Coverage**: Added term-missing, XML, and HTML coverage reports
4. **OIDC Publishing**: Secure PyPI publishing without API tokens
5. **Rich Summaries**: User-friendly workflow outputs with install commands
6. **Dependency Grouping**: Smarter Dependabot updates reduce PR noise
7. **Native uv Support**: Dependabot uses `uv` ecosystem directly
8. **Package Validation**: Added `twine check` step before publishing
9. **Concurrency Control**: Proper workflow cancellation and serialization

---

## Reference

Based on: [joyfulhouse/pythermacell](https://github.com/joyfulhouse/pythermacell/tree/main/.github)

Documentation: See `CLAUDE.md` sections "Pre-Commit Workflow" and "GitHub & CI/CD"

---

## Next Steps

1. ✅ Configure GitHub secrets (if not already done)
2. ✅ Create GitHub environments
3. ✅ Set up PyPI trusted publishers
4. ✅ Test CI workflow with a push or PR
5. ✅ Test publish workflow with a GitHub release

**Status**: Ready for production use
