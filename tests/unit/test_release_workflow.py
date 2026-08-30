"""Production-shaped contract tests for the package release workflow."""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from typing import IO, Any

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_PATH = _ROOT / ".github" / "workflows" / "release.yml"
_WORKFLOWS_PATH = _WORKFLOW_PATH.parent
_FULL_SHA_ACTION = re.compile(r"^[^\s@]+@[0-9a-f]{40}$")
_TEST_WORKFLOW_REF = "joyfulhouse/pylxpweb/.github/workflows/release.yml@refs/tags/v1.2.3"
_PACKAGE_INDEX_PUBLISHER = re.compile(
    r"pypa/gh-action-pypi-publish@|"
    r"https://(?:(?:test|upload)\.)?pypi\.org/legacy/|"
    r"\b(?:twine\s+upload|(?:uv|poetry|hatch|flit|pdm)\s+publish)\b",
    re.IGNORECASE,
)
_BINDING_TIMEOUT_SECONDS = 15.0
_SUBPROCESS_WALL_MULTIPLIER = 20.0
_SUBPROCESS_TAIL_BYTES = 1 << 20
_SUBPROCESS_READER_JOIN_SECONDS = 2.0
# The terminator must be a whole ``PY`` line: without the lookahead a body line
# merely *starting* with ``PY`` would silently truncate the materialized script.
_PYTHON_HEREDOC = re.compile(
    r"python3 -(?P<args>[^\n]*(?:\\\n[^\n]*)*) <<'PY'\n(?P<body>.*?)\nPY(?=\n|$)",
    re.DOTALL,
)


@pytest.fixture
def package_index_server() -> Iterator[tuple[str, dict[str, Any]]]:
    """Serve mutable package-index responses for the exact workflow scripts."""
    state: dict[str, Any] = {
        "files": {},
        "index_calls": 0,
        "index_responses": [],
        "redirected_files": {},
        "redirected_index": None,
        "request_events": [],
    }

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            if self.path.startswith("/pypi/"):
                state["request_events"].append("index")
                responses = state["index_responses"]
                index = min(state["index_calls"], len(responses) - 1)
                state["index_calls"] += 1
                response = responses[index]
                if isinstance(response, int):
                    self.send_error(response)
                    return
                if isinstance(response, dict) and "redirect" in response:
                    self.send_response(302)
                    self.send_header("Location", response["redirect"])
                    self.end_headers()
                    return
                body = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/files/"):
                state["request_events"].append("file")
                name = self.path.removeprefix("/files/")
                response = state["files"][name]
                if isinstance(response, dict) and "redirect" in response:
                    self.send_response(302)
                    self.send_header("Location", response["redirect"])
                    self.end_headers()
                    return
                if isinstance(response, dict) and "drip" in response:
                    content = response["drip"]
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    try:
                        for byte in content:
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                            time.sleep(response["delay"])
                    except BrokenPipeError:
                        pass
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                return
            if self.path.startswith("/redirected/"):
                name = self.path.removeprefix("/redirected/")
                response = state["redirected_files"][name]
                self.send_response(200)
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                return
            if self.path.startswith("/redirected-index"):
                response = state["redirected_index"]
                if response is None:
                    self.send_error(404)
                    return
                body = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(404)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _workflow() -> dict[str, Any]:
    workflow: dict[str, Any] = yaml.safe_load(_WORKFLOW_PATH.read_text())
    # PyYAML follows YAML 1.1 and resolves the unquoted key ``on`` as True.
    if True in workflow:
        workflow["on"] = workflow.pop(True)
    return workflow


def _job(job_id: str) -> dict[str, Any]:
    job: dict[str, Any] = _workflow()["jobs"][job_id]
    return job


def _step(job_id: str, step_id: str) -> dict[str, Any]:
    return next(step for step in _job(job_id)["steps"] if step.get("id") == step_id)


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


def _index_payload(
    base_url: str,
    files: dict[str, bytes],
) -> dict[str, Any]:
    return {
        "info": {"name": "pylxpweb", "version": "1.2.3"},
        "urls": [
            {
                "digests": {"sha256": hashlib.sha256(content).hexdigest()},
                "filename": name,
                "url": f"{base_url}/files/{name}",
                "yanked": False,
            }
            for name, content in files.items()
        ],
    }


def _prepare_index_case(
    tmp_path: Path, base_url: str, state: dict[str, Any]
) -> tuple[dict[str, bytes], dict[str, Any]]:
    files = {
        "pylxpweb-1.2.3-py3-none-any.whl": b"wheel",
        "pylxpweb-1.2.3.tar.gz": b"sdist",
    }
    bundle = tmp_path / "release-bundle"
    bundle.mkdir(exist_ok=True)
    bundle.joinpath("DIST_SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(content).hexdigest()}  dist/{name}\n"
            for name, content in files.items()
        )
    )
    state["files"] = dict(files)
    return files, _index_payload(base_url, files)


def _run_index_verifier(
    tmp_path: Path,
    base_url: str,
    *,
    job_id: str = "verify-testpypi",
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ | {
        "ALLOWED_FILE_HOST": "127.0.0.1",
        "DOWNLOAD_TOTAL_SECONDS": "2",
        "EXPECTED_PROJECT_NAME": "pylxpweb",
        "EXPECTED_VERSION": "1.2.3",
        "INDEX_TOTAL_SECONDS": "2",
        "INDEX_JSON_BASE": f"{base_url}/pypi",
        "MAX_ATTEMPTS": "3",
        "REQUIRED_FILE_SCHEME": "http",
        "RETRY_BASE_SECONDS": "0",
        "SOCKET_TIMEOUT_SECONDS": "1",
    }
    env.update(env_overrides or {})
    return _run_yaml_script(
        _step(job_id, f"verify-{job_id.removeprefix('verify-')}-files")["run"],
        cwd=tmp_path,
        env=env,
        tmp_path=tmp_path,
        timeout_seconds=15,
    )


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _commit(repo: Path, message: str, marker: str) -> str:
    repo.joinpath("source.txt").write_text(marker)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=repo, check=True)
    return _git(repo, "rev-parse", "HEAD")


def _write_fake_gh(bin_dir: Path) -> None:
    gh = bin_dir / "gh"
    gh.write_text(
        r"""#!/usr/bin/env python3
import json
import os
import pathlib
import sys

if len(sys.argv) >= 2 and sys.argv[1] == "api":
    endpoint = next(arg for arg in sys.argv[2:] if arg.startswith("repos/"))
    fixtures = json.loads(pathlib.Path(os.environ["GH_FIXTURES"]).read_text())
    if endpoint not in fixtures:
        print(f"unexpected endpoint: {endpoint}", file=sys.stderr)
        raise SystemExit(2)
    value = fixtures[endpoint]
    if "--slurp" in sys.argv:
        if isinstance(value, list):
            pages = [value[index : index + 30] for index in range(0, len(value), 30)]
            if "--paginate" not in sys.argv:
                pages = pages[:1]
        else:
            pages = [value]
        print(json.dumps(pages))
    else:
        print(json.dumps(value))
    raise SystemExit(0)

if sys.argv[1:3] == ["attestation", "verify"]:
    if not os.environ.get("GH_TOKEN"):
        print("GH_TOKEN is required", file=sys.stderr)
        raise SystemExit(4)
    subject = sys.argv[3]
    bundle = pathlib.Path(sys.argv[sys.argv.index("--bundle") + 1])
    expected_options = {
        "--repo": os.environ["REPOSITORY"],
        "--signer-workflow": (
            f'{os.environ["REPOSITORY"]}/.github/workflows/release.yml'
        ),
        "--signer-digest": os.environ["EXPECTED_WORKFLOW_SHA"],
        "--source-ref": f'refs/tags/{os.environ["EXPECTED_TAG"]}',
        "--source-digest": os.environ["EXPECTED_COMMIT"],
    }
    for option, expected_value in expected_options.items():
        if option not in sys.argv or sys.argv[sys.argv.index(option) + 1] != expected_value:
            print(f"attestation identity mismatch: {option}", file=sys.stderr)
            raise SystemExit(1)
    source_subject = "release-bundle/release-source.json"
    dist_subjects = {
        f"release-bundle/{line.split('  ', 1)[1]}"
        for line in pathlib.Path("release-bundle/DIST_SHA256SUMS").read_text().splitlines()
    }
    if subject == source_subject:
        expected_bundle = pathlib.Path("release-bundle/attestations/source.jsonl")
    elif subject in dist_subjects:
        expected_bundle = pathlib.Path("release-bundle/attestations/build.jsonl")
    else:
        print(f"unexpected attestation subject: {subject}", file=sys.stderr)
        raise SystemExit(1)
    if bundle != expected_bundle:
        print(f"wrong attestation bundle for {subject}", file=sys.stderr)
        raise SystemExit(1)
    expected = os.environ.get("EXPECTED_ATTESTATION_CONTENT")
    if expected is not None and bundle.read_text() != expected:
        raise SystemExit(1)
    with pathlib.Path(os.environ["GH_CALLS"]).open("a") as calls:
        calls.write(" ".join(sys.argv[1:]) + "\n")
    print("verified")
    raise SystemExit(0)

print("unsupported fake gh invocation", file=sys.stderr)
raise SystemExit(2)
"""
    )
    gh.chmod(0o755)


