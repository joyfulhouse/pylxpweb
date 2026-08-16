"""Executable and structural contract tests for the package release workflow."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

import pytest
import yaml

_WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml"
_WORKFLOWS_PATH = _WORKFLOW_PATH.parent
_WORKFLOW_DOCS_PATH = Path(__file__).resolve().parents[2] / ".github" / "WORKFLOWS.md"
_FULL_SHA_ACTION = re.compile(r"^[^\s@]+@[0-9a-f]{40}$")
_PACKAGE_INDEX_PUBLISHER = re.compile(
    r"pypa/gh-action-pypi-publish@|"
    r"https://(?:(?:test|upload)\.)?pypi\.org/legacy/|"
    r"\b(?:twine\s+upload|(?:uv|poetry|hatch|flit|pdm)\s+publish)\b",
    re.IGNORECASE,
)
_WHEEL_NAME = "pylxpweb-1.2.3-py3-none-any.whl"
_SDIST_NAME = "pylxpweb-1.2.3.tar.gz"
_DISTRIBUTIONS = {_WHEEL_NAME: b"wheel bytes", _SDIST_NAME: b"sdist bytes"}
_DISTRIBUTION_HASHES = {
    name: hashlib.sha256(content).hexdigest() for name, content in _DISTRIBUTIONS.items()
}


def _workflow() -> dict[str, Any]:
    workflow: dict[str, Any] = yaml.safe_load(_WORKFLOW_PATH.read_text())
    # PyYAML follows YAML 1.1 and resolves the unquoted key ``on`` as True.
    if True in workflow:
        workflow["on"] = workflow.pop(True)
    return workflow


def _job(workflow: dict[str, Any], job_id: str) -> dict[str, Any]:
    job: dict[str, Any] = workflow["jobs"][job_id]
    return job


def _steps_by_id(job: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {step["id"]: step for step in job["steps"] if "id" in step}


def _action_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for job in workflow["jobs"].values() for step in job["steps"] if "uses" in step]


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def _package_index_publisher_workflows(workflows_path: Path) -> set[str]:
    publishers = set()
    for path in sorted([*workflows_path.glob("*.yml"), *workflows_path.glob("*.yaml")]):
        document = yaml.safe_load(path.read_text())
        if any(_PACKAGE_INDEX_PUBLISHER.search(text) for text in _strings(document)):
            publishers.add(path.name)
    return publishers


def _step(workflow: dict[str, Any], job_id: str, step_id: str) -> dict[str, Any]:
    return _steps_by_id(_job(workflow, job_id))[step_id]


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _commit(repo: Path, message: str, version: str, marker: str) -> str:
    repo.joinpath("pyproject.toml").write_text(
        f'[project]\nname = "pylxpweb"\nversion = "{version}"\n'
    )
    repo.joinpath("source.txt").write_text(marker)
    subprocess.run(["git", "add", "pyproject.toml", "source.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=repo, check=True)
    return _git(repo, "rev-parse", "HEAD")


def _release_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Release Test"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "release-test@example.com"], cwd=repo, check=True
    )
    parent = _commit(repo, "parent", "1.2.2", "parent")
    commit = _commit(repo, "release", "1.2.3", "release")
    subprocess.run(["git", "tag", "-a", "v1.2.3", "-m", "release"], cwd=repo, check=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", commit], cwd=repo, check=True)
    subprocess.run(["git", "checkout", "-q", "--detach", "v1.2.3"], cwd=repo, check=True)
    subprocess.run(["git", "branch", "-D", "main"], cwd=repo, check=True)
    return repo, parent, commit


def _run_resolve_source(
    repo: Path,
    *,
    commit: str,
    event_name: str = "release",
    event_sha: str | None = None,
    release_tag: str = "v1.2.3",
    release_target: str = "main",
    dispatch_tag: str = "v1.2.3",
) -> subprocess.CompletedProcess[str]:
    output = repo / "github-output"
    output.unlink(missing_ok=True)
    env = os.environ | {
        "DISPATCH_TAG": dispatch_tag,
        "EVENT_NAME": event_name,
        "EVENT_SHA": event_sha or commit,
        "GITHUB_OUTPUT": str(output),
        "RELEASE_DRAFT": "false",
        "RELEASE_ID": "291",
        "RELEASE_TAG": release_tag,
        "RELEASE_TARGET": release_target,
        "RELEASE_URL": "https://github.test/releases/291",
    }
    return subprocess.run(
        ["bash", "-c", _step(_workflow(), "build", "resolve-source")["run"]],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _python_heredoc(job_id: str, step_id: str) -> str:
    script: str = _step(_workflow(), job_id, step_id)["run"]
    match = re.fullmatch(r"python3 - <<'PY'\n(?P<code>.*)\nPY\n?", script, re.DOTALL)
    assert match is not None, step_id
    return match.group("code")


def _execute_python_heredoc(job_id: str, step_id: str) -> None:
    namespace: dict[str, Any] = {"__builtins__": __builtins__}
    exec(
        compile(_python_heredoc(job_id, step_id), step_id, "exec"),
        namespace,
        namespace,
    )


class _Response(io.BytesIO):
    def __init__(self, content: bytes, url: str) -> None:
        super().__init__(content)
        self._url = url

    def geturl(self) -> str:
        return self._url


def _index_payload(
    filenames: list[str] | tuple[str, ...],
    *,
    file_host: str | None = None,
) -> dict[str, Any]:
    releases = []
    for filename in filenames:
        release = {
            "filename": filename,
            "yanked": False,
            "digests": {"sha256": _DISTRIBUTION_HASHES.get(filename, "0" * 64)},
        }
        if file_host is not None:
            release["url"] = f"https://{file_host}/{filename}"
        releases.append(release)
    return {"info": {"name": "pylxpweb", "version": "1.2.3"}, "urls": releases}


def _write_release_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "release-bundle"
    dist = bundle / "dist"
    dist.mkdir(parents=True)
    for filename, content in _DISTRIBUTIONS.items():
        dist.joinpath(filename).write_bytes(content)
    bundle.joinpath("SHA256SUMS").write_text(
        "\n".join(
            [
                f"{'0' * 64}  release-source.json",
                *(f"{_DISTRIBUTION_HASHES[name]}  dist/{name}" for name in sorted(_DISTRIBUTIONS)),
            ]
        )
        + "\n"
    )


def _run_testpypi_verifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload: dict[str, Any],
    downloads: dict[str, bytes],
) -> None:
    _write_release_bundle(tmp_path)
    output = tmp_path / "github-output"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ALLOWED_DISTRIBUTION_HOST", "files.test")
    monkeypatch.setenv("EXPECTED_PROJECT_NAME", "pylxpweb")
    monkeypatch.setenv("EXPECTED_VERSION", "1.2.3")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("MAX_ATTEMPTS", "1")
    monkeypatch.setenv("TESTPYPI_JSON_BASE_URL", "https://index.test/pypi")

    def urlopen(request: Any, timeout: int) -> _Response:
        del timeout
        url = request.full_url
        if url == "https://index.test/pypi/pylxpweb/1.2.3/json":
            return _Response(json.dumps(payload).encode(), url)
        filename = Path(url).name
        return _Response(downloads[filename], url)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    _execute_python_heredoc("verify-testpypi", "query-testpypi")


def test_testpypi_verifier_downloads_and_hashes_both_distributions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remote verification covers the wheel and sdist while exporting the wheel."""
    _run_testpypi_verifier(
        tmp_path,
        monkeypatch,
        payload=_index_payload(tuple(_DISTRIBUTIONS), file_host="files.test"),
        downloads=_DISTRIBUTIONS,
    )

    verified = tmp_path / "verified-distributions"
    assert verified.joinpath(_WHEEL_NAME).read_bytes() == _DISTRIBUTIONS[_WHEEL_NAME]
    assert verified.joinpath(_SDIST_NAME).read_bytes() == _DISTRIBUTIONS[_SDIST_NAME]
    assert (tmp_path / "github-output").read_text() == (
        f"wheel-path=verified-distributions/{_WHEEL_NAME}\n"
    )


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("wrong-project", "package index project name does not match"),
        ("wrong-version", "package index version does not match"),
        ("wrong-host", "distribution URL is not allowlisted HTTPS"),
        ("wrong-index-hash", "package index hash does not match"),
        ("wrong-download-hash", "downloaded distribution hash does not match"),
        ("yanked", "package index contains yanked file"),
        ("unexpected", "package index file set does not match"),
        ("missing", "package index file set does not match"),
    ],
)
def test_testpypi_verifier_rejects_untrusted_remote_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    expected_error: str,
) -> None:
    """Index metadata, hosts, file sets, and downloaded bytes fail closed."""
    downloads = _DISTRIBUTIONS.copy()
    payload = _index_payload(tuple(_DISTRIBUTIONS), file_host="files.test")
    if case == "wrong-project":
        payload["info"]["name"] = "other"
    elif case == "wrong-version":
        payload["info"]["version"] = "9.9.9"
    elif case == "wrong-host":
        payload["urls"][1]["url"] = f"https://evil.test/{_SDIST_NAME}"
    elif case == "wrong-index-hash":
        payload["urls"][1]["digests"]["sha256"] = "0" * 64
    elif case == "wrong-download-hash":
        downloads[_SDIST_NAME] = b"different"
    elif case == "yanked":
        payload["urls"][1]["yanked"] = True
    elif case == "unexpected":
        payload["urls"].append(
            {
                "filename": "unexpected.whl",
                "url": "https://files.test/unexpected.whl",
                "yanked": False,
                "digests": {"sha256": "0" * 64},
            }
        )
    elif case == "missing":
        payload["urls"].pop()

    with pytest.raises(AssertionError, match=expected_error):
        _run_testpypi_verifier(
            tmp_path,
            monkeypatch,
            payload=payload,
            downloads=downloads,
        )


