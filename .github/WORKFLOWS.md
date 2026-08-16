# GitHub Workflows

This document describes the CI and package-publication paths for pylxpweb. The
workflow files are the source of truth for their executable details.

## Pull request CI (`ci.yml`)

CI runs for pull requests and can also be started manually. It does not run for
pushes to `main`.

The workflow has four jobs:

1. `lint` runs Ruff checks, Ruff formatting validation, and strict mypy.
2. `test` runs the unit suite with coverage and uploads coverage artifacts.
3. `integration` runs after lint and unit tests in the protected
   `integration-tests` environment. Dependabot pull requests skip this job.
4. `ci-success` aggregates the preceding results for branch protection.

## Package release (`release.yml`)

The only publishing trigger is a GitHub Release `published` event. Pushing a tag
does not run this workflow, and a manual dispatch cannot publish to either package
index.

### Published-release path

Publishing is a four-job promotion chain:

1. `build` resolves the release's existing `v*` tag, peels it to a commit and
   tree, and checks that the tag version, project metadata, release event, release
   target, checked-out commit, and `origin/main` ancestry agree. It builds exactly
   one wheel and one source distribution under Python 3.13 from a locked,
   unchanged checkout, runs `twine check`, records source identity in
   `release-source.json`, and records each distribution and the source manifest
   in `SHA256SUMS`.
2. `publish-testpypi` downloads and revalidates that one named Actions artifact,
   then publishes it to TestPyPI with trusted publishing. `skip-existing` is
   permitted here so an interrupted release can resume at the verification gate.
3. `verify-testpypi` is unprivileged. It downloads and revalidates the original
   Actions artifact, polls the exact TestPyPI name and version with bounded
   retries, requires the exact non-yanked filename and SHA256 set, then downloads
   and rehashes both the allowlisted HTTPS wheel and source distribution. The job
   installs the verified local wheel in a clean Python 3.13 environment while
   resolving dependencies only from production PyPI, then validates installed
   metadata and import behavior.
4. `publish-pypi` runs only after verification succeeds. It again downloads and
   revalidates the original artifact, checks any files already present for the
   version on PyPI, and accepts only a non-yanked, hash-matching subset of the
   wheel and source distribution. The preflight retries transient index failures
   up to three times while treating a genuine version 404 as an empty set. It
   stages and publishes only absent files from the original artifact. If the
   complete exact set already exists, it skips the publisher. It never rebuilds
   and never uses `skip-existing`. After publication, it polls PyPI with bounded
   retries until the final filenames, yanked states, and hashes exactly match.
   The final retry budget leaves at least five minutes of the job timeout for
   setup and upload. An upload race fails the publisher closed and can be retried
   through the same preflight path.

The build artifact is named from the project version and peeled commit and is
retained for 30 days. The workflow default permission is `contents: read`; only
the two publisher jobs receive `id-token: write`. Production uses the protected
`pypi` environment, while TestPyPI uses `testpypi`.

### Manual validation path

Manual dispatch requires an existing `v*` tag:

```bash
gh workflow run release.yml --ref main -f tag=v0.10.0b3
```

The dispatch must select `main`. It runs only the source-identity, build, package,
manifest, and artifact checks. All publication and remote-index verification jobs
are skipped. Use this path to validate release construction without publishing.

### Required repository settings

Before relying on the published-release path, verify these settings after the
workflow change merges:

- The `pypi` environment requires a reviewer, limits deployment tags to `v*`, and
  does not allow administrators to bypass protection.
- The `testpypi` environment limits deployment tags to `v*`.
- PyPI and TestPyPI trusted-publisher bindings match this repository, the
  `release.yml` workflow, and their respective environment names.

These are post-merge settings gates. The workflow and this document do not apply
or mutate repository, environment, or package-index settings.

## Release procedure

1. Prepare the version in a pull request. `project.version` in `pyproject.toml`
   must be the intended tag without the leading `v`.
2. Merge the reviewed change to `main` after CI succeeds.
3. Create the `v*` tag on the intended `main` commit.
4. Optionally run the manual validation path for that tag.
5. Publish a GitHub Release for the same tag. Publication starts the package
   promotion chain.
6. Review the TestPyPI verification result and approve the protected `pypi`
   environment when prompted.

If production publication is interrupted, rerun the same release workflow. The
preflight accepts matching files already published from the original artifact and
stages only the absent distribution; it never enables production `skip-existing`.

## Package publishing compromise response

If a release workflow or authorized GitHub identity may be compromised:

1. Cancel active release workflow runs and pending environment approvals.
2. Disable the `pypi` and `testpypi` environments or remove the corresponding
   trusted-publisher bindings so no new package-index identity can be minted.
3. Audit the compromised GitHub identity and revoke its sessions, tokens, and
   keys. Review repository, environment, release, and package-index audit records
   for unauthorized changes or publications.
4. Restore environments and trusted-publisher bindings only after recovery,
   identity rotation, artifact verification, and review are complete.

Trusted publishing remains secretless. No long-lived package-index credential is
introduced for normal publication or recovery.

## Executable builds (`build-executables.yml`)

Publishing a GitHub Release also starts the separate executable-build workflow for
Windows, macOS, and Linux. It can be dispatched manually. This path is independent
of the Python package promotion artifact described above.

## Local validation

Use the locked uv environment:

```bash
uv sync --locked --all-extras
uv run pytest tests/unit/test_release_workflow.py -v
uv run pytest tests/unit/ -q
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy --strict src/pylxpweb/
uv build
uv run twine check dist/*
```

No local command exercises a publisher job. TestPyPI and PyPI publication require
the GitHub-hosted release event, protected environments, and trusted publishing.

## Troubleshooting

- A manual run with skipped `build` selected a ref other than `main`.
- A source-identity failure means the event tag, project version, commit, tree,
  release target, or `main` ancestry did not agree. Correct the release inputs; do
  not weaken the check.
- A TestPyPI verification failure means the remote name, version, filenames,
  yanked state, hashes, downloaded wheel, dependency install, metadata, or import
  did not match the built artifact.
- A PyPI job waiting for approval is enforcing the production environment gate.
- An OIDC failure requires checking the corresponding trusted-publisher binding;
  do not add long-lived package-index credentials.

## References

- [GitHub Actions](https://docs.github.com/en/actions)
- [GitHub deployment environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
- [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/)