def _release_repo(
    tmp_path: Path, *, lightweight: bool = False, stale_candidate: bool = False
) -> dict[str, Any]:
    remote = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "config", "user.name", "Release Test"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "release-test@example.com"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "tag.gpgSign", "false"], cwd=repo, check=True)
    subprocess.run(["git", "config", "tag.forceSignAnnotated", "false"], cwd=repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo, check=True)
    repo.joinpath("pyproject.toml").write_text('[project]\nname = "pylxpweb"\nversion = "1.2.3"\n')
    workflow = repo / ".github" / "workflows" / "release.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: Publish to PyPI\n")
    parent = _commit(repo, "parent", "parent")
    subprocess.run(["git", "checkout", "-qb", "release-candidate"], cwd=repo, check=True)
    head = _commit(repo, "release candidate", "release")
    subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True)
    if stale_candidate:
        repo.joinpath("new-main.txt").write_text("newer-main")
        subprocess.run(["git", "add", "new-main.txt"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "newer main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "merge", "-q", "--no-ff", "release-candidate", "-m", "merge candidate"],
        cwd=repo,
        check=True,
    )
    merge = _git(repo, "rev-parse", "HEAD")
    first_parent = _git(repo, "rev-parse", "HEAD^1")
    tag_args = ["git", "-c", "tag.forceSignAnnotated=false", "tag", "v1.2.3"]
    if not lightweight:
        tag_args = ["git", "tag", "-a", "v1.2.3", "-m", "release"]
    subprocess.run(tag_args, cwd=repo, check=True)
    subprocess.run(["git", "push", "-q", "origin", "main", "v1.2.3"], cwd=repo, check=True)
    subprocess.run(["git", "checkout", "-q", "--detach", "v1.2.3"], cwd=repo, check=True)
    # Seed a divergent tracking ref: the production binder must force-replace it.
    subprocess.run(["git", "checkout", "-qb", "stale-ref", parent], cwd=repo, check=True)
    stale = _commit(repo, "divergent stale ref", "stale")
    subprocess.run(["git", "checkout", "-q", "--detach", "v1.2.3"], cwd=repo, check=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", stale], cwd=repo, check=True)
    repository = "joyfulhouse/pylxpweb"
    fixtures: dict[str, Any] = {
        f"repos/{repository}/commits/{merge}/pulls": [
            {
                "number": 17,
                "state": "closed",
                "merged_at": "2026-08-16T12:00:00Z",
                "merge_commit_sha": merge,
                "head": {"sha": head},
                "base": {"ref": "main", "sha": first_parent},
                "user": {"login": "author"},
            }
        ],
        f"repos/{repository}/commits/{head}/check-runs": {
            "check_runs": [
                {
                    "name": "CI Success",
                    "head_sha": head,
                    "conclusion": "success",
                    "details_url": (
                        f"https://github.com/{repository}/actions/runs/12345/job/67890"
                    ),
                    "app": {"slug": "github-actions", "owner": {"login": "github"}},
                }
            ]
        },
        f"repos/{repository}/actions/runs/12345": {
            "conclusion": "success",
            "event": "pull_request",
            "head_sha": head,
            "path": ".github/workflows/ci.yml",
            "repository": {"full_name": repository},
        },
    }
    return {
        "repo": repo,
        "remote": remote,
        "stale": stale,
        "parent": parent,
        "first_parent": first_parent,
        "head": head,
        "merge": merge,
        "fixtures": fixtures,
    }


# Pipes whose reader threads were abandoned are parked here for the life of the
# process instead of being closed: closing them would free the fd numbers for
# reuse while a zombie reader could still loop, letting it read an unrelated
# later file that happened to receive the recycled fd number.
_ABANDONED_PIPES: list[IO[bytes]] = []


def _drain_pipe(
    fd: int,
    key: str,
    captured: dict[str, deque[bytes]],
    retained: dict[str, int],
    dropped: dict[str, int],
    capture_tail_bytes: int,
    last_progress: list[float],
    abandoned: threading.Event,
) -> None:
    """Drain one captured pipe into a bounded tail until EOF or abandonment.

    The abandon event is checked before every read: once the harness gives up
    on this reader it must never issue another ``os.read``, because the fd
    number could otherwise be recycled to an unrelated file whose bytes a
    still-looping zombie reader would steal. OSError also ends the drain when
    the abandoning thread switches the fd to non-blocking (EAGAIN).
    """
    with suppress(OSError, ValueError):
        while not abandoned.is_set() and (chunk := os.read(fd, 65536)):
            captured[key].append(chunk)
            retained[key] += len(chunk)
            while retained[key] > capture_tail_bytes and len(captured[key]) > 1:
                oldest = captured[key].popleft()
                retained[key] -= len(oldest)
                dropped[key] += len(oldest)
            if retained[key] > capture_tail_bytes:
                excess = retained[key] - capture_tail_bytes
                captured[key][0] = captured[key][0][excess:]
                retained[key] -= excess
                dropped[key] += excess
            last_progress[0] = time.monotonic()


def _run_bounded_subprocess(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: float,
    wall_timeout_seconds: float | None = None,
    capture_tail_bytes: int = _SUBPROCESS_TAIL_BYTES,
) -> subprocess.CompletedProcess[str]:
    # Two independent deadlines: timeout_seconds bounds *silence* (a child that
    # keeps writing to either captured pipe stays alive), wall_timeout_seconds
    # bounds *total runtime* even while output keeps arriving. Either firing
    # kills the whole process group. Captured output is a bounded tail: only
    # the most recent capture_tail_bytes per stream are retained, with a
    # truncation notice when earlier bytes were dropped.
    if wall_timeout_seconds is None:
        wall_timeout_seconds = timeout_seconds * _SUBPROCESS_WALL_MULTIPLIER
    process = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True,
        start_new_session=True,
    )
    stdout_pipe = process.stdout
    stderr_pipe = process.stderr
    assert stdout_pipe is not None and stderr_pipe is not None
    captured: dict[str, deque[bytes]] = {"stdout": deque(), "stderr": deque()}
    retained = {"stdout": 0, "stderr": 0}
    dropped = {"stdout": 0, "stderr": 0}
    started = time.monotonic()
    last_progress = [started]
    abandoned = threading.Event()

    readers = [
        threading.Thread(
            target=_drain_pipe,
            args=(
                pipe.fileno(),
                key,
                captured,
                retained,
                dropped,
                capture_tail_bytes,
                last_progress,
                abandoned,
            ),
            daemon=True,
        )
        for pipe, key in ((stdout_pipe, "stdout"), (stderr_pipe, "stderr"))
    ]
    for reader in readers:
        reader.start()

    def decoded(key: str) -> str:
        text = b"".join(captured[key]).decode(errors="replace")
        if dropped[key]:
            return f"[... {dropped[key]} bytes dropped ...]\n{text}"
        return text

    expired_deadline: float | None = None
    try:
        while process.poll() is None or any(reader.is_alive() for reader in readers):
            now = time.monotonic()
            if now - started >= wall_timeout_seconds:
                expired_deadline = wall_timeout_seconds
            elif now - last_progress[0] >= timeout_seconds:
                expired_deadline = timeout_seconds
            if expired_deadline is not None:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                break
            time.sleep(0.01)
    except BaseException:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        raise
    finally:
        # A descendant that re-setsid'd or double-forked survives the group
        # SIGKILL and keeps the captured pipes open, so joins must be bounded
        # or pytest hangs despite both deadlines. On join expiry the readers
        # are abandoned, never woken by force: close() from this thread would
        # not interrupt a reader blocked in os.read (the syscall holds the old
        # file description) and would free the fd numbers for reuse, letting a
        # still-looping reader steal bytes from an unrelated later file. So
        # instead the abandon event guarantees no reader issues a new os.read,
        # the fds are switched to non-blocking so a not-yet-blocked read fails
        # fast, and the pipe objects are parked module-globally, never closed,
        # so their fd numbers cannot be recycled. A reader already blocked in
        # os.read may stay blocked; the daemon flag plus the bounded joins are
        # the backstop that keeps pytest exit and this harness prompt.
        deadline = time.monotonic() + _SUBPROCESS_READER_JOIN_SECONDS
        for reader in readers:
            reader.join(timeout=max(0.0, deadline - time.monotonic()))
        if any(reader.is_alive() for reader in readers):
            abandoned.set()
            for pipe in (stdout_pipe, stderr_pipe):
                with suppress(OSError, ValueError):
                    os.set_blocking(pipe.fileno(), False)
            deadline = time.monotonic() + _SUBPROCESS_READER_JOIN_SECONDS
            for reader in readers:
                reader.join(timeout=max(0.0, deadline - time.monotonic()))
        if any(reader.is_alive() for reader in readers):
            _ABANDONED_PIPES.extend((stdout_pipe, stderr_pipe))
        else:
            stdout_pipe.close()
            stderr_pipe.close()
        returncode = process.wait()
    if expired_deadline is not None:
        raise subprocess.TimeoutExpired(
            args,
            expired_deadline,
            output=decoded("stdout"),
            stderr=decoded("stderr"),
        )
    return subprocess.CompletedProcess(args, returncode, decoded("stdout"), decoded("stderr"))


def _materialize_python_heredocs(script: str, tmp_path: Path) -> str:
    script_dir = tmp_path / "yaml-script"
    script_dir.mkdir(exist_ok=True)
    heredoc_count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal heredoc_count
        body_path = script_dir / f"heredoc-{heredoc_count}.py"
        heredoc_count += 1
        body_path.write_text(match.group("body") + "\n")
        return f"python3 {shlex.quote(str(body_path))}{match.group('args')}"

    materialized = _PYTHON_HEREDOC.sub(replace, script)
    assert heredoc_count == script.count("<<'PY'")
    assert "<<'PY'" not in materialized
    return materialized


def _run_yaml_script(
    script: str,
    *,
    cwd: Path,
    env: dict[str, str],
    tmp_path: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    return _run_bounded_subprocess(
        ["bash", "-c", _materialize_python_heredocs(script, tmp_path)],
        cwd=cwd,
        env=env,
        timeout_seconds=timeout_seconds,
    )


def _run_binding(
    case: dict[str, Any], tmp_path: Path, **env_overrides: str
) -> subprocess.CompletedProcess[str]:
    repo: Path = case["repo"]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _write_fake_gh(bin_dir)
    fixtures_path = tmp_path / "gh-fixtures.json"
    fixtures_path.write_text(json.dumps(case["fixtures"]))
    output = tmp_path / "github-output"
    summary = tmp_path / "github-summary"
    env = os.environ | {
        "EVENT_NAME": "release",
        "EVENT_SHA": case["merge"],
        "GITHUB_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(summary),
        "GH_FIXTURES": str(fixtures_path),
        "GH_PROMPT_DISABLED": "1",
        "GCM_INTERACTIVE": "Never",
        "GIT_TERMINAL_PROMPT": "0",
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "RELEASE_DRAFT": "false",
        "RELEASE_TAG": "v1.2.3",
        "REPOSITORY": "joyfulhouse/pylxpweb",
        "WORKFLOW_REF": "joyfulhouse/pylxpweb/.github/workflows/release.yml@refs/tags/v1.2.3",
        "WORKFLOW_SHA": case["merge"],
    }
    env.update(env_overrides)
    return _run_yaml_script(
        _step("bind-build-attest", "bind-source")["run"],
        cwd=repo,
        env=env,
        tmp_path=tmp_path,
        timeout_seconds=_BINDING_TIMEOUT_SECONDS,
    )


def _assert_reader_threads_settled(threads_before: int) -> None:
    """Reader threads must wind down after the harness returns.

    Uses a bounded retry and a ``<=`` comparison instead of exact equality:
    unrelated interpreter threads can start or stop under load, and exact
    ``threading.active_count()`` equality is flaky on loaded CI runners.
    """
    deadline = time.monotonic() + 5.0
    while threading.active_count() > threads_before and time.monotonic() < deadline:
        time.sleep(0.05)
    assert threading.active_count() <= threads_before


def test_bounded_subprocess_terminates_entire_child_group(tmp_path: Path) -> None:
    """A timed-out shell must not leave descendants holding captured pipes open."""
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        _run_bounded_subprocess(
            ["bash", "-c", "sleep 60 & wait"],
            cwd=tmp_path,
            env=os.environ.copy(),
            timeout_seconds=0.2,
        )
    assert time.monotonic() - started < 2


def test_bounded_subprocess_join_stays_bounded_when_descendant_escapes_group(
    tmp_path: Path,
) -> None:
    """A re-setsid'd descendant surviving the group SIGKILL cannot hang pytest.

    The escaped child inherits the captured pipes and keeps them open for 30
    seconds after the group is killed, so an unbounded ``reader.join()`` would
    block until the child exits. The harness must instead give up on the
    readers within its bounded join budget and raise the timeout promptly.
    """
    escaped = (
        f"{shlex.quote(sys.executable)} -c "
        '"import os, time; os.setsid(); time.sleep(30)" & sleep 30'
    )
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        _run_bounded_subprocess(
            ["bash", "-c", escaped],
            cwd=tmp_path,
            env=os.environ.copy(),
            timeout_seconds=0.3,
        )
    assert time.monotonic() - started < 15


def test_drain_pipe_never_issues_a_read_once_abandoned() -> None:
    """An abandoned drain must not touch its fd again, even with bytes pending.

    After the harness abandons a reader, its fd number must be treated as
    poisoned: one more ``os.read`` from a zombie reader could consume bytes
    from an unrelated file if the number were ever recycled. The abandon event
    is therefore checked before every read, so a drain entered (or resumed)
    after abandonment returns without consuming the pending bytes.
    """
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b"pending bytes")
        os.close(write_fd)
        write_fd = -1
        captured: dict[str, deque[bytes]] = {"stdout": deque()}
        abandoned = threading.Event()
        abandoned.set()
        _drain_pipe(
            read_fd,
            "stdout",
            captured,
            {"stdout": 0},
            {"stdout": 0},
            _SUBPROCESS_TAIL_BYTES,
            [time.monotonic()],
            abandoned,
        )
        assert not captured["stdout"]
        assert os.read(read_fd, 65536) == b"pending bytes"
    finally:
        os.close(read_fd)
        if write_fd != -1:
            os.close(write_fd)


def test_heredoc_materialization_keeps_body_lines_starting_with_py(tmp_path: Path) -> None:
    """A heredoc body line starting with ``PY`` is body, not the terminator.

    Without a line-anchored terminator the materialized script is silently
    truncated at the first ``PY``-prefixed body line and the sync assertions
    in ``_materialize_python_heredocs`` cannot catch it.
    """
    script = "python3 - <<'PY'\nx = 1\nPY_MARKER = 2\nprint(x + PY_MARKER)\nPY\n"
    materialized = _materialize_python_heredocs(script, tmp_path)
    body_path = tmp_path / "yaml-script" / "heredoc-0.py"
    assert body_path.read_text() == "x = 1\nPY_MARKER = 2\nprint(x + PY_MARKER)\n"
    assert "PY_MARKER" not in materialized


def test_bounded_subprocess_tolerates_slow_but_progressing_child(tmp_path: Path) -> None:
    """The deadline bounds silence, not total runtime.

    A child whose output gaps stay under the deadline must run to completion
    even when its total runtime exceeds the deadline several times over, and
    the harness must not leave reader threads behind afterwards. The 1-second
    silence deadline leaves ~20x margin over the 0.05-second cadence so a
    loaded CI runner cannot stretch one gap past the deadline.
    """
    threads_before = threading.active_count()
    result = _run_bounded_subprocess(
        ["bash", "-c", 'for i in $(seq 60); do echo "tick $i"; sleep 0.05; done'],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_seconds=1.0,
    )
    assert result.returncode == 0
    assert result.stdout.splitlines() == [f"tick {i}" for i in range(1, 61)]
    _assert_reader_threads_settled(threads_before)


def test_bounded_subprocess_kills_child_that_stops_progressing(tmp_path: Path) -> None:
    """Progress followed by silence is still killed, with the whole group."""
    threads_before = threading.active_count()
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as excinfo:
        _run_bounded_subprocess(
            ["bash", "-c", 'echo "made progress"; sleep 60 & wait'],
            cwd=tmp_path,
            env=os.environ.copy(),
            timeout_seconds=0.3,
        )
    assert time.monotonic() - started < 2
    assert "made progress" in (excinfo.value.output or "")
    _assert_reader_threads_settled(threads_before)


def test_bounded_subprocess_enforces_wall_deadline_despite_progress(tmp_path: Path) -> None:
    """A child that keeps emitting output must still die at the wall deadline."""
    threads_before = threading.active_count()
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as excinfo:
        _run_bounded_subprocess(
            ["bash", "-c", 'while true; do echo "still alive"; sleep 0.02; done'],
            cwd=tmp_path,
            env=os.environ.copy(),
            timeout_seconds=5.0,
            wall_timeout_seconds=0.4,
        )
    assert time.monotonic() - started < 3
    assert excinfo.value.timeout == 0.4
    assert "still alive" in (excinfo.value.output or "")
    _assert_reader_threads_settled(threads_before)


def test_bounded_subprocess_default_wall_deadline_is_finite() -> None:
    """Omitting the wall deadline must still yield a hard total-runtime bound."""
    assert _SUBPROCESS_WALL_MULTIPLIER > 1
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as excinfo:
        _run_bounded_subprocess(
            ["bash", "-c", 'while true; do echo "still alive"; done'],
            cwd=Path.cwd(),
            env=os.environ.copy(),
            timeout_seconds=0.1,
        )
    assert time.monotonic() - started < 5
    assert excinfo.value.timeout == pytest.approx(0.1 * _SUBPROCESS_WALL_MULTIPLIER)


def test_bounded_subprocess_retains_bounded_tail_of_output(tmp_path: Path) -> None:
    """Retained output stays bounded while the diagnostic tail survives."""
    result = _run_bounded_subprocess(
        ["bash", "-c", 'for i in $(seq 2000); do echo "line $i"; done'],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_seconds=5.0,
        capture_tail_bytes=1024,
    )
    assert result.returncode == 0
    assert len(result.stdout.encode()) < 1024 + 200
    assert result.stdout.startswith("[... ")
    assert "bytes dropped ...]" in result.stdout
    assert result.stdout.rstrip().endswith("line 2000")


def test_bounded_subprocess_bounds_memory_of_endlessly_emitting_child(tmp_path: Path) -> None:
    """A killed chatty child leaves a bounded diagnostic, not unbounded capture."""
    with pytest.raises(subprocess.TimeoutExpired) as excinfo:
        _run_bounded_subprocess(
            ["bash", "-c", 'while true; do echo "flood flood flood flood"; done'],
            cwd=tmp_path,
            env=os.environ.copy(),
            timeout_seconds=5.0,
            wall_timeout_seconds=0.4,
            capture_tail_bytes=2048,
        )
    output = excinfo.value.output or ""
    assert len(output.encode()) < 2048 + 200
    assert "flood" in output


def test_harness_never_hands_bash_a_python_heredoc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every workflow heredoc must be a private file before bash parses the script.

    Homebrew Bash 5.3 on macOS can deadlock in heredoc_write under load, so the
    harness removes the heredoc construct entirely instead of racing the pipe.
    This checks the command actually handed to bash for every heredoc-bearing
    workflow script: no ``<<'PY'`` survives, each body is byte-identical on
    disk, and the interpreter arguments are preserved.
    """
    scripts = [
        text
        for job in _workflow()["jobs"].values()
        for step in job["steps"]
        for text in [step.get("run")]
        if isinstance(text, str) and "<<'PY'" in text
    ]
    assert scripts, "release.yml no longer contains python heredocs to materialize"
    executed: list[list[str]] = []

    def record(
        args: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[str]:
        executed.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(sys.modules[__name__], "_run_bounded_subprocess", record)
    for index, script in enumerate(scripts):
        script_tmp = tmp_path / str(index)
        script_tmp.mkdir()
        _run_yaml_script(script, cwd=script_tmp, env={}, tmp_path=script_tmp, timeout_seconds=1.0)
        executable, flag, command = executed[-1]
        assert (executable, flag) == ("bash", "-c")
        assert "<<'PY'" not in command
        heredocs = list(_PYTHON_HEREDOC.finditer(script))
        assert len(heredocs) == script.count("<<'PY'")
        for heredoc_index, heredoc in enumerate(heredocs):
            body_path = script_tmp / "yaml-script" / f"heredoc-{heredoc_index}.py"
            invocation = f"python3 {shlex.quote(str(body_path))}{heredoc.group('args')}"
            assert invocation in command
            assert body_path.read_text() == heredoc.group("body") + "\n"


@pytest.mark.parametrize("lightweight", [False, True], ids=["annotated", "lightweight"])
def test_binding_accepts_exact_merged_pr_and_peels_tag(tmp_path: Path, lightweight: bool) -> None:
    """Changing tag peeling or exact merge binding rejects a valid release."""
    case = _release_repo(tmp_path, lightweight=lightweight)
    result = _run_binding(case, tmp_path)
    assert result.returncode == 0, result.stderr
    assert _git(case["repo"], "rev-parse", "refs/remotes/origin/main") == case["merge"]


def test_binding_force_replaces_stale_origin_main(tmp_path: Path) -> None:
    """Removing --force/--no-tags leaves a stale tracking ref trusted or unresolved."""
    case = _release_repo(tmp_path)
    assert _git(case["repo"], "rev-parse", "refs/remotes/origin/main") == case["stale"]
    result = _run_binding(case, tmp_path)
    assert result.returncode == 0, result.stderr
    assert _git(case["repo"], "rev-parse", "refs/remotes/origin/main") == case["merge"]


def test_checkout_depth_exposes_both_merge_parents(tmp_path: Path) -> None:
    """A one-commit Actions checkout makes a valid merge look parentless."""
    case = _release_repo(tmp_path / "source")
    checkout = tmp_path / "checkout"
    subprocess.run(
        [
            "git",
            "clone",
            "-q",
            "--no-local",
            "--depth",
            str(_step("bind-build-attest", "checkout-source")["with"]["fetch-depth"]),
            "--branch",
            "v1.2.3",
            str(case["remote"]),
            str(checkout),
        ],
        check=True,
    )
    case["repo"] = checkout
    result = _run_binding(case, tmp_path)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"EVENT_SHA": "0" * 40}, "event"),
        ({"WORKFLOW_SHA": "1" * 40}, "workflow SHA"),
        (
            {"WORKFLOW_REF": "joyfulhouse/pylxpweb/.github/workflows/release.yml@refs/heads/main"},
            "workflow ref",
        ),
        ({"RELEASE_TAG": "v9.9.9"}, "tag"),
    ],
)
def test_binding_rejects_event_workflow_and_version_identity_mismatch(
    tmp_path: Path, override: dict[str, str], message: str
) -> None:
    """Weakening any event/workflow/tag equality permits an unbound identity."""
    case = _release_repo(tmp_path)
    if override.get("RELEASE_TAG") == "v9.9.9":
        override["WORKFLOW_REF"] = (
            "joyfulhouse/pylxpweb/.github/workflows/release.yml@refs/tags/v9.9.9"
        )
        subprocess.run(
            ["git", "tag", "-a", "v9.9.9", case["merge"], "-m", "wrong version"],
            cwd=case["repo"],
            check=True,
        )
    result = _run_binding(case, tmp_path, **override)
    assert result.returncode != 0
    assert message.lower() in result.stderr.lower()


def test_binding_rejects_old_ancestor_or_main_movement(tmp_path: Path) -> None:
    """Replacing equality with ancestry permits publication after main advances."""
    case = _release_repo(tmp_path)
    repo: Path = case["repo"]
    subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True)
    _commit(repo, "later main", "later")
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=repo, check=True)
    subprocess.run(["git", "checkout", "-q", "--detach", "v1.2.3"], cwd=repo, check=True)
    result = _run_binding(case, tmp_path)
    assert result.returncode != 0
    assert "current main" in result.stderr.lower()


def test_binding_rejects_stale_candidate_merged_onto_newer_main(tmp_path: Path) -> None:
    """A successful old-head CI result cannot cover an untested combined merge tree."""
    case = _release_repo(tmp_path, stale_candidate=True)
    result = _run_binding(case, tmp_path)
    assert result.returncode != 0
    assert "up to date" in result.stderr.lower()


def test_binding_rejects_merge_tree_not_tested_on_exact_pr_head(tmp_path: Path) -> None:
    """An up-to-date two-parent commit cannot add bytes absent from the CI-tested head."""
    case = _release_repo(tmp_path)
    repo: Path = case["repo"]
    old_merge = case["merge"]
    repo.joinpath("injected.txt").write_text("not CI-tested\n")
    subprocess.run(["git", "add", "injected.txt"], cwd=repo, check=True)
    tree = _git(repo, "write-tree")
    altered = subprocess.check_output(
        [
            "git",
            "commit-tree",
            tree,
            "-p",
            case["first_parent"],
            "-p",
            case["head"],
            "-m",
            "altered merge tree",
        ],
        cwd=repo,
        text=True,
    ).strip()
    subprocess.run(["git", "tag", "-f", "v1.2.3", altered], cwd=repo, check=True)
    subprocess.run(["git", "branch", "-f", "main", altered], cwd=repo, check=True)
    subprocess.run(
        ["git", "push", "-q", "--force", "origin", "main", "v1.2.3"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "checkout", "-q", "--detach", altered], cwd=repo, check=True)
    pull_key = f"repos/joyfulhouse/pylxpweb/commits/{old_merge}/pulls"
    pull = case["fixtures"].pop(pull_key)
    pull[0]["merge_commit_sha"] = altered
    case["fixtures"][f"repos/joyfulhouse/pylxpweb/commits/{altered}/pulls"] = pull
    case["merge"] = altered
    result = _run_binding(case, tmp_path)
    assert result.returncode != 0
    assert "merge tree" in result.stderr.lower()


def test_binding_does_not_treat_mutable_pr_base_sha_as_merge_parent(tmp_path: Path) -> None:
    """GitHub updates closed PR base.sha after merge; git parentage owns merge-time base."""
    case = _release_repo(tmp_path)
    pull_key = f"repos/joyfulhouse/pylxpweb/commits/{case['merge']}/pulls"
    case["fixtures"][pull_key][0]["base"]["sha"] = case["merge"]
    result = _run_binding(case, tmp_path)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "mutation",
    [
        "not-merge",
        "octopus",
        "no-pr",
        "wrong-pr",
        "wrong-merge-sha",
        "wrong-base",
        "wrong-head",
    ],
)
def test_binding_rejects_invalid_merge_and_associated_pr(tmp_path: Path, mutation: str) -> None:
    """Relaxing merge geometry or PR identity admits a non-CI-tested candidate."""
    case = _release_repo(tmp_path)
    repo: Path = case["repo"]
    pull_key = f"repos/joyfulhouse/pylxpweb/commits/{case['merge']}/pulls"
    pull = case["fixtures"][pull_key][0]
    if mutation == "not-merge":
        subprocess.run(
            ["git", "tag", "-f", "-a", "v1.2.3", case["head"], "-m", "non-merge"],
            cwd=repo,
            check=True,
        )
        subprocess.run(["git", "branch", "-f", "main", case["head"]], cwd=repo, check=True)
        subprocess.run(
            ["git", "push", "-q", "--force", "origin", "main", "v1.2.3"],
            cwd=repo,
            check=True,
        )
        case["merge"] = case["head"]
    elif mutation == "octopus":
        subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True)
        subprocess.run(["git", "checkout", "-qb", "side-a", case["merge"]], cwd=repo, check=True)
        repo.joinpath("side-a.txt").write_text("a")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "side a"], cwd=repo, check=True)
        subprocess.run(["git", "checkout", "-qb", "side-b", case["merge"]], cwd=repo, check=True)
        repo.joinpath("side-b.txt").write_text("b")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "side b"], cwd=repo, check=True)
        subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True)
        subprocess.run(
            ["git", "merge", "-q", "--no-ff", "side-a", "side-b", "-m", "octopus"],
            cwd=repo,
            check=True,
        )
        octopus = _git(repo, "rev-parse", "HEAD")
        subprocess.run(
            ["git", "tag", "-f", "-a", "v1.2.3", octopus, "-m", "octopus"],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "push", "-q", "--force", "origin", "main", "v1.2.3"], cwd=repo, check=True
        )
        case["merge"] = octopus
    elif mutation == "no-pr":
        case["fixtures"][pull_key] = []
    elif mutation == "wrong-pr":
        case["fixtures"][pull_key].append(dict(pull, number=18))
    elif mutation == "wrong-merge-sha":
        pull["merge_commit_sha"] = case["head"]
    elif mutation == "wrong-base":
        pull["base"]["ref"] = "release"
    elif mutation == "wrong-head":
        pull["head"]["sha"] = case["parent"]
    result = _run_binding(case, tmp_path)
    assert result.returncode != 0


@pytest.mark.parametrize("mutation", ["missing-ci", "failed-ci", "wrong-ci-head"])
def test_binding_rejects_missing_or_stale_required_ci(tmp_path: Path, mutation: str) -> None:
    """Dropping the exact-head CI-success binding permits an untested candidate."""
    case = _release_repo(tmp_path)
    check_key = f"repos/joyfulhouse/pylxpweb/commits/{case['head']}/check-runs"
    if mutation == "missing-ci":
        case["fixtures"][check_key]["check_runs"] = []
    elif mutation == "failed-ci":
        case["fixtures"][check_key]["check_runs"][0]["conclusion"] = "failure"
    elif mutation == "wrong-ci-head":
        case["fixtures"][check_key]["check_runs"][0]["head_sha"] = case["parent"]
    result = _run_binding(case, tmp_path)
    assert result.returncode != 0


@pytest.mark.parametrize(
    "mutation",
    [
        "collision",
        "wrong-app",
        "wrong-owner",
        "wrong-workflow",
        "wrong-run-head",
        "wrong-event",
    ],
)
def test_binding_rejects_same_name_ci_from_untrusted_producer(
    tmp_path: Path, mutation: str
) -> None:
    """A same-name check must resolve to this repository's exact PR CI workflow run."""
    case = _release_repo(tmp_path)
    check_key = f"repos/joyfulhouse/pylxpweb/commits/{case['head']}/check-runs"
    check = case["fixtures"][check_key]["check_runs"][0]
    run = case["fixtures"]["repos/joyfulhouse/pylxpweb/actions/runs/12345"]
    if mutation == "collision":
        check_key = f"repos/joyfulhouse/pylxpweb/commits/{case['head']}/check-runs"
        case["fixtures"][check_key]["check_runs"].append(
            {
                **check,
                "app": {"slug": "attacker-ci", "owner": {"login": "attacker"}},
            }
        )
    elif mutation == "wrong-app":
        check["app"]["slug"] = "attacker-ci"
    elif mutation == "wrong-owner":
        check["app"]["owner"]["login"] = "attacker"
    elif mutation == "wrong-workflow":
        run["path"] = ".github/workflows/lookalike.yml"
    elif mutation == "wrong-run-head":
        run["head_sha"] = case["parent"]
    elif mutation == "wrong-event":
        run["event"] = "push"
    result = _run_binding(case, tmp_path)
    assert result.returncode != 0


def test_binding_releases_merged_pr_with_zero_reviews(tmp_path: Path) -> None:
    """Review approval is not required: a merged two-parent PR releases as-is.

    The fixtures contain no review data at all, so any re-introduction of a
    review-approval binding (which would have to fetch and assert on reviews)
    fails this test rather than silently tightening the release contract.
    """
    case = _release_repo(tmp_path)
    assert not any("reviews" in endpoint for endpoint in case["fixtures"])
    result = _run_binding(case, tmp_path)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("step_id", ["assert-clean-source", "seal-source"])
@pytest.mark.parametrize("mutation", ["tracked", "staged", "untracked"])
def test_source_tree_checks_reject_mutable_build_inputs(
    tmp_path: Path, step_id: str, mutation: str
) -> None:
    """Removing either cleanliness check permits bytes outside the recorded HEAD tree."""
    case = _release_repo(tmp_path)
    repo: Path = case["repo"]
    if step_id == "seal-source":
        assert _run_binding(case, tmp_path).returncode == 0
        output = repo / "release-bundle" / "dist"
        output.mkdir(parents=True)
        output.joinpath("expected.whl").write_bytes(b"expected output")
    if mutation in {"tracked", "staged"}:
        repo.joinpath("source.txt").write_text("mutated")
        if mutation == "staged":
            subprocess.run(["git", "add", "source.txt"], cwd=repo, check=True)
    else:
        repo.joinpath("build-input.py").write_text("MUTATED = True\n")
    env = os.environ | {"EXPECTED_COMMIT": case["merge"]}
    result = _run_yaml_script(
        _step("bind-build-attest", step_id)["run"],
        cwd=repo,
        env=env,
        tmp_path=tmp_path,
        timeout_seconds=15,
    )
    assert result.returncode != 0
    assert "source tree" in result.stderr.lower()


def test_sealing_allows_only_the_expected_release_bundle(tmp_path: Path) -> None:
    """The generated sealed bundle is output, not an untracked build input."""
    case = _release_repo(tmp_path)
    assert _run_binding(case, tmp_path).returncode == 0
    repo: Path = case["repo"]
    output = repo / "release-bundle" / "dist"
    output.mkdir(parents=True)
    output.joinpath("expected.whl").write_bytes(b"expected output")
    env = os.environ | {"EXPECTED_COMMIT": case["merge"]}
    result = _run_yaml_script(
        _step("bind-build-attest", "seal-source")["run"],
        cwd=repo,
        env=env,
        tmp_path=tmp_path,
        timeout_seconds=15,
    )
    assert result.returncode == 0, result.stderr


def test_sealing_rechecks_fresh_main_immediately_before_attestation(tmp_path: Path) -> None:
    """Removing the second force-fetch permits main movement before sealing."""
    case = _release_repo(tmp_path)
    assert _run_binding(case, tmp_path).returncode == 0
    repo: Path = case["repo"]
    subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True)
    _commit(repo, "late movement", "late")
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=repo, check=True)
    subprocess.run(["git", "checkout", "-q", "--detach", "v1.2.3"], cwd=repo, check=True)
    env = os.environ | {"EXPECTED_COMMIT": case["merge"]}
    result = _run_yaml_script(
        _step("bind-build-attest", "seal-source")["run"],
        cwd=repo,
        env=env,
        tmp_path=tmp_path,
        timeout_seconds=15,
    )
    assert result.returncode != 0
    assert "current main" in result.stderr.lower()


