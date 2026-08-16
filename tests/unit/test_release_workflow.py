"""Structural contract tests for the package release workflow."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml"
_FULL_SHA_ACTION = re.compile(r"^[^\s@]+@[0-9a-f]{40}$")


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
    workflow = _workflow()
    steps = _steps_by_id(_job(workflow, "build"))

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
        "ALLOWED_WHEEL_HOST": "test-files.pythonhosted.org",
        "EXPECTED_PROJECT_NAME": "${{ needs.build.outputs.project-name }}",
        "EXPECTED_VERSION": "${{ needs.build.outputs.version }}",
        "MAX_ATTEMPTS": "12",
        "TESTPYPI_JSON_BASE_URL": "https://test.pypi.org/pypi",
    }
    assert steps["install-testpypi-wheel"]["env"] == {
        "PYPI_INDEX_URL": "https://pypi.org/simple",
        "WHEEL_PATH": "${{ steps.query-testpypi.outputs.wheel-path }}",
    }
    assert steps["verify-installed-package"]["env"] == {
        "EXPECTED_PROJECT_NAME": "${{ needs.build.outputs.project-name }}",
        "EXPECTED_VERSION": "${{ needs.build.outputs.version }}",
    }


def test_publishers_use_trusted_publishing_with_skip_only_on_testpypi() -> None:
    """Production must fail on an existing file instead of silently skipping it."""
    workflow = _workflow()
    test_publish = _steps_by_id(_job(workflow, "publish-testpypi"))["publish-testpypi"]
    production_publish = _steps_by_id(_job(workflow, "publish-pypi"))["publish-pypi"]

    assert test_publish["with"] == {
        "packages-dir": "release-bundle/dist/",
        "repository-url": "https://test.pypi.org/legacy/",
        "skip-existing": True,
    }
    assert production_publish["with"] == {"packages-dir": "release-bundle/dist/"}


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