def _run_pypi_state_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    step_id: str,
    mode: str,
    responses: list[dict[str, Any] | Exception | None],
) -> tuple[set[str], str, int]:
    _write_release_bundle(tmp_path)
    output = tmp_path / "github-output"
    upload = tmp_path / "pypi-upload"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXPECTED_PROJECT_NAME", "pylxpweb")
    monkeypatch.setenv("EXPECTED_VERSION", "1.2.3")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    step_env = _step(_workflow(), "publish-pypi", step_id)["env"]
    monkeypatch.setenv("MAX_ATTEMPTS", step_env["MAX_ATTEMPTS"])
    for name in ("BACKOFF_SECONDS", "MAX_BACKOFF_SECONDS", "REQUEST_TIMEOUT_SECONDS"):
        if name in step_env:
            monkeypatch.setenv(name, step_env[name])
    monkeypatch.setenv("MODE", mode)
    monkeypatch.setenv("PYPI_JSON_BASE_URL", "https://index.test/pypi")
    monkeypatch.setenv("UPLOAD_DIR", str(upload))
    monkeypatch.setattr("time.sleep", lambda _: None)
    pending = list(responses)
    calls = 0

    def urlopen(request: Any, timeout: int) -> _Response:
        nonlocal calls
        del timeout
        calls += 1
        payload = pending.pop(0) if pending else responses[-1]
        if isinstance(payload, Exception):
            raise payload
        if payload is None:
            raise HTTPError(request.full_url, 404, "Not Found", {}, None)
        return _Response(json.dumps(payload).encode(), request.full_url)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    _execute_python_heredoc("publish-pypi", step_id)
    staged = {path.name for path in upload.iterdir()} if upload.exists() else set()
    return staged, output.read_text() if output.exists() else "", calls