def test_release_job_graph_and_permissions_are_fail_closed() -> None:
    """Changing a dependency or granting publisher shell/OIDC broadens promotion authority."""
    workflow = _workflow()
    expected = [
        "bind-build-attest",
        "prepare-testpypi",
        "publish-testpypi",
        "verify-testpypi",
        "prepare-pypi",
        "publish-pypi",
        "verify-pypi",
    ]
    assert list(workflow["jobs"]) == expected
    previous: str | None = None
    for job_id in expected:
        job = workflow["jobs"][job_id]
        if previous is not None:
            needs = job["needs"] if isinstance(job["needs"], list) else [job["needs"]]
            assert previous in needs
        previous = job_id
    for job_id in ("publish-testpypi", "publish-pypi"):
        job = workflow["jobs"][job_id]
        assert job["permissions"] == {"contents": "read", "id-token": "write"}
        assert len(job["steps"]) == 2
        assert all("uses" in step and "run" not in step for step in job["steps"])
        assert "actions/download-artifact@" in job["steps"][0]["uses"]
        assert "pypa/gh-action-pypi-publish@" in job["steps"][1]["uses"]
    assert "skip-existing" not in _job("publish-pypi")["steps"][1].get("with", {})
    assert _job("bind-build-attest")["permissions"]["actions"] == "read"
    for job_id in set(expected) - {"bind-build-attest", "publish-testpypi", "publish-pypi"}:
        assert _job(job_id).get("permissions", {}).get("id-token") != "write"
    for job_id in ("prepare-testpypi", "prepare-pypi"):
        upload = _step(job_id, "upload-staging-artifact")
        assert upload["with"]["retention-days"] == 30


