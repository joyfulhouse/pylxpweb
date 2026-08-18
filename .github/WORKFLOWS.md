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
   download fails closed.

The TestPyPI verifier's mechanical worst case is 12 minutes 45 seconds: twelve
30-second index attempts, 255 seconds of capped backoff, two 60-second downloads,
and a final 30-second snapshot. Its 20-minute job timeout leaves 7 minutes 15
seconds for artifact download, checksums, attestation verification, and runner
overhead. A 10-second socket timeout only detects inactivity; a process-level
total-transfer deadline separately caps each index request at 30 seconds and each
distribution download at 60 seconds.
7. `prepare-pypi` has no OIDC and is itself protected by the `pypi` environment.
   It does not trust only prior job outputs: it queries the Actions run and artifact
   APIs for `github.run_id`, requires exactly one non-expired sealed artifact with
   the expected repository, release run, head, deterministic name, and upload
   digest, then downloads it by artifact ID with digest mismatch set to an error.
   It rechecks the bundle hashes, source identity, and separate source/build
   attestations before taking two PyPI snapshots around any distribution downloads.
   Each index snapshot requires the final response URL to be HTTPS on the pinned
   `pypi.org` index host, so an off-origin redirect — including one that ends in a
   404 — classifies as `UNCERTAIN`, never as `ABSENT`. Every expected file the
   index advertises is validated (metadata digest, advertised and final HTTPS
   `files.pythonhosted.org` URL, and downloaded bytes) before subset/superset
   classification, so a partial or extra file set with any conflicting evidence
   classifies as `MISMATCH` rather than `PARTIAL`/`EXTRA`. Its evidence steps
   tolerate failure: a missing, expired, duplicated, or unverifiable sealed
   artifact or attestation funnels into a **successful** prepare result with
   state `UNCERTAIN` instead of terminating the job, so the terminal verifier
   below still runs and fails closed. It emits one state from the closed state
   machine below and stages the **full** wheel-plus-sdist set only for `ABSENT`.
8. `publish-pypi` runs only when the fresh prepare output is exactly `ABSENT`. It
   retains exactly two full-SHA-pinned action steps: download the run-attempt-scoped
   staging artifact and invoke the official PyPA publisher. This is the only
   production OIDC job. It has no shell, `skip-existing`, partial-file path, or
   continue-on-error behavior.
