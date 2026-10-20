"""CI permissions and remote-write boundaries."""

import re
from pathlib import Path

import yaml


def test_ci_permissions_and_actions() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())
    assert workflow["permissions"] == {"contents": "read"}
    for job in workflow["jobs"].values():
        assert "permissions" not in job
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[\w-]+/[\w-]+@[a-f0-9]{40}", step["uses"])


def test_ci_excludes_remote_control_tests() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())
    commands = [s.get("run", "") for s in workflow["jobs"]["integration"]["steps"]]
    test_command = next(command for command in commands if "pytest" in command)
    assert '-m "integration and not control"' in test_command