def test_release_trigger_and_workflow_identity_are_tag_only() -> None:
    """Adding branch dispatch permits branch-resident release workflow execution."""
    trigger = _workflow()["on"]
    assert trigger == {"release": {"types": ["published"]}}
    checkout = _step("bind-build-attest", "checkout-source")
    assert checkout["with"]["ref"] == "${{ github.event.release.tag_name }}"
    assert checkout["with"]["fetch-tags"] is False
    assert checkout["with"]["persist-credentials"] is False
    assert "repository remains public" in (_ROOT / ".github" / "WORKFLOWS.md").read_text().lower()


def test_build_uses_verified_digest_pinned_offline_read_only_container() -> None:
    """Floating image/tool/backend versions or writable/networked mounts break hermeticity."""
    workflow = _workflow()
    image = workflow["env"]["BUILD_IMAGE"]
    assert image == (
        "ghcr.io/astral-sh/uv:0.9.30-python3.13-bookworm-slim@"
        "sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca"
    )
    run = _step("bind-build-attest", "build-distributions")["run"]
    for token in (
        "--network none",
        "--read-only",
        '--user "$(id -u):$(id -g)"',
        ":/src:ro",
        ":/out:rw",
        "--tmpfs /cache",
        "uv build --offline --no-python-downloads --no-sources",
        "uv 0.9.30",
        "Python 3.13",
        "uv_build==0.9.30",
    ):
        assert token in run
    assert run.count("uv build --offline --no-python-downloads --no-sources") == 1


