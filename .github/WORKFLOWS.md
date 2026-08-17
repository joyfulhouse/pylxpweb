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

The only trigger is a GitHub Release `published` event. Pushing a tag does not run
the workflow, and there is no branch-form manual release path. GitHub must execute
the copy of `release.yml` stored in the release tag: `github.workflow_ref` must end
in `@refs/tags/<tag>` and `github.workflow_sha`, `github.sha`, and the peeled tag
commit must all be identical.

### Published-release path

Publishing is a linear seven-job promotion chain:

1. `bind-build-attest` force-fetches only `origin/main` with `--no-tags`, then
   peels the event tag and requires the tag commit to be current `main`. The commit
   must be a two-parent GitHub merge commit associated with exactly one merged
   pull request. Its first parent is the previous `main`, its second parent is the
   final pull-request head, and the first parent must be an ancestor of that head.
   The PR base is `main`; GitHub's mutable `pull.base.sha` is not used as historical
   merge evidence. An effective non-self approval covers the exact head. The
   head's single `CI Success` check must come from GitHub Actions and resolve to a
   successful pull-request run of this repository's `.github/workflows/ci.yml`.
2. The same job builds once in the official uv/Python 3.13 image pinned by the
   platform-manifest digest recorded in the workflow. Source and container root
   are read-only; only the distribution directory, ephemeral `/tmp`, and an empty
   uv cache are writable. The checkout must have no tracked, staged, or
   build-relevant untracked changes before the build, and that condition is
   rechecked at sealing while allowing only the generated `release-bundle/`.
   The container has no network. uv and Python versions and the exact bundled
   `uv_build` backend are asserted, and `SOURCE_DATE_EPOCH` is set unconditionally
   from the bound commit timestamp rather than inherited from the runner, before
   `uv build --offline --no-python-downloads --no-sources` creates exactly one
   wheel and one source distribution.
3. Immediately before attestation, the job force-fetches `origin/main` again and
   requires equality with the bound commit. This is the artifact-sealing
   linearization point. Separate GitHub source-identity and build-provenance
   attestations are generated, stored with the bundle, and the sealed artifact is
   uploaded once.
4. `prepare-testpypi` has no OIDC permission. It verifies the bundle's exact file
   set and checksums and uses `gh attestation verify` to bind both attestations to
   the release workflow, workflow digest, tag ref, source digest, and distribution
   digests. Only then does it stage the two distributions.
5. `publish-testpypi` has exactly two action steps: a full-SHA-pinned artifact
   download and the full-SHA-pinned official PyPA publisher. It has OIDC only for
   TestPyPI trusted publishing and may skip an already-present TestPyPI file.
6. `verify-testpypi` is unprivileged. It revalidates the original sealed artifact,
   polls the exact TestPyPI version, requires exactly the two non-yanked filenames
   and SHA-256 digests, and downloads and rehashes their allowlisted HTTPS bytes.
   It then takes a second exact index snapshot so a competing publication during
   download fails closed. Production verification uses the same rule.

The TestPyPI verifier's mechanical worst case is 12 minutes 45 seconds: twelve
30-second index attempts, 255 seconds of capped backoff, two 60-second downloads,
and a final 30-second snapshot. Its 20-minute job timeout leaves 7 minutes 15
seconds for artifact download, checksums, attestation verification, and runner
overhead. The PyPI verifier's corresponding worst case is 8 minutes 45 seconds
inside a 15-minute job, leaving 6 minutes 15 seconds. A 10-second socket timeout
only detects inactivity; a process-level total-transfer deadline separately caps
each index request at 30 seconds and each distribution download at 60 seconds.
7. `prepare-pypi`, `publish-pypi`, and `verify-pypi` repeat the separation for
   production: the no-OIDC prepare job revalidates and stages only when the
   version is absent; the OIDC publisher again contains only the two pinned
   actions; and the no-OIDC verifier polls and downloads the exact final bytes.

The sealed artifact is named from the version and merge commit and is retained for
30 days. The two staged upload artifacts use the same 30-day retention so a delayed
protected-environment approval does not require rebuilding or restaging. Job
summaries expose the tag, commit, tree, final PR/head, workflow
ref/SHA, container digest, distribution names/digests, and attestation verification.

GitHub build/source attestations establish the GitHub workflow and source identity
for the local subjects. They are distinct from the PEP 740 attestations that the
PyPA publishing action generates and sends to PyPI during trusted publication.

### Required repository settings

The workflow cannot create or repair these external controls. Verify them before
unfreezing publication and again during release review:

- `main` is protected: the final release-candidate PR requires review, dismisses
  stale approval, requires `CI Success`, requires the branch to be up to date,
  prevents bypass, and is merged with GitHub's **Create a merge commit** method.
- A tag ruleset protects `v*` tags from update and deletion except for the narrow,
  audited recovery operation described below.
- The `pypi` environment requires an independent reviewer, limits deployments to
  protected `v*` tags, and disallows administrator bypass.
- The `testpypi` environment limits deployments to protected `v*` tags.
- PyPI and TestPyPI trusted-publisher bindings match this repository, the
  `release.yml` workflow, and their respective environment names.
- The repository remains public. Checkout credentials are deliberately not
  persisted, and both source-binding fetches rely on anonymous read-only access to
  `origin/main`; a visibility change therefore fails closed before any build.

These are post-merge settings gates. The workflow and this document do not apply
or mutate repository, environment, or package-index settings.

## Release procedure

1. Prepare the final version and every release-tree change in one final candidate
   pull request. `project.version` must equal the intended tag without `v`.
2. Obtain an effective approval and successful required CI on the exact final head.
   If the head changes, repeat both gates.
3. Merge with GitHub **Create a merge commit**. Do not squash or rebase.
4. Confirm no later commit has reached `main`, then create the protected `v*` tag
   on that GitHub merge commit and publish the GitHub Release for the same tag.
5. Review the identity and attestation summaries after TestPyPI verification, then
   approve the protected `pypi` environment if every value matches the candidate.

### Recovery at the sealing boundary

- If `main` moves before artifact sealing, the second equality check fails and no
  package-index upload occurs. Delete the unpublished or failed GitHub Release and
  its tag using the audited tag-recovery path. Prepare a new final candidate on
  current `main`, obtain fresh exact-head review and CI, merge it, and create a new
  release tag. Do not retarget or recreate the old candidate tag.
- Movement of `main` after the sealing check does not change the sealed artifact.
  The bound commit/tree/PR/workflow/container and attestation results remain visible
  in the summaries. Treat the protected-environment approval as the explicit human
  decision whether to promote that sealed candidate or reject it and use the new
  candidate procedure above.
- If TestPyPI or PyPI contains unexpected or mismatched files, stop. Package-index
  files are immutable; do not use `skip-existing` in production and do not rebuild
  under the same version. Investigate before preparing a new version.

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

- A source-identity failure means the event tag, project version, commit, tree,
  tag-resident workflow identity, reviewed merge identity, or freshly fetched
  `main` did not agree. Correct the release inputs; do not weaken the check.
- A TestPyPI verification failure means the remote name, version, filenames,
  yanked state, hashes, or downloaded distributions did not match the sealed
  artifact.
- A PyPI job waiting for approval is enforcing the production environment gate.
- An OIDC failure requires checking the corresponding trusted-publisher binding;
  do not add long-lived package-index credentials.

## References

- [GitHub Actions](https://docs.github.com/en/actions)
- [GitHub deployment environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
- [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/)