9. `verify-pypi` is the sole terminal definition of production completion. Its
   `always()`/non-cancelled condition runs it after a successful prepare whether
   the publisher succeeded, failed, or was skipped. It rediscovers and revalidates
   the sealed artifact and attestations, reruns the same classifier against fresh
   PyPI bytes, and succeeds only for `EXACT_COMPLETE`. Unlike `prepare-pypi`, its
   evidence steps fail hard: any evidence failure fails the terminal verifier
   itself. Because it runs immediately after `publish-pypi`, routine PyPI index
   propagation can briefly report absence: the terminal reclassification wraps a
   stable `ABSENT` snapshot pair in a bounded recheck loop (12 attempts, 5-second
   backoff base capped at 30 seconds — the TestPyPI verifier's envelope). Each
   attempt keeps the full two-snapshot stability rule, only `ABSENT` retries, and
   `prepare-pypi` keeps its single-pass classification semantics: absence is a
   publishable state there and must never be retried away.

The prepare-time classifier's mechanical worst case is 3 minutes 5 seconds: two
30-second index snapshots, two 60-second downloads, and a five-second stability
interval. Its 15-minute prepare timeout leaves 11 minutes 55 seconds for Actions
API discovery, artifact download, checksum and attestation verification, and
runner overhead. The terminal reclassification's mechanical worst case is 19
minutes 15 seconds: twelve 65-second snapshot pairs, 255 seconds of capped
backoff, and two 60-second downloads on the final attempt. The 25-minute
`verify-pypi` timeout leaves 5 minutes 45 seconds for the same non-classifier
work.

| State | Meaning | Workflow consequence |
|---|---|---|
| `ABSENT` | Two clean 404 snapshots with no conflicting or uncertain evidence | The only state that stages and permits the publisher |
| `EXACT_COMPLETE` | Stable exact filenames, index hashes, allowlisted final hosts, downloaded bytes, non-yanked status, sealed bundle, and GitHub attestations | Publisher skips; terminal verifier succeeds |
| `PARTIAL` | A stable non-empty strict subset whose present files fully validate (metadata, hosts, and downloaded bytes) | Terminal failure; burn the version and never top up |
| `MISMATCH` | Stable identity, hash, host, or downloaded-byte conflict — including one inside an otherwise partial or extra file set | Terminal failure; preserve evidence and use compromise/new-version procedure |
| `YANKED` | Any advertised remote file for the version is yanked, expected or not | Terminal failure; preserve evidence and use compromise/new-version procedure |
| `EXTRA` | The full expected set, fully validated, plus stable additional files | Terminal failure; preserve evidence and use compromise/new-version procedure |
| `COMPETING` | A duplicate filename or another stable occupied file set | Terminal failure; preserve evidence and use compromise/new-version procedure |
| `UNCERTAIN` | Timeout, TLS/JSON/API/429/5xx error, off-origin index redirect, inconsistent snapshots, or unavailable artifact/attestation evidence | Never publish; retry only the classifier/verifier recovery chain |

The sealed artifact is named from the version and merge commit and is retained for
30 days. Staging artifacts also retain for 30 days and include `github.run_attempt`
in their names so a recovery attempt cannot collide with immutable staging from an
earlier attempt. Job summaries expose the tag, commit, tree, final PR/head,
workflow ref/SHA, container digest, distribution names/digests, attestation
verification, classifier state, evidence, and required action.

### Pinned artifact-action contract evidence

Three digest-binding assumptions in `release.yml` are properties of the pinned
action code, not of the workflow YAML — GitHub Actions silently ignores unknown
action inputs, so these facts must be re-verified whenever either pin moves
(`tests/unit/test_release_workflow.py::test_artifact_action_pins_match_recorded_contract_verification`
fails until this note and the test's recorded map match the new pin):

- `actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` (v8.0.0),
  `action.yml` SHA-256
  `e98559b7a31ba31be4709f20d22102dc2737fa630f69a339eb89981151e505fe`:
  - Declares the `digest-mismatch` input (options `ignore`/`info`/`warn`/`error`,
    default `error`), so `digest-mismatch: error` is enforced rather than
    silently dropped.
  - `src/download-artifact.ts` (SHA-256
    `665dccdfa36cc93c7d75515fd93a9f97b8dee937b9b5517a15ba77d2a48f6934`) selects
    the resolved `path:` directly whenever exactly one artifact is downloaded
    (`isSingleArtifactDownload || inputs.mergeMultiple || artifacts.length === 1`),
    so a single-`artifact-ids` download extracts flat into `path:`, not into a
    per-artifact subdirectory.
- `actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` (v7.0.0),
  `action.yml` SHA-256
  `c5979822866a72362e609844b6ebe77d4b7e759af68cc1c2c425dcf51481fab4`:
  - Declares the `artifact-digest` output, and `src/shared/upload-artifact.ts`
    (SHA-256 `bfab1f3c0e5ada3dd46e64addb583730dd84e17a47f06e24f9bda3cd50b9153b`)
    sets it to the artifact toolkit's bare-hex SHA-256 digest — no `sha256:`
    prefix — matching the workflow's `[0-9a-f]{64}` fullmatch. Independently
    verified against the action source during review (2026-08) and re-verified
    2026-08-18.

Verified 2026-08-18 by fetching `action.yml` and the named source files at the
exact pinned commits from `github.com` and hashing them with `sha256sum`.

GitHub build/source attestations establish the GitHub workflow and source identity
for the local subjects. They are distinct from the PEP 740 attestations that the
PyPA publishing action generates and sends to PyPI during trusted publication.
PyPI Integrity API inspection of the publish attestation is optional
defense-in-depth when that API is available and reliable. It is not a substitute
for any MUST check above, and this workflow does not claim or require the PyPI
attestation to expose the same GitHub run or attempt as a PyPI-enforced property.

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
   approve the protected `pypi` environment for `prepare-pypi` if every value
   matches the candidate. Each job that references an environment is separately
   protected. An `EXACT_COMPLETE` recovery needs only the prepare approval because
   the publisher skips. An `ABSENT` path normally asks for a second `pypi` approval
   when `publish-pypi` becomes pending; approve it only after reviewing the fresh
   `ABSENT` summary. Never approve a publisher job directly as a recovery shortcut.

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

### PyPI recovery runbook

The following decisions are **MUST** requirements. A normal PyPI recovery never
rebuilds, never runs **Re-run all jobs**, never directly reruns `publish-pypi`, and
never recreates, moves, or deletes the tag or GitHub Release. GitHub's job-rerun API
reruns the selected job and its dependent jobs while retaining the original event
SHA/ref. Select `prepare-pypi` so classification is fresh and its dependent
publisher/verifier jobs follow the state machine:

```bash
run_id=<original-release-workflow-run-id>
prepare_job_id=$(gh run view "$run_id" --repo joyfulhouse/pylxpweb \
  --json jobs --jq '.jobs[] | select(.name == "Classify, verify, and conditionally stage for PyPI") | .databaseId')
test -n "$prepare_job_id"
gh run rerun --repo joyfulhouse/pylxpweb --job "$prepare_job_id"
```

- **Failure before upload / clean absence:** MUST rerun `prepare-pypi` and its
  dependents as above. After protected-environment approval, two clean absence
  snapshots permit one full-set publisher attempt. A verifier result of `ABSENT`
  means the attempt did not complete; use the same recovery invocation, not the
  publisher job.
- **Lost publisher response / exact complete:** MUST use the same recovery
  invocation. Fresh `EXACT_COMPLETE` classification skips the publisher and the
  terminal verifier completes from the sealed artifact and exact remote bytes.
- **Partial publication:** MUST preserve the run summaries and package-index
  evidence, treat the version as burned, and prepare a new version through the
  normal reviewed release process. Never upload the missing file as a top-up.
- **Mismatch, yanked, extra, or competing publication:** MUST stop publication,
  preserve all evidence, and begin the compromise assessment below before creating
  a new reviewed version. Do not normalize, delete, or overwrite remote evidence.
- **Uncertain evidence:** MUST NOT approve or publish. Retry only `prepare-pypi`
  and its dependent verifier/classifier path after the transient condition is
  understood. Repeated uncertainty is not evidence of absence.
- **Missing, expired, duplicated, or unverifiable sealed artifact/attestation:**
  MUST treat the run as `UNCERTAIN`; never rebuild under the same version. If the
  original 30-day artifact cannot be recovered, prepare a new version through the
  normal release process.
- **Compromise or revocation:** MUST follow the response steps below, including
  canceling pending approvals and disabling trusted-publisher authority before any
  new release. Normal recovery does not authorize tag/Release cleanup.

An operator **MAY** additionally inspect PyPI's Integrity API publish attestation
for the expected repository, `release.yml`, tag, and `pypi` environment identity
when the API is available and its fixture contract has been revalidated. This is a
SHOULD defense-in-depth check, not a completion condition. Do not infer a mandatory
same-run or same-attempt binding that PyPI does not enforce and expose reliably.

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