def test_build_backend_is_exactly_the_bundled_uv_version() -> None:
    """Widening the backend range permits an offline cache miss or different builder."""
    pyproject = (_ROOT / "pyproject.toml").read_text()
    assert 'requires = ["uv_build==0.9.30"]' in pyproject


def test_build_attests_source_and_distributions_separately_with_full_sha_actions() -> None:
    """Combining or omitting provenance prevents independent source/build verification."""
    source = _step("bind-build-attest", "attest-source")
    build = _step("bind-build-attest", "attest-build")
    assert source["uses"].startswith("actions/attest@")
    assert build["uses"].startswith("actions/attest@")
    assert _FULL_SHA_ACTION.fullmatch(source["uses"])
    assert _FULL_SHA_ACTION.fullmatch(build["uses"])
    assert source["with"]["subject-path"].endswith("release-source.json")
    assert build["with"]["subject-checksums"].endswith("DIST_SHA256SUMS")
    assert source["with"] != build["with"]


def test_preparation_verifies_attestation_identity_before_staging() -> None:
    """Dropping signer/source constraints permits a valid attestation from the wrong run."""
    for job_id in ("prepare-testpypi", "prepare-pypi"):
        step = _step(job_id, "verify-release-bundle")
        run = step["run"]
        assert step["env"]["GH_TOKEN"] == "${{ github.token }}"
        for option in (
            "--signer-workflow",
            "--signer-digest",
            "--source-ref",
            "--source-digest",
            "--bundle",
        ):
            assert option in run
        assert run.count("gh attestation verify") == 2  # source command + distribution loop


def test_bundle_validation_rejects_artifact_and_attestation_tampering(tmp_path: Path) -> None:
    """Removing hash or gh verification permits modified bytes into staging."""
    bundle = tmp_path / "release-bundle"
    dist = bundle / "dist"
    attestations = bundle / "attestations"
    dist.mkdir(parents=True)
    attestations.mkdir()
    wheel = dist / "pylxpweb-1.2.3-py3-none-any.whl"
    sdist = dist / "pylxpweb-1.2.3.tar.gz"
    source = bundle / "release-source.json"
    dist_manifest = bundle / "DIST_SHA256SUMS"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    source.write_text(
        json.dumps(
            {
                "artifact_name": "release",
                "commit": "a" * 40,
                "container_image": _workflow()["env"]["BUILD_IMAGE"],
                "head": "b" * 40,
                "project_name": "pylxpweb",
                "pr": 17,
                "schema_version": 2,
                "tag": "v1.2.3",
                "tree": "c" * 40,
                "version": "1.2.3",
                "workflow_ref": _TEST_WORKFLOW_REF,
                "workflow_sha": "a" * 40,
            }
        )
    )
    dist_manifest.write_text(
        f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  dist/{wheel.name}\n"
        f"{hashlib.sha256(sdist.read_bytes()).hexdigest()}  dist/{sdist.name}\n"
    )
    (attestations / "source.jsonl").write_text("source-bundle")
    (attestations / "build.jsonl").write_text("build-bundle")
    manifest_files = [source, dist_manifest, wheel, sdist]
    (bundle / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(bundle)}\n"
            for path in manifest_files
        )
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_gh(bin_dir)
    env = os.environ | {
        "ARTIFACT_NAME": "release",
        "EXPECTED_COMMIT": "a" * 40,
        "EXPECTED_CONTAINER_IMAGE": _workflow()["env"]["BUILD_IMAGE"],
        "EXPECTED_HEAD": "b" * 40,
        "EXPECTED_PROJECT_NAME": "pylxpweb",
        "EXPECTED_PR": "17",
        "EXPECTED_TAG": "v1.2.3",
        "EXPECTED_TREE": "c" * 40,
        "EXPECTED_VERSION": "1.2.3",
        "EXPECTED_WORKFLOW_REF": _TEST_WORKFLOW_REF,
        "EXPECTED_WORKFLOW_SHA": "a" * 40,
        "GH_CALLS": str(tmp_path / "gh-calls"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "github-summary"),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "REPOSITORY": "joyfulhouse/pylxpweb",
    }
    env.pop("GH_TOKEN", None)
    run = _step("prepare-testpypi", "verify-release-bundle")["run"]

    def run_verifier(script: str) -> subprocess.CompletedProcess[str]:
        return _run_yaml_script(
            script,
            cwd=tmp_path,
            env=env,
            tmp_path=tmp_path,
            timeout_seconds=15,
        )

    missing_auth = run_verifier(run)
    assert missing_auth.returncode != 0
    env["GH_TOKEN"] = "scoped-test-token"
    good = run_verifier(run)
    assert good.returncode == 0
    calls = (tmp_path / "gh-calls").read_text().splitlines()
    assert len(calls) == 3
    assert {call.split()[2] for call in calls} == {
        "release-bundle/release-source.json",
        f"release-bundle/dist/{wheel.name}",
        f"release-bundle/dist/{sdist.name}",
    }
    identity_mutations = {
        "repository": ('--repo "$REPOSITORY"', '--repo "attacker/repository"'),
        "workflow": (
            'signer="$REPOSITORY/.github/workflows/release.yml"',
            'signer="attacker/repository/.github/workflows/release.yml"',
        ),
        "workflow digest": (
            '--signer-digest "$EXPECTED_WORKFLOW_SHA"',
            f'--signer-digest "{"0" * 40}"',
        ),
        "tag": ('--source-ref "refs/tags/$EXPECTED_TAG"', '--source-ref "refs/tags/v9.9.9"'),
        "commit": (
            '--source-digest "$EXPECTED_COMMIT"',
            f'--source-digest "{"f" * 40}"',
        ),
        "subject": (
            "gh attestation verify release-bundle/release-source.json",
            "gh attestation verify release-bundle/DIST_SHA256SUMS",
        ),
    }
    for label, (expected, replacement) in identity_mutations.items():
        assert expected in run, label
        mutated = run.replace(expected, replacement, 1)
        result = run_verifier(mutated)
        assert result.returncode != 0, label
    wheel.write_bytes(b"tampered")
    tampered_artifact = run_verifier(run)
    assert tampered_artifact.returncode != 0
    wheel.write_bytes(b"wheel")
    env["EXPECTED_ATTESTATION_CONTENT"] = "not-the-bundle"
    tampered_attestation = run_verifier(run)
    assert tampered_attestation.returncode != 0


def test_index_verifier_retries_then_accepts_exact_remote_bytes(
    tmp_path: Path,
    package_index_server: tuple[str, dict[str, Any]],
) -> None:
    """The YAML-derived verifier handles transient index lag and exact bytes."""
    base_url, state = package_index_server
    _, payload = _prepare_index_case(tmp_path, base_url, state)
    state["index_responses"] = [503, payload]
    result = _run_index_verifier(tmp_path, base_url, job_id="verify-testpypi")
    assert result.returncode == 0, result.stderr
    assert state["index_calls"] >= 2


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-project",
        "wrong-version",
        "advertised-host",
        "redirect-host",
        "missing-file",
        "unexpected-file",
        "yanked-file",
        "index-hash",
        "downloaded-bytes",
        "exhausted-retries",
    ],
)
def test_index_verifier_rejects_remote_identity_and_byte_mutations(
    tmp_path: Path,
    package_index_server: tuple[str, dict[str, Any]],
    mutation: str,
) -> None:
    """Weakening any remote-index check admits a different published artifact set."""
    base_url, state = package_index_server
    files, payload = _prepare_index_case(tmp_path, base_url, state)
    if mutation == "wrong-project":
        payload["info"]["name"] = "lookalike"
    elif mutation == "wrong-version":
        payload["info"]["version"] = "9.9.9"
    elif mutation == "advertised-host":
        payload["urls"][0]["url"] = payload["urls"][0]["url"].replace("127.0.0.1", "localhost")
    elif mutation == "redirect-host":
        name = payload["urls"][0]["filename"]
        state["redirected_files"][name] = files[name]
        state["files"][name] = {
            "redirect": f"{base_url.replace('127.0.0.1', 'localhost')}/redirected/{name}"
        }
    elif mutation == "missing-file":
        payload["urls"] = payload["urls"][:1]
    elif mutation == "unexpected-file":
        payload["urls"].append(
            {
                "digests": {"sha256": hashlib.sha256(b"other").hexdigest()},
                "filename": "pylxpweb-1.2.3.zip",
                "url": f"{base_url}/files/pylxpweb-1.2.3.zip",
                "yanked": False,
            }
        )
    elif mutation == "yanked-file":
        payload["urls"][0]["yanked"] = True
    elif mutation == "index-hash":
        payload["urls"][0]["digests"]["sha256"] = "0" * 64
    elif mutation == "downloaded-bytes":
        state["files"][payload["urls"][0]["filename"]] = b"tampered"
    elif mutation == "exhausted-retries":
        state["index_responses"] = [503, 503, 503]
    if not state["index_responses"]:
        state["index_responses"] = [payload]
    result = _run_index_verifier(tmp_path, base_url, job_id="verify-testpypi")
    assert result.returncode != 0


def test_index_verifier_rejects_competing_publication_race(
    tmp_path: Path,
    package_index_server: tuple[str, dict[str, Any]],
) -> None:
    """A second index snapshot catches a file added while exact bytes are downloaded."""
    base_url, state = package_index_server
    _, exact = _prepare_index_case(tmp_path, base_url, state)
    raced = json.loads(json.dumps(exact))
    raced["urls"].append(
        {
            "digests": {"sha256": hashlib.sha256(b"competitor").hexdigest()},
            "filename": "pylxpweb-1.2.3.zip",
            "url": f"{base_url}/files/pylxpweb-1.2.3.zip",
            "yanked": False,
        }
    )
    state["index_responses"] = [exact, raced]
    result = _run_index_verifier(tmp_path, base_url, job_id="verify-testpypi")
    assert result.returncode != 0
    assert state["index_calls"] == 2


def test_index_verifier_worst_case_fits_job_timeout_with_five_minute_headroom() -> None:
    """Polling, transfers, final snapshot, and non-index verification fit mechanically."""
    job = _job("verify-testpypi")
    step = _step("verify-testpypi", "verify-testpypi-files")
    env = step["env"]
    attempts = int(env["MAX_ATTEMPTS"])
    retry_base = int(env["RETRY_BASE_SECONDS"])
    index_total = int(env["INDEX_TOTAL_SECONDS"])
    download_total = int(env["DOWNLOAD_TOTAL_SECONDS"])
    socket_timeout = int(env["SOCKET_TIMEOUT_SECONDS"])
    backoff = sum(min(attempt * retry_base, 30) for attempt in range(1, attempts))
    verifier_worst_case = attempts * index_total + backoff + 2 * download_total + index_total
    headroom = int(job["timeout-minutes"]) * 60 - verifier_worst_case
    assert headroom >= 300
    assert socket_timeout < index_total
    assert socket_timeout < download_total
    assert "signal.setitimer" in step["run"]