@pytest.mark.parametrize("existing_count", [0, 1, 2])
def test_pypi_preflight_stages_only_absent_distributions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing_count: int
) -> None:
    """A retry publishes none, one, or both files without production skipping."""
    filenames = list(_DISTRIBUTIONS)
    payload = None if existing_count == 0 else _index_payload(filenames[:existing_count])

    staged, output, calls = _run_pypi_state_step(
        tmp_path,
        monkeypatch,
        step_id="prepare-pypi",
        mode="prepare",
        responses=[payload],
    )

    assert staged == set(filenames[existing_count:])
    assert output == f"upload-needed={'true' if staged else 'false'}\n"
    assert calls == 1


def test_pypi_preflight_retries_transient_failure_then_accepts_absent_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient index failure is retried before a genuine 404 is accepted."""
    staged, output, calls = _run_pypi_state_step(
        tmp_path,
        monkeypatch,
        step_id="prepare-pypi",
        mode="prepare",
        responses=[URLError("temporary failure"), None],
    )

    assert staged == set(_DISTRIBUTIONS)
    assert output == "upload-needed=true\n"
    assert calls == 2


def test_pypi_preflight_exhausts_bounded_transient_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preflight fails closed after its small retry allowance is exhausted."""
    with pytest.raises(URLError, match="third failure"):
        _run_pypi_state_step(
            tmp_path,
            monkeypatch,
            step_id="prepare-pypi",
            mode="prepare",
            responses=[
                URLError("first failure"),
                URLError("second failure"),
                URLError("third failure"),
            ],
        )


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("wrong-hash", "PyPI hash does not match"),
        ("unexpected", "PyPI contains unexpected file"),
        ("yanked", "PyPI contains yanked file"),
    ],
)
def test_pypi_preflight_rejects_untrusted_existing_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    expected_error: str,
) -> None:
    """Existing production files are accepted only as an exact trusted subset."""
    payload = _index_payload([_WHEEL_NAME])
    if case == "wrong-hash":
        payload["urls"][0]["digests"]["sha256"] = "0" * 64
    elif case == "unexpected":
        payload["urls"].append(
            {
                "filename": "unexpected.whl",
                "yanked": False,
                "digests": {"sha256": "0" * 64},
            }
        )
    elif case == "yanked":
        payload["urls"][0]["yanked"] = True

    with pytest.raises(AssertionError, match=expected_error):
        _run_pypi_state_step(
            tmp_path,
            monkeypatch,
            step_id="prepare-pypi",
            mode="prepare",
            responses=[payload],
        )


