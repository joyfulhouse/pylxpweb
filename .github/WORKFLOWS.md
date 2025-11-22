# GitHub Workflows Documentation

This document explains the CI/CD setup for pylxpweb.

## Overview

The project uses a three-stage workflow optimized for efficiency:

```
PR → CI runs → Merge to main (no CI rerun) → Tag → Auto-release → Publish to PyPI
```

## Workflows

### 1. CI Workflow (`ci.yml`)

**Trigger**: Pull requests only (not pushes to main)

**Purpose**: Run all quality checks before code is merged

**Jobs**:
- Lint & Type Check (ruff, mypy)
- Unit Tests (pytest with coverage)
- Integration Tests (real API tests)
- CI Success (aggregate status check)

**Why no push to main?**
- Prevents redundant CI runs
- Branch protection ensures CI passes before merge
- Code is already tested in the PR

### 2. Release Workflow (`release.yml`)

**Trigger**: Version tags (`v*.*.*`)

**Purpose**: Automatically create GitHub Release with changelog

**Example**:
```bash
git tag v0.3.4
git push origin v0.3.4
# → Automatically creates GitHub Release
```

**What it does**:
1. Extracts version from tag
2. Pulls changelog section for that version from CHANGELOG.md
3. Creates GitHub Release with changelog

### 3. Publish Workflow (`publish.yml`)

**Trigger**: GitHub Release published (automatic from release.yml)

**Purpose**: Build and publish package to PyPI

**Jobs**:
1. Build package (uv build + twine check)
2. Publish to TestPyPI (for verification)
3. Publish to PyPI (production)

**Why no tests?**
- All code is already tested in the PR (via CI workflow)
- Branch protection prevents untested code from reaching main
- Re-running tests would be redundant and wasteful

## Branch Protection

The `main` branch is protected with these rules:

- ✅ Require pull request before merging (no direct commits)
- ✅ Require "CI Success" status check to pass
- ✅ Require branches to be up to date before merging
- ✅ Dismiss stale PR reviews when new commits pushed
- ✅ Enforce rules for administrators
- ✅ Block force pushes
- ✅ Block branch deletion

### Setup Branch Protection

Run once to configure:

```bash
.github/setup-branch-protection.sh
```

Or configure manually at:
https://github.com/joyfulhouse/pylxpweb/settings/branches

## Release Process

### Standard Release (Patch/Minor)

1. **Bump version** in PR:
   ```bash
   # Update version in:
   # - src/pylxpweb/__init__.py
   # - pyproject.toml
   # - CHANGELOG.md
   ```

2. **Create and merge PR**:
   - CI runs automatically
   - Merge after "CI Success" passes

3. **Tag and push**:
   ```bash
   git checkout main
   git pull
   git tag v0.3.4
   git push origin v0.3.4
   ```

4. **Automatic from here**:
   - `release.yml` creates GitHub Release
   - `publish.yml` publishes to PyPI

### Manual Publish (Emergency)

If you need to publish without creating a release:

```bash
gh workflow run publish.yml -f environment=pypi
```

## Workflow Efficiency

### Before (Old Setup)
```
PR: CI runs (5 min)
Merge: CI runs again (5 min) ❌ Redundant!
Release: CI runs third time (5 min) ❌ Redundant!
Publish: 2 min
Total: 17 minutes, 2 redundant CI runs
```

### After (New Setup)
```
PR: CI runs (5 min)
Merge: No CI (instant) ✅
Tag: Release created (10 sec) ✅
Publish: 2 min ✅
Total: 7 minutes, zero redundancy
```

**Savings**: 10 minutes per release + 2 fewer CI runs

## CI Run Statistics

- **Unit Tests**: ~53 seconds (492 tests)
- **Integration Tests**: ~2.5 minutes (67 tests)
- **Lint & Type Check**: ~14 seconds
- **Total CI Time**: ~3.5 minutes per PR

## Troubleshooting

### CI didn't run on my PR
- Check that the PR is targeting `main` branch
- Manually trigger: Go to Actions → CI → Run workflow

### Release didn't create
- Verify tag format: `v*.*.*` (e.g., `v0.3.4`)
- Check Actions tab for errors
- Manually create release via GitHub UI

### Publish failed
- Check PyPI credentials (OIDC configured?)
- Verify version doesn't already exist on PyPI
- Check Actions tab for detailed error logs

## Local Testing

Before pushing:

```bash
# Run all checks locally
uv run ruff check --fix && uv run ruff format
uv run mypy --strict src/pylxpweb/
uv run pytest tests/unit/ --cov=pylxpweb
uv run pytest tests/integration/ -m integration  # Requires .env

# Build package
uv build
uv run twine check dist/*
```

## References

- [GitHub Branch Protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches)
- [GitHub Actions](https://docs.github.com/en/actions)
- [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