def test_index_verifier_enforces_total_deadline_despite_socket_activity(
    tmp_path: Path,
    package_index_server: tuple[str, dict[str, Any]],
) -> None:
    """A drip-fed body cannot evade the total-transfer deadline via socket activity."""
    base_url, state = package_index_server
    files, payload = _prepare_index_case(tmp_path, base_url, state)
    wheel_name = next(name for name in files if name.endswith(".whl"))
    state["files"][wheel_name] = {"drip": files[wheel_name], "delay": 0.1}
    state["index_responses"] = [payload]
    result = _run_index_verifier(
        tmp_path,
        base_url,
        env_overrides={
            "DOWNLOAD_TOTAL_SECONDS": "0.2",
            "INDEX_TOTAL_SECONDS": "2",
            "SOCKET_TIMEOUT_SECONDS": "1",
        },
    )
    assert result.returncode != 0


def _read_output(path: Path, key: str) -> str:
    """Read the last scalar written for a GitHub Actions output."""
    prefix = f"{key}="
    return next(
        line.removeprefix(prefix)
        for line in reversed(path.read_text().splitlines())
        if line.startswith(prefix)
    )


def _run_pypi_classifier(
    tmp_path: Path,
    base_url: str,
    *,
    env_overrides: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], str]:
    output = tmp_path / "prepare-pypi-output"
    summary = tmp_path / "prepare-pypi-summary"
    env = os.environ | {
        "ALLOWED_FILE_HOST": "127.0.0.1",
        "ALLOWED_INDEX_HOST": "127.0.0.1",
        "DOWNLOAD_TOTAL_SECONDS": "2",
        "EXPECTED_PROJECT_NAME": "pylxpweb",
        "EXPECTED_VERSION": "1.2.3",
        "GITHUB_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(summary),
        "INDEX_JSON_BASE": f"{base_url}/pypi",
        "INDEX_TOTAL_SECONDS": "2",
        "REQUIRED_FILE_SCHEME": "http",
        "REQUIRED_INDEX_SCHEME": "http",
        "SNAPSHOT_DELAY_SECONDS": "0",
        "SOCKET_TIMEOUT_SECONDS": "1",
    }
    env.update(env_overrides or {})
    result = _run_yaml_script(
        _step("prepare-pypi", "classify-pypi-state")["run"],
        cwd=tmp_path,
        env=env,
        tmp_path=tmp_path,
        timeout_seconds=15,
    )
    state = _read_output(output, "state") if output.exists() else ""
    return result, state


@pytest.mark.parametrize(
    ("remote_case", "expected_state"),
    [
        ("absent", "ABSENT"),
        ("exact", "EXACT_COMPLETE"),
        ("partial", "PARTIAL"),
        ("mismatch", "MISMATCH"),
        ("yanked", "YANKED"),
        ("extra", "EXTRA"),
        ("competing", "COMPETING"),
        ("uncertain", "UNCERTAIN"),
    ],
)
def test_pypi_classifier_emits_closed_state_machine_from_remote_bytes(
    tmp_path: Path,
    package_index_server: tuple[str, dict[str, Any]],
    remote_case: str,
    expected_state: str,
) -> None:
    """Deleting any state branch makes an immutable remote state publishable or ambiguous."""
    base_url, server = package_index_server
    files, payload = _prepare_index_case(tmp_path, base_url, server)
    if remote_case == "absent":
        server["index_responses"] = [404, 404]
    elif remote_case == "partial":
        payload["urls"] = payload["urls"][:1]
    elif remote_case == "mismatch":
        payload["urls"][0]["digests"]["sha256"] = "0" * 64
    elif remote_case == "yanked":
        payload["urls"][0]["yanked"] = True
    elif remote_case == "extra":
        payload["urls"].append(
            {
                "digests": {"sha256": hashlib.sha256(b"extra").hexdigest()},
                "filename": "pylxpweb-1.2.3.zip",
                "url": f"{base_url}/files/pylxpweb-1.2.3.zip",
                "yanked": False,
            }
        )
    elif remote_case == "competing":
        payload["urls"].append(dict(payload["urls"][0]))
    elif remote_case == "uncertain":
        server["index_responses"] = [503, 503]
    if not server["index_responses"]:
        server["index_responses"] = [payload, payload]
    result, state = _run_pypi_classifier(tmp_path, base_url)
    assert result.returncode == 0, result.stderr
    assert state == expected_state
    summary = (tmp_path / "prepare-pypi-summary").read_text()
    assert "Expected sealed files" in summary
    assert "First snapshot" in summary
    assert "Second snapshot" in summary
    if expected_state == "EXACT_COMPLETE":
        assert server["files"] == files
        assert server["request_events"][0] == "index"
        assert server["request_events"][-1] == "index"
        assert "file" in server["request_events"][1:-1]


@pytest.mark.parametrize(
    "mutation",
    [
        "advertised-host",
        "redirect-host",
        "metadata-hash",
        "downloaded-bytes",
        "inconsistent-snapshots",
        "malformed-json",
        "partial-metadata-hash",
        "partial-advertised-host",
        "partial-downloaded-bytes",
        "partial-redirect-host",
        "extra-metadata-hash",
        "extra-downloaded-bytes",
        "index-redirect-host",
        "index-redirect-absent",
    ],
)
def test_pypi_classifier_never_publishes_untrusted_or_unstable_evidence(
    tmp_path: Path,
    package_index_server: tuple[str, dict[str, Any]],
    mutation: str,
) -> None:
    """Weakening host/hash/byte/snapshot checks can misclassify occupied PyPI as absent."""
    base_url, server = package_index_server
    files, payload = _prepare_index_case(tmp_path, base_url, server)
    localhost_base = base_url.replace("127.0.0.1", "localhost")
    expected = "MISMATCH"
    if mutation.startswith("partial-"):
        payload["urls"] = payload["urls"][:1]
    elif mutation.startswith("extra-"):
        payload["urls"].append(
            {
                "digests": {"sha256": hashlib.sha256(b"extra").hexdigest()},
                "filename": "pylxpweb-1.2.3.zip",
                "url": f"{base_url}/files/pylxpweb-1.2.3.zip",
                "yanked": False,
            }
        )
    if mutation in {"advertised-host", "partial-advertised-host"}:
        payload["urls"][0]["url"] = payload["urls"][0]["url"].replace("127.0.0.1", "localhost")
    elif mutation in {"redirect-host", "partial-redirect-host"}:
        name = payload["urls"][0]["filename"]
        server["redirected_files"][name] = files[name]
        server["files"][name] = {"redirect": f"{localhost_base}/redirected/{name}"}
    elif mutation in {"metadata-hash", "partial-metadata-hash", "extra-metadata-hash"}:
        payload["urls"][0]["digests"]["sha256"] = "0" * 64
    elif mutation in {"downloaded-bytes", "partial-downloaded-bytes", "extra-downloaded-bytes"}:
        server["files"][payload["urls"][0]["filename"]] = b"tampered"
    elif mutation == "inconsistent-snapshots":
        changed = json.loads(json.dumps(payload))
        changed["urls"][0]["yanked"] = True
        server["index_responses"] = [payload, changed]
        expected = "UNCERTAIN"
    elif mutation == "malformed-json":
        server["index_responses"] = ["not-an-object", "not-an-object"]
        expected = "UNCERTAIN"
    elif mutation == "index-redirect-host":
        server["redirected_index"] = payload
        redirect = {"redirect": f"{localhost_base}/redirected-index"}
        server["index_responses"] = [redirect, redirect]
        expected = "UNCERTAIN"
    elif mutation == "index-redirect-absent":
        redirect = {"redirect": f"{localhost_base}/missing-index"}
        server["index_responses"] = [redirect, redirect]
        expected = "UNCERTAIN"
    if not server["index_responses"]:
        server["index_responses"] = [payload, payload]
    result, state = _run_pypi_classifier(tmp_path, base_url)
    assert result.returncode == 0, result.stderr
    assert state == expected
    assert state != "ABSENT"


def test_recovery_recomputes_state_from_mutable_remote_without_rebuilding(
    tmp_path: Path,
    package_index_server: tuple[str, dict[str, Any]],
) -> None:
    """Caching prepare output would miss an upload accepted after a lost publisher response."""
    base_url, server = package_index_server
    _, payload = _prepare_index_case(tmp_path, base_url, server)
    server["index_responses"] = [404, 404]
    first, first_state = _run_pypi_classifier(tmp_path, base_url)
    server["index_calls"] = 0
    server["index_responses"] = [payload, payload]
    second, second_state = _run_pypi_classifier(tmp_path, base_url)
    assert first.returncode == second.returncode == 0
    assert (first_state, second_state) == ("ABSENT", "EXACT_COMPLETE")
    assert _job("prepare-pypi")["needs"] == ["bind-build-attest", "verify-testpypi"]
    assert "bind-build-attest" not in _job("prepare-pypi").get("if", "")


def _artifact_fixture(expected_name: str, expected_digest: str) -> dict[str, Any]:
    run_id = 12345
    commit = "a" * 40
    repository = "joyfulhouse/pylxpweb"
    artifact = {
        "id": 987,
        "name": expected_name,
        "expired": False,
        "digest": expected_digest,
        "workflow_run": {
            "id": run_id,
            "head_sha": commit,
            "repository_id": 42,
            "head_repository_id": 42,
        },
    }
    return {
        f"repos/{repository}/actions/runs/{run_id}": {
            "id": run_id,
            "event": "release",
            "head_sha": commit,
            "path": ".github/workflows/release.yml",
            "repository": {"id": 42, "full_name": repository},
            "head_repository": {"id": 42, "full_name": repository},
        },
        f"repos/{repository}/actions/runs/{run_id}/artifacts": {
            "total_count": 1,
            "artifacts": [artifact],
        },
    }


def _run_artifact_resolution(
    tmp_path: Path,
    fixtures: dict[str, Any],
    *,
    expected_digest: str = "d" * 64,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _write_fake_gh(bin_dir)
    fixtures_path = tmp_path / "artifact-fixtures.json"
    fixtures_path.write_text(json.dumps(fixtures))
    env = os.environ | {
        "EXPECTED_ARTIFACT_DIGEST": expected_digest,
        "EXPECTED_ARTIFACT_NAME": "pylxpweb-release-1.2.3-aaaaaaaaaaaa",
        "EXPECTED_COMMIT": "a" * 40,
        "GH_FIXTURES": str(fixtures_path),
        "GITHUB_OUTPUT": str(tmp_path / "artifact-output"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "artifact-summary"),
        "GH_TOKEN": "scoped-test-token",
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "REPOSITORY": "joyfulhouse/pylxpweb",
        "RUN_ID": "12345",
    }
    return _run_yaml_script(
        _step("prepare-pypi", "resolve-release-artifact")["run"],
        cwd=tmp_path,
        env=env,
        tmp_path=tmp_path,
        timeout_seconds=15,
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "expired",
        "duplicate",
        "count-mismatch",
        "wrong-envelope",
        "wrong-name",
        "wrong-digest",
        "wrong-action-digest-format",
        "wrong-run",
        "wrong-head",
        "wrong-repository",
    ],
)
def test_prepare_rediscovers_one_exact_nonexpired_run_artifact(
    tmp_path: Path, mutation: str
) -> None:
    """Trusting only stale job outputs can select missing, replaced, or cross-run bytes."""
    name = "pylxpweb-release-1.2.3-aaaaaaaaaaaa"
    digest = "sha256:" + "d" * 64
    fixtures = _artifact_fixture(name, digest)
    page = fixtures["repos/joyfulhouse/pylxpweb/actions/runs/12345/artifacts"]
    artifacts = page["artifacts"]
    artifact = artifacts[0]
    run = fixtures["repos/joyfulhouse/pylxpweb/actions/runs/12345"]
    if mutation == "missing":
        artifacts.clear()
        page["total_count"] = 0
    elif mutation == "expired":
        artifact["expired"] = True
    elif mutation == "duplicate":
        artifacts.append(dict(artifact, id=988))
        page["total_count"] = 2
    elif mutation == "count-mismatch":
        page["total_count"] = 2
    elif mutation == "wrong-envelope":
        fixtures["repos/joyfulhouse/pylxpweb/actions/runs/12345/artifacts"] = artifacts
    elif mutation == "wrong-name":
        artifact["name"] = "attacker-artifact"
    elif mutation == "wrong-digest":
        artifact["digest"] = "sha256:" + "0" * 64
    elif mutation == "wrong-run":
        artifact["workflow_run"]["id"] = 54321
    elif mutation == "wrong-head":
        artifact["workflow_run"]["head_sha"] = "b" * 40
    elif mutation == "wrong-repository":
        run["repository"]["full_name"] = "attacker/pylxpweb"
    expected_digest = "sha256:" + "d" * 64 if mutation == "wrong-action-digest-format" else "d" * 64
    result = _run_artifact_resolution(tmp_path, fixtures, expected_digest=expected_digest)
    assert result.returncode != 0