def test_pypi_final_verification_retries_until_exact_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Index propagation is bounded and must converge to the exact file set."""
    filenames = list(_DISTRIBUTIONS)

    staged, output, calls = _run_pypi_state_step(
        tmp_path,
        monkeypatch,
        step_id="verify-pypi",
        mode="verify",
        responses=[
            _index_payload(filenames[:1]),
            _index_payload(filenames),
        ],
    )

    assert staged == set()
    assert output == ""
    assert calls == 2


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("missing", "PyPI final file set does not match"),
        ("wrong-hash", "PyPI hash does not match"),
        ("unexpected", "PyPI contains unexpected file"),
        ("yanked", "PyPI contains yanked file"),
    ],
)
def test_pypi_final_verification_rejects_untrusted_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    expected_error: str,
) -> None:
    """Post-publication verification fails closed on every non-exact state."""
    payload = _index_payload(list(_DISTRIBUTIONS))
    if case == "missing":
        payload["urls"].pop()
    elif case == "wrong-hash":
        payload["urls"][1]["digests"]["sha256"] = "0" * 64
    elif case == "unexpected":
        payload["urls"].append(
            {
                "filename": "unexpected.whl",
                "yanked": False,
                "digests": {"sha256": "0" * 64},
            }
        )
    elif case == "yanked":
        payload["urls"][1]["yanked"] = True

    with pytest.raises(AssertionError, match=expected_error):
        _run_pypi_state_step(
            tmp_path,
            monkeypatch,
            step_id="verify-pypi",
            mode="verify",
            responses=[payload],
        )


def test_resolve_source_accepts_remote_branch_release_target(tmp_path: Path) -> None:
    """A detached release checkout resolves a branch target through origin."""
    repo, _, commit = _release_repo(tmp_path)

    result = _run_resolve_source(repo, commit=commit)

    assert result.returncode == 0, result.stderr
    assert (
        subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", "refs/heads/main"], cwd=repo
        ).returncode
        != 0
    )
    assert _git(repo, "rev-parse", "refs/remotes/origin/main") == commit


def test_resolve_source_accepts_full_commit_release_target(tmp_path: Path) -> None:
    """GitHub may supply the complete target commit instead of a branch name."""
    repo, _, commit = _release_repo(tmp_path)

    result = _run_resolve_source(repo, commit=commit, release_target=commit)

    assert result.returncode == 0, result.stderr


def test_resolve_source_accepts_dispatch_and_rejects_other_events(tmp_path: Path) -> None:
    """Manual validation is supported, but no other event may enter the build path."""
    repo, parent, commit = _release_repo(tmp_path)

    dispatch = _run_resolve_source(
        repo,
        commit=commit,
        event_name="workflow_dispatch",
        event_sha=parent,
        release_tag="",
        release_target="--ignored",
    )
    unsupported = _run_resolve_source(repo, commit=commit, event_name="push")

    assert dispatch.returncode == 0, dispatch.stderr
    assert unsupported.returncode != 0
    assert "unsupported release workflow event" in unsupported.stderr


@pytest.mark.parametrize("target", ["main~1", "--help", "deadbeef", "missing"])
def test_resolve_source_rejects_ambiguous_or_malformed_target(tmp_path: Path, target: str) -> None:
    """Only a full commit or an exact remote branch name is a valid target."""
    repo, _, commit = _release_repo(tmp_path)

    result = _run_resolve_source(repo, commit=commit, release_target=target)

    assert result.returncode != 0
    assert "invalid or unresolved release target" in result.stderr


@pytest.mark.parametrize("target_kind", ["branch", "commit"])
def test_resolve_source_rejects_target_before_release(tmp_path: Path, target_kind: str) -> None:
    """The release tag must be contained by either supported target form."""
    repo, parent, commit = _release_repo(tmp_path)
    target = parent
    if target_kind == "branch":
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/stable", parent],
            cwd=repo,
            check=True,
        )
        target = "stable"

    result = _run_resolve_source(repo, commit=commit, release_target=target)

    assert result.returncode != 0
    assert "release tag is not an ancestor of release target" in result.stderr


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("event", "release event commit does not match tag commit"),
        ("tag-version", "release tag does not match project version"),
        ("main-ancestry", "release tag is not an ancestor of origin/main"),
    ],
)
def test_resolve_source_rejects_identity_mismatch(
    tmp_path: Path, mutation: str, expected_error: str
) -> None:
    """Event, tag, version, checkout tree, and main ancestry remain bound."""
    repo, parent, commit = _release_repo(tmp_path)
    kwargs: dict[str, str] = {}
    if mutation == "event":
        kwargs["event_sha"] = parent
    elif mutation == "tag-version":
        subprocess.run(["git", "tag", "-a", "v1.2.4", "-m", "wrong"], cwd=repo, check=True)
        kwargs["release_tag"] = "v1.2.4"
    elif mutation == "main-ancestry":
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/main", parent], cwd=repo, check=True
        )

    result = _run_resolve_source(repo, commit=commit, **kwargs)

    assert result.returncode != 0
    assert expected_error in result.stderr


def test_release_bundle_validator_rejects_tree_mismatch(tmp_path: Path) -> None:
    """Artifact promotion rebinds the machine-readable source tree."""
    bundle = tmp_path / "release-bundle"
    dist = bundle / "dist"
    dist.mkdir(parents=True)
    wheel = dist / "pylxpweb-1.2.3-py3-none-any.whl"
    sdist = dist / "pylxpweb-1.2.3.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    source = {
        "artifact_name": "pylxpweb-release-1.2.3-0123456789ab",
        "commit": "0123456789abcdef0123456789abcdef01234567",
        "project_name": "pylxpweb",
        "tag": "v1.2.3",
        "tree": "1111111111111111111111111111111111111111",
        "version": "1.2.3",
    }
    bundle.joinpath("release-source.json").write_text(json.dumps(source))
    hashed = [bundle / "release-source.json", wheel, sdist]
    bundle.joinpath("SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
            f"{path.relative_to(bundle).as_posix()}\n"
            for path in hashed
        )
    )
    env = os.environ | {
        "EXPECTED_ARTIFACT_NAME": source["artifact_name"],
        "EXPECTED_COMMIT": source["commit"],
        "EXPECTED_PROJECT_NAME": source["project_name"],
        "EXPECTED_TAG": source["tag"],
        "EXPECTED_TREE": "2222222222222222222222222222222222222222",
        "EXPECTED_VERSION": source["version"],
    }

    result = subprocess.run(
        ["bash", "-c", _step(_workflow(), "build", "validate-release-bundle")["run"]],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "release source identity does not match" in result.stderr


def test_release_triggers_are_published_release_or_main_only_manual_build() -> None:
    """A tag push or manual publisher path must not bypass a published release."""
    workflow = _workflow()
    triggers = workflow["on"]

    assert set(triggers) == {"release", "workflow_dispatch"}
    assert triggers["release"] == {"types": ["published"]}
    assert triggers["workflow_dispatch"]["inputs"] == {
        "tag": {
            "description": "Existing v* tag to validate",
            "required": True,
            "type": "string",
        }
    }
    assert _job(workflow, "build")["if"] == (
        "github.event_name == 'release' || github.ref == 'refs/heads/main'"
    )
    for job_id in ("publish-testpypi", "verify-testpypi", "publish-pypi"):
        assert _job(workflow, job_id)["if"] == "github.event_name == 'release'"


def test_oidc_is_confined_to_publisher_jobs() -> None:
    """Compromising build or verification must not yield an OIDC token."""
    workflow = _workflow()

    assert workflow["permissions"] == {"contents": "read"}
    for job_id, job in workflow["jobs"].items():
        permissions = job.get("permissions", {})
        if job_id in {"publish-testpypi", "publish-pypi"}:
            assert permissions == {"contents": "read", "id-token": "write"}
        else:
            assert "id-token" not in permissions


def test_release_jobs_form_a_verified_promotion_chain() -> None:
    """Production publication must depend on independent TestPyPI verification."""
    workflow = _workflow()

    assert set(workflow["jobs"]) == {
        "build",
        "publish-testpypi",
        "verify-testpypi",
        "publish-pypi",
    }
    assert _job(workflow, "publish-testpypi")["needs"] == "build"
    assert _job(workflow, "verify-testpypi")["needs"] == ["build", "publish-testpypi"]
    assert _job(workflow, "publish-pypi")["needs"] == ["build", "verify-testpypi"]
    assert _job(workflow, "publish-testpypi")["environment"] == "testpypi"
    assert "environment" not in _job(workflow, "verify-testpypi")
    assert _job(workflow, "publish-pypi")["environment"] == "pypi"


def test_build_exports_bound_source_and_artifact_identity() -> None:
    """Every downstream check must consume identity resolved once by build."""
    workflow = _workflow()
    build = _job(workflow, "build")
    source = _steps_by_id(build)["resolve-source"]

    assert build["outputs"] == {
        key: f"${{{{ steps.resolve-source.outputs.{key} }}}}"
        for key in ("artifact-name", "commit", "project-name", "tag", "tree", "version")
    }
    assert source["env"] == {
        "DISPATCH_TAG": "${{ inputs.tag }}",
        "EVENT_NAME": "${{ github.event_name }}",
        "EVENT_SHA": "${{ github.sha }}",
        "RELEASE_DRAFT": "${{ github.event.release.draft }}",
        "RELEASE_ID": "${{ github.event.release.id }}",
        "RELEASE_TAG": "${{ github.event.release.tag_name }}",
        "RELEASE_TARGET": "${{ github.event.release.target_commitish }}",
        "RELEASE_URL": "${{ github.event.release.html_url }}",
    }


def test_build_uploads_one_complete_retained_release_artifact() -> None:
    """Promotion must use one named bundle containing both distributions and manifests."""
    workflow = _workflow()
    build = _job(workflow, "build")
    steps = _steps_by_id(build)
    expected_order = [
        "resolve-source",
        "build-distributions",
        "check-distributions",
        "validate-distributions",
        "write-source-manifest",
        "write-sha256-manifest",
        "validate-release-bundle",
        "upload-release-artifact",
    ]

    positions = {step_id: index for index, step_id in enumerate(steps)}
    assert positions.keys() >= set(expected_order)
    assert [positions[step_id] for step_id in expected_order] == sorted(
        positions[step_id] for step_id in expected_order
    )
    uploads = [
        step
        for step in _action_steps(workflow)
        if step["uses"].startswith("actions/upload-artifact@")
    ]
    assert uploads == [steps["upload-release-artifact"]]
    assert uploads[0]["with"] == {
        "name": "${{ steps.resolve-source.outputs.artifact-name }}",
        "path": "release-bundle/",
        "if-no-files-found": "error",
        "retention-days": 30,
    }


def test_build_uses_locked_tools_without_mutating_bound_source() -> None:
    """Dependency setup must not change source after its commit and tree are bound."""
    build = _job(_workflow(), "build")
    steps = _steps_by_id(build)

    assert build["env"] == {"UV_PYTHON": "3.13"}
    assert steps["sync-build-tools"]["env"] == {"UV_LOCKED": "1"}
    step_ids = list(steps)
    assert step_ids.index("sync-build-tools") < step_ids.index("verify-clean-source")
    assert step_ids.index("verify-clean-source") < step_ids.index("build-distributions")


def test_every_promotion_downloads_and_revalidates_the_original_artifact() -> None:
    """Publisher and verifier jobs must never rebuild or select a different bundle."""
    workflow = _workflow()

    for job_id in ("publish-testpypi", "verify-testpypi", "publish-pypi"):
        job = _job(workflow, job_id)
        steps = _steps_by_id(job)
        assert steps["download-release-artifact"]["with"] == {
            "name": "${{ needs.build.outputs.artifact-name }}",
            "path": "release-bundle/",
        }
        assert steps["revalidate-release-bundle"]["env"] == {
            "EXPECTED_ARTIFACT_NAME": "${{ needs.build.outputs.artifact-name }}",
            "EXPECTED_COMMIT": "${{ needs.build.outputs.commit }}",
            "EXPECTED_PROJECT_NAME": "${{ needs.build.outputs.project-name }}",
            "EXPECTED_TAG": "${{ needs.build.outputs.tag }}",
            "EXPECTED_TREE": "${{ needs.build.outputs.tree }}",
            "EXPECTED_VERSION": "${{ needs.build.outputs.version }}",
        }
        step_ids = list(steps)
        assert step_ids.index("download-release-artifact") < step_ids.index(
            "revalidate-release-bundle"
        )
        assert "build-distributions" not in steps


def test_testpypi_verification_is_unprivileged_bounded_and_ordered() -> None:
    """Verification must prove remote bytes and an isolated production-index install."""
    workflow = _workflow()
    verify = _job(workflow, "verify-testpypi")
    steps = _steps_by_id(verify)
    order = [
        "download-release-artifact",
        "revalidate-release-bundle",
        "query-testpypi",
        "create-verification-environment",
        "install-testpypi-wheel",
        "verify-installed-package",
    ]

    assert verify["permissions"] == {"contents": "read"}
    assert [list(steps).index(step_id) for step_id in order] == sorted(
        list(steps).index(step_id) for step_id in order
    )
    assert steps["query-testpypi"]["env"] == {
        "ALLOWED_DISTRIBUTION_HOST": "test-files.pythonhosted.org",
        "EXPECTED_PROJECT_NAME": "${{ needs.build.outputs.project-name }}",
        "EXPECTED_VERSION": "${{ needs.build.outputs.version }}",
        "MAX_ATTEMPTS": "12",
        "TESTPYPI_JSON_BASE_URL": "https://test.pypi.org/pypi",
    }
    assert steps["create-verification-environment"]["run"] == ("uv venv --python 3.13 .verify-venv")
    assert steps["install-testpypi-wheel"]["env"] == {
        "PYPI_INDEX_URL": "https://pypi.org/simple",
        "WHEEL_PATH": "${{ steps.query-testpypi.outputs.wheel-path }}",
    }
    assert steps["verify-installed-package"]["env"] == {
        "EXPECTED_PROJECT_NAME": "${{ needs.build.outputs.project-name }}",
        "EXPECTED_VERSION": "${{ needs.build.outputs.version }}",
    }


def test_publishers_use_trusted_publishing_with_skip_only_on_testpypi() -> None:
    """Production stages absent files and verifies the final exact remote set."""
    workflow = _workflow()
    test_publish = _steps_by_id(_job(workflow, "publish-testpypi"))["publish-testpypi"]
    production_steps = _steps_by_id(_job(workflow, "publish-pypi"))
    production_publish = production_steps["publish-pypi"]

    assert test_publish["with"] == {
        "packages-dir": "release-bundle/dist/",
        "repository-url": "https://test.pypi.org/legacy/",
        "skip-existing": True,
    }
    assert production_steps["prepare-pypi"]["env"] == {
        "BACKOFF_SECONDS": "2",
        "EXPECTED_PROJECT_NAME": "${{ needs.build.outputs.project-name }}",
        "EXPECTED_VERSION": "${{ needs.build.outputs.version }}",
        "MAX_ATTEMPTS": "3",
        "MAX_BACKOFF_SECONDS": "5",
        "MODE": "prepare",
        "PYPI_JSON_BASE_URL": "https://pypi.org/pypi",
        "REQUEST_TIMEOUT_SECONDS": "10",
        "UPLOAD_DIR": "pypi-upload",
    }
    assert production_publish["if"] == (
        "success() && steps.prepare-pypi.outputs.upload-needed == 'true'"
    )
    assert production_publish["with"] == {"packages-dir": "pypi-upload/"}
    assert "skip-existing" not in production_publish["with"]
    assert production_steps["verify-pypi"]["env"] == {
        "BACKOFF_SECONDS": "5",
        "EXPECTED_PROJECT_NAME": "${{ needs.build.outputs.project-name }}",
        "EXPECTED_VERSION": "${{ needs.build.outputs.version }}",
        "MAX_ATTEMPTS": "8",
        "MAX_BACKOFF_SECONDS": "20",
        "MODE": "verify",
        "PYPI_JSON_BASE_URL": "https://pypi.org/pypi",
        "REQUEST_TIMEOUT_SECONDS": "15",
        "UPLOAD_DIR": "pypi-upload",
    }
    order = [
        "download-release-artifact",
        "revalidate-release-bundle",
        "prepare-pypi",
        "publish-pypi",
        "verify-pypi",
    ]
    assert [list(production_steps).index(step_id) for step_id in order] == sorted(
        list(production_steps).index(step_id) for step_id in order
    )


def test_pypi_final_retry_budget_leaves_five_minutes_for_setup_and_upload() -> None:
    """Worst-case request and backoff time must fit with meaningful job headroom."""
    job = _job(_workflow(), "publish-pypi")
    env = _step(_workflow(), "publish-pypi", "verify-pypi")["env"]
    attempts = int(env["MAX_ATTEMPTS"])
    request_timeout = int(env["REQUEST_TIMEOUT_SECONDS"])
    backoff = int(env["BACKOFF_SECONDS"])
    backoff_cap = int(env["MAX_BACKOFF_SECONDS"])
    request_budget = attempts * request_timeout
    backoff_budget = sum(min(backoff * attempt, backoff_cap) for attempt in range(1, attempts))

    assert attempts >= 2
    assert request_budget + backoff_budget <= job["timeout-minutes"] * 60 - 5 * 60


def test_release_is_the_only_package_index_publisher_workflow() -> None:
    """No release or tag workflow may compete with the package promotion chain."""
    assert _package_index_publisher_workflows(_WORKFLOWS_PATH) == {"release.yml"}


def test_package_index_workflow_audit_detects_a_competing_publisher(tmp_path: Path) -> None:
    """The repository audit recognizes a publisher action outside release.yml."""
    tmp_path.joinpath("build-executables.yml").write_text(
        "jobs:\n  build:\n    steps:\n      - uses: pypa/gh-action-pypi-publish@" + "a" * 40 + "\n"
    )

    assert _package_index_publisher_workflows(tmp_path) == {"build-executables.yml"}


@pytest.mark.parametrize(
    "command",
    ["poetry publish", "hatch publish", "flit publish", "pdm publish"],
)
def test_package_index_workflow_audit_detects_known_publish_commands(
    tmp_path: Path, command: str
) -> None:
    """The audit recognizes established Python package publisher commands."""
    tmp_path.joinpath("competing.yml").write_text(
        f"jobs:\n  publish:\n    steps:\n      - run: {command}\n"
    )

    assert _package_index_publisher_workflows(tmp_path) == {"competing.yml"}


def test_workflow_docs_define_compromise_response_and_keep_settings_gate() -> None:
    """Recovery guidance must stop publishing and preserve the post-merge gate."""
    docs = _WORKFLOW_DOCS_PATH.read_text()
    normalized_docs = " ".join(docs.split())

    for phrase in (
        "Cancel active release workflow runs and pending environment approvals",
        "Disable the `pypi` and `testpypi` environments",
        "remove the corresponding trusted-publisher bindings",
        "Audit the compromised GitHub identity",
        "revoke its sessions, tokens, and keys",
        "Restore environments and trusted-publisher bindings only after recovery",
        "These are post-merge settings gates",
        "do not apply or mutate repository, environment, or package-index settings",
        "No long-lived package-index credential is introduced",
    ):
        assert phrase in normalized_docs


def test_all_actions_are_immutable_full_sha_pins() -> None:
    """A mutable action tag must not change executable release code after review."""
    workflow = _workflow()
    pins: dict[str, set[str]] = {}

    for step in _action_steps(workflow):
        assert _FULL_SHA_ACTION.fullmatch(step["uses"]), step["uses"]
        action, pin = step["uses"].split("@", 1)
        pins.setdefault(action, set()).add(pin)
    assert pins == {
        "actions/checkout": {"3d3c42e5aac5ba805825da76410c181273ba90b1"},
        "actions/download-artifact": {"3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"},
        "actions/upload-artifact": {"043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"},
        "astral-sh/setup-uv": {"37802adc94f370d6bfd71619e3f0bf239e1f3b78"},
        "pypa/gh-action-pypi-publish": {"dc37677b2e1c63e2034f94d8a5b11f265b73ba33"},
    }


def test_release_job_conditions_fail_closed_without_always() -> None:
    """Failed identity, publication, or verification checks must stop promotion."""
    workflow = _workflow()

    assert {job_id: job.get("if") for job_id, job in workflow["jobs"].items()} == {
        "build": "github.event_name == 'release' || github.ref == 'refs/heads/main'",
        "publish-testpypi": "github.event_name == 'release'",
        "verify-testpypi": "github.event_name == 'release'",
        "publish-pypi": "github.event_name == 'release'",
    }
    assert "always()" not in _WORKFLOW_PATH.read_text()
    for job in workflow["jobs"].values():
        assert job.get("if") != "always()"