def test_prepare_accepts_exact_run_artifact_and_binds_download_by_id(tmp_path: Path) -> None:
    """The accepted API identity must drive the immutable artifact download selector."""
    name = "pylxpweb-release-1.2.3-aaaaaaaaaaaa"
    digest = "sha256:" + "d" * 64
    result = _run_artifact_resolution(tmp_path, _artifact_fixture(name, digest))
    assert result.returncode == 0, result.stderr
    output = tmp_path / "artifact-output"
    assert _read_output(output, "artifact-id") == "987"
    summary = (tmp_path / "artifact-summary").read_text()
    assert "987" in summary
    assert name in summary
    assert digest in summary
    download = _step("prepare-pypi", "download-release-artifact")
    assert download["with"]["artifact-ids"] == (
        "${{ steps.resolve-release-artifact.outputs.artifact-id }}"
    )
    assert download["with"]["run-id"] == "${{ github.run_id }}"
    assert download["with"]["digest-mismatch"] == "error"


def test_production_recovery_topology_has_one_terminal_verifier() -> None:
    """Changing conditions can republish exact state, top up partial state, or hide failure."""
    prepare = _job("prepare-pypi")
    publish = _job("publish-pypi")
    verify = _job("verify-pypi")
    assert prepare["environment"] == "pypi"
    assert prepare["outputs"]["state"] == "${{ steps.resolve-prepare-state.outputs.state }}"
    assert _step("prepare-pypi", "stage")["if"] == (
        "steps.resolve-prepare-state.outputs.state == 'ABSENT'"
    )
    assert _step("prepare-pypi", "upload-staging-artifact")["if"] == (
        "steps.resolve-prepare-state.outputs.state == 'ABSENT'"
    )
    assert publish["if"] == "needs.prepare-pypi.outputs.state == 'ABSENT'"
    assert publish["needs"] == "prepare-pypi"
    assert verify["needs"] == ["bind-build-attest", "prepare-pypi", "publish-pypi"]
    assert verify["if"] == (
        "${{ always() && !cancelled() && needs.prepare-pypi.result == 'success' }}"
    )
    assert "needs.publish-pypi.result" not in verify["if"]
    assert (
        _step("verify-pypi", "classify-pypi-state")["run"]
        == _step("prepare-pypi", "classify-pypi-state")["run"]
    )
    terminal = _step("verify-pypi", "require-exact-complete")
    assert terminal["env"]["STATE"] == "${{ steps.classify-pypi-state.outputs.state }}"
    assert "EXACT_COMPLETE" in terminal["run"]
    assert not any("continue-on-error" in step for step in publish["steps"])


_PREPARE_EVIDENCE_STEPS = (
    "resolve-release-artifact",
    "download-release-artifact",
    "verify-release-bundle",
    "classify-pypi-state",
)


def test_prepare_evidence_failures_funnel_into_uncertain_not_job_failure() -> None:
    """A hard prepare failure skips the terminal verifier and hides a lost upload."""
    for step_id in _PREPARE_EVIDENCE_STEPS:
        assert _step("prepare-pypi", step_id).get("continue-on-error") is True
    assert _step("prepare-pypi", "download-release-artifact")["if"] == (
        "steps.resolve-release-artifact.outcome == 'success'"
    )
    assert _step("prepare-pypi", "verify-release-bundle")["if"] == (
        "steps.download-release-artifact.outcome == 'success'"
    )
    assert _step("prepare-pypi", "classify-pypi-state")["if"] == (
        "steps.verify-release-bundle.outcome == 'success'"
    )
    resolver = _step("prepare-pypi", "resolve-prepare-state")
    assert "if" not in resolver
    assert "continue-on-error" not in resolver
    assert resolver["env"]["CLASSIFY_OUTCOME"] == "${{ steps.classify-pypi-state.outcome }}"
    # The terminal verifier must keep failing hard on the same evidence.
    for step_id in _PREPARE_EVIDENCE_STEPS:
        verify_step = _step("verify-pypi", step_id)
        assert "continue-on-error" not in verify_step
        assert "if" not in verify_step
    verify_step_ids = [step.get("id") for step in _job("verify-pypi")["steps"]]
    assert "resolve-prepare-state" not in verify_step_ids


def _run_prepare_state_resolver(
    tmp_path: Path, outcomes: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], str, str]:
    output = tmp_path / "resolver-output"
    summary = tmp_path / "resolver-summary"
    env = os.environ | {
        "CLASSIFIED_REASON": "",
        "CLASSIFIED_STATE": "",
        "CLASSIFY_OUTCOME": "skipped",
        "DOWNLOAD_OUTCOME": "success",
        "GITHUB_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(summary),
        "RESOLVE_OUTCOME": "success",
        "VERIFY_OUTCOME": "success",
    }
    env.update(outcomes)
    result = _run_yaml_script(
        _step("prepare-pypi", "resolve-prepare-state")["run"],
        cwd=tmp_path,
        env=env,
        tmp_path=tmp_path,
        timeout_seconds=15,
    )
    state = _read_output(output, "state") if output.exists() else ""
    reason = _read_output(output, "reason") if output.exists() else ""
    return result, state, reason


@pytest.mark.parametrize(
    "outcomes",
    [
        {"RESOLVE_OUTCOME": "failure"},
        {"DOWNLOAD_OUTCOME": "failure"},
        {"VERIFY_OUTCOME": "failure"},
        {"CLASSIFY_OUTCOME": "failure"},
        {"CLASSIFY_OUTCOME": "skipped"},
        {"CLASSIFY_OUTCOME": "success"},  # succeeded but emitted no state
    ],
)
def test_prepare_state_resolver_reports_uncertain_for_missing_evidence(
    tmp_path: Path, outcomes: dict[str, str]
) -> None:
    """Terminating prepare on evidence failure would skip the sole terminal verifier."""
    result, state, reason = _run_prepare_state_resolver(tmp_path, outcomes)
    assert result.returncode == 0, result.stderr
    assert state == "UNCERTAIN"
    assert reason


@pytest.mark.parametrize("classified_state", ["ABSENT", "EXACT_COMPLETE", "PARTIAL", "UNCERTAIN"])
def test_prepare_state_resolver_passes_through_classified_states(
    tmp_path: Path, classified_state: str
) -> None:
    """The resolver must not invent, drop, or rewrite a genuine classification."""
    result, state, reason = _run_prepare_state_resolver(
        tmp_path,
        {
            "CLASSIFY_OUTCOME": "success",
            "CLASSIFIED_STATE": classified_state,
            "CLASSIFIED_REASON": "classifier evidence reason",
        },
    )
    assert result.returncode == 0, result.stderr
    assert state == classified_state
    assert reason == "classifier evidence reason"


@pytest.mark.parametrize(
    "state",
    [
        "ABSENT",
        "EXACT_COMPLETE",
        "PARTIAL",
        "MISMATCH",
        "YANKED",
        "EXTRA",
        "COMPETING",
        "UNCERTAIN",
    ],
)
def test_terminal_verifier_succeeds_only_for_exact_complete(state: str, tmp_path: Path) -> None:
    """Any other successful terminal state can hide a lost or immutable partial upload."""
    step = _step("verify-pypi", "require-exact-complete")
    result = _run_yaml_script(
        step["run"],
        cwd=_ROOT,
        env=os.environ | {"STATE": state},
        tmp_path=tmp_path,
        timeout_seconds=15,
    )
    assert (result.returncode == 0) is (state == "EXACT_COMPLETE")


def test_production_classifier_worst_case_fits_verifier_timeout() -> None:
    """Bounded ABSENT rechecks and both byte downloads leave five minutes of headroom."""
    job = _job("verify-pypi")
    env = _step("verify-pypi", "classify-pypi-state")["env"]
    attempts = int(env["ABSENT_RECHECK_MAX_ATTEMPTS"])
    retry_base = int(env["ABSENT_RECHECK_BASE_SECONDS"])
    snapshot_pair = 2 * int(env["INDEX_TOTAL_SECONDS"]) + int(env["SNAPSHOT_DELAY_SECONDS"])
    backoff = sum(min(recheck * retry_base, 30) for recheck in range(1, attempts))
    classifier_worst_case = (
        attempts * snapshot_pair + backoff + 2 * int(env["DOWNLOAD_TOTAL_SECONDS"])
    )
    assert int(job["timeout-minutes"]) * 60 - classifier_worst_case >= 300
    assert int(env["SOCKET_TIMEOUT_SECONDS"]) < int(env["INDEX_TOTAL_SECONDS"])
    assert "signal.setitimer" in _step("verify-pypi", "classify-pypi-state")["run"]
    prepare_env = _step("prepare-pypi", "classify-pypi-state")["env"]
    prepare_worst_case = snapshot_pair + 2 * int(prepare_env["DOWNLOAD_TOTAL_SECONDS"])
    assert int(_job("prepare-pypi")["timeout-minutes"]) * 60 - prepare_worst_case >= 300


def test_verify_pypi_retries_absent_but_prepare_classifies_once() -> None:
    """Prepare must keep single-pass semantics; only terminal verification retries.

    A retrying prepare could wait out genuine absence differently than the
    publish gate expects, while a non-retrying terminal verifier fails
    the happy path on routine PyPI index-propagation lag after publish-pypi.
    """
    prepare_env = _step("prepare-pypi", "classify-pypi-state")["env"]
    verify_env = _step("verify-pypi", "classify-pypi-state")["env"]
    assert int(prepare_env["ABSENT_RECHECK_MAX_ATTEMPTS"]) == 1
    assert int(verify_env["ABSENT_RECHECK_MAX_ATTEMPTS"]) > 1
    assert int(verify_env["ABSENT_RECHECK_BASE_SECONDS"]) > 0
    # The retry knob is the only permitted divergence between the two envs.
    divergent = {
        key
        for key in prepare_env.keys() | verify_env.keys()
        if prepare_env.get(key) != verify_env.get(key)
    }
    assert divergent == {"ABSENT_RECHECK_MAX_ATTEMPTS", "ABSENT_RECHECK_BASE_SECONDS"}


def test_pypi_classifier_rechecks_absent_within_bounded_attempts(
    tmp_path: Path,
    package_index_server: tuple[str, dict[str, Any]],
) -> None:
    """An ABSENT snapshot pair is re-taken until stable evidence appears."""
    base_url, server = package_index_server
    _, payload = _prepare_index_case(tmp_path, base_url, server)
    server["index_responses"] = [404, 404, 404, 404, payload, payload]
    result, state = _run_pypi_classifier(
        tmp_path,
        base_url,
        env_overrides={
            "ABSENT_RECHECK_MAX_ATTEMPTS": "5",
            "ABSENT_RECHECK_BASE_SECONDS": "0",
        },
    )
    assert result.returncode == 0, result.stderr
    assert state == "EXACT_COMPLETE"
    assert server["index_calls"] == 6


@pytest.mark.parametrize(
    ("responses", "expected_state", "expected_calls"),
    [
        # Persistent absence exhausts the bounded budget and stays ABSENT.
        ([404, 404, 404, 404, 404, 404], "ABSENT", 6),
        # Snapshot instability is UNCERTAIN and must not consume retry budget.
        ([404, "payload", 404, 404], "UNCERTAIN", 2),
    ],
)
def test_pypi_classifier_absent_recheck_is_bounded_and_absent_only(
    tmp_path: Path,
    package_index_server: tuple[str, dict[str, Any]],
    responses: list[Any],
    expected_state: str,
    expected_calls: int,
) -> None:
    """Only a stable ABSENT pair retries; the per-attempt stability rule survives."""
    base_url, server = package_index_server
    _, payload = _prepare_index_case(tmp_path, base_url, server)
    server["index_responses"] = [payload if item == "payload" else item for item in responses]
    result, state = _run_pypi_classifier(
        tmp_path,
        base_url,
        env_overrides={
            "ABSENT_RECHECK_MAX_ATTEMPTS": "3",
            "ABSENT_RECHECK_BASE_SECONDS": "0",
        },
    )
    assert result.returncode == 0, result.stderr
    assert state == expected_state
    assert server["index_calls"] == expected_calls


def test_production_classifier_pins_https_pypi_index_origin() -> None:
    """An off-origin index redirect could impersonate absence and trigger a republish."""
    for job_id in ("prepare-pypi", "verify-pypi"):
        env = _step(job_id, "classify-pypi-state")["env"]
        assert env["INDEX_JSON_BASE"] == "https://pypi.org/pypi"
        assert env["ALLOWED_INDEX_HOST"] == "pypi.org"
        assert env["REQUIRED_INDEX_SCHEME"] == "https"
        assert env["ALLOWED_FILE_HOST"] == "files.pythonhosted.org"
        assert env["REQUIRED_FILE_SCHEME"] == "https"


def test_prepare_and_verifier_share_artifact_and_remote_evidence_scripts() -> None:
    """Divergent recovery verification can bless evidence normal verification rejects."""
    assert (
        _step("prepare-pypi", "resolve-release-artifact")["run"]
        == _step("verify-pypi", "resolve-release-artifact")["run"]
    )
    assert (
        _step("prepare-pypi", "verify-release-bundle")["run"]
        == _step("verify-pypi", "verify-release-bundle")["run"]
    )
    assert (
        _step("prepare-pypi", "classify-pypi-state")["run"]
        == _step("verify-pypi", "classify-pypi-state")["run"]
    )


def test_only_absent_state_can_reach_action_only_production_publisher() -> None:
    """Any broader publisher guard permits republish or immutable one-file top-up."""
    publish = _job("publish-pypi")
    assert publish["environment"] == "pypi"
    assert publish["permissions"] == {"contents": "read", "id-token": "write"}
    assert publish["if"] == "needs.prepare-pypi.outputs.state == 'ABSENT'"
    assert len(publish["steps"]) == 2
    assert all(set(step) <= {"uses", "with", "name"} for step in publish["steps"])
    assert all("run" not in step for step in publish["steps"])
    assert "skip-existing" not in publish["steps"][1].get("with", {})
    workflow = _workflow()
    production_oidc = [
        job_id
        for job_id, job in workflow["jobs"].items()
        if job.get("permissions", {}).get("id-token") == "write"
        and job.get("environment") == "pypi"
    ]
    assert production_oidc == ["publish-pypi"]
    assert not any("continue-on-error" in job for job in workflow["jobs"].values())
    tolerated = [
        (job_id, step.get("id"))
        for job_id, job in workflow["jobs"].items()
        for step in job["steps"]
        if "continue-on-error" in step
    ]
    # Only prepare-pypi evidence steps may tolerate failure: they funnel into an
    # UNCERTAIN prepare result so the sole terminal verifier still runs and fails.
    assert tolerated == [("prepare-pypi", step_id) for step_id in _PREPARE_EVIDENCE_STEPS]


# CI-only artifact-action contract facts, verified 2026-08-18 against the pinned
# actions' committed sources (evidence, including the verified file hashes, lives
# in .github/WORKFLOWS.md under "Pinned artifact-action contract evidence"):
# - actions/download-artifact `action.yml` declares the `digest-mismatch` input
#   (unknown action inputs are silently ignored, so existence at the exact pin is
#   load-bearing) and `src/download-artifact.ts` selects `resolvedPath` whenever
#   `artifacts.length === 1`, so a single-`artifact-ids` download extracts flat
#   into `path:`, not into a per-artifact subdirectory.
# - actions/upload-artifact `action.yml` declares the `artifact-digest` output and
#   `src/shared/upload-artifact.ts` emits the toolkit's bare-hex SHA-256 (no
#   `sha256:` prefix), matching the workflow's `[0-9a-f]{64}` fullmatch.
_VERIFIED_ARTIFACT_ACTION_CONTRACTS = {
    "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c": (
        "e98559b7a31ba31be4709f20d22102dc2737fa630f69a339eb89981151e505fe"
    ),
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a": (
        "c5979822866a72362e609844b6ebe77d4b7e759af68cc1c2c425dcf51481fab4"
    ),
}


def test_artifact_action_pins_match_recorded_contract_verification() -> None:
    """Every artifact-action pin must carry recorded contract evidence.

    Bumping either pin invalidates the recorded verification of the CI-only
    contract facts above, so the new SHA must be re-verified and both this map
    and the WORKFLOWS.md evidence note updated before the pin can land.
    """
    used = {
        step["uses"]
        for job in _workflow()["jobs"].values()
        for step in job["steps"]
        if step.get("uses", "").split("@")[0]
        in {"actions/download-artifact", "actions/upload-artifact"}
    }
    assert used == set(_VERIFIED_ARTIFACT_ACTION_CONTRACTS)
    evidence = (_ROOT / ".github" / "WORKFLOWS.md").read_text()
    for pin, action_yml_sha256 in _VERIFIED_ARTIFACT_ACTION_CONTRACTS.items():
        assert pin.split("@")[1] in evidence
        assert action_yml_sha256 in evidence
    # The digest binding only holds if every by-id download opts into hard failure.
    for job in _workflow()["jobs"].values():
        for step in job["steps"]:
            if "download-artifact@" in step.get("uses", ""):
                with_options = step.get("with", {})
                if "artifact-ids" in with_options:
                    assert with_options["digest-mismatch"] == "error"


def test_all_release_actions_are_immutable_full_sha_pins() -> None:
    """Replacing any action SHA with a tag restores mutable third-party code."""
    actions = [
        step["uses"]
        for job in _workflow()["jobs"].values()
        for step in job["steps"]
        if "uses" in step
    ]
    assert actions
    assert all(_FULL_SHA_ACTION.fullmatch(action) for action in actions)


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


def test_build_produces_exactly_two_bit_reproducible_distributions(tmp_path: Path) -> None:
    """A second build or nondeterministic input changes the clean-build digest set."""
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")
    subprocess.run(["docker", "info"], capture_output=True, check=True)
    script = _step("bind-build-attest", "build-distributions")["run"]
    commit_epoch = _git(_ROOT, "show", "-s", "--format=%ct", "HEAD")
    build_command = "  uv build --offline"
    assert script.count(build_command) == 1
    script = script.replace(
        build_command,
        f'  test "$SOURCE_DATE_EPOCH" = "{commit_epoch}"\n{build_command}',
    )
    image = _workflow()["env"]["BUILD_IMAGE"]
    source = tmp_path / "source"
    shutil.copytree(
        _ROOT,
        source,
        ignore=shutil.ignore_patterns(".git", ".venv", ".release-test-output-*"),
    )
    outputs: list[dict[str, str]] = []
    for index, ambient_epoch in enumerate(("1", "2000000000"), start=1):
        output = tmp_path / f"output-{index}"
        output.mkdir()
        env = os.environ | {
            "BUILD_IMAGE": image,
            "EXPECTED_COMMIT": _git(_ROOT, "rev-parse", "HEAD"),
            "GITHUB_WORKSPACE": str(source),
            "OUTPUT_DIR": str(output),
            "SOURCE_DATE_EPOCH": ambient_epoch,
        }
        result = _run_yaml_script(
            script,
            cwd=_ROOT,
            env=env,
            tmp_path=tmp_path,
            timeout_seconds=180,
        )
        assert result.returncode == 0, result.stderr
        files = sorted(path for path in output.iterdir() if path.is_file())
        assert sum(path.suffix == ".whl" for path in files) == 1
        assert sum(path.name.endswith(".tar.gz") for path in files) == 1
        assert len(files) == 2
        outputs.append({path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files})
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("mutation", ["backend", "uv", "python"])
def test_build_container_rejects_wrong_backend_or_tool_version(
    tmp_path: Path, mutation: str
) -> None:
    """Removing a version assertion lets a different builder produce release bytes."""
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")
    subprocess.run(["docker", "info"], capture_output=True, check=True)
    image = _workflow()["env"]["BUILD_IMAGE"]
    source = tmp_path / "source"
    shutil.copytree(_ROOT, source, ignore=shutil.ignore_patterns(".git", ".venv"))
    script = _step("bind-build-attest", "build-distributions")["run"]
    if mutation == "backend":
        pyproject = source / "pyproject.toml"
        pyproject.write_text(pyproject.read_text().replace("uv_build==0.9.30", "uv_build==0.9.29"))
    elif mutation == "uv":
        script = script.replace('"uv 0.9.30"', '"uv 9.9.9"')
    elif mutation == "python":
        script = script.replace('"Python 3.13"', '"Python 9.9"')
    output = tmp_path / "output"
    output.mkdir()
    env = os.environ | {
        "BUILD_IMAGE": image,
        "EXPECTED_COMMIT": _git(_ROOT, "rev-parse", "HEAD"),
        "GITHUB_WORKSPACE": str(source),
        "OUTPUT_DIR": str(output),
        "SOURCE_DATE_EPOCH": "1755302400",
    }
    result = _run_yaml_script(
        script,
        cwd=_ROOT,
        env=env,
        tmp_path=tmp_path,
        timeout_seconds=180,
    )
    assert result.returncode != 0


def test_build_container_denies_network_when_workflow_network_flag_is_mutated(
    tmp_path: Path,
) -> None:
    """Removing --network none is detected by the build's live network probe."""
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")
    subprocess.run(["docker", "info"], capture_output=True, check=True)
    image = _workflow()["env"]["BUILD_IMAGE"]
    source = tmp_path / "source"
    shutil.copytree(_ROOT, source, ignore=shutil.ignore_patterns(".git", ".venv"))
    output = tmp_path / "output"
    output.mkdir()
    script = _step("bind-build-attest", "build-distributions")["run"].replace(
        "--network none", "--network bridge"
    )
    env = os.environ | {
        "BUILD_IMAGE": image,
        "EXPECTED_COMMIT": _git(_ROOT, "rev-parse", "HEAD"),
        "GITHUB_WORKSPACE": str(source),
        "OUTPUT_DIR": str(output),
        "SOURCE_DATE_EPOCH": "1755302400",
    }
    result = _run_yaml_script(
        script,
        cwd=_ROOT,
        env=env,
        tmp_path=tmp_path,
        timeout_seconds=180,
    )
    assert result.returncode != 0
