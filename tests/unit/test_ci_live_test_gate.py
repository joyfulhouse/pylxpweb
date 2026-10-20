"""Keep ordinary CI from exercising real device or plant controls."""

from pathlib import Path

import yaml


def test_live_integration_tests_require_explicit_manual_opt_in() -> None:
    workflow = yaml.safe_load((Path(__file__).parents[2] / ".github/workflows/ci.yml").read_text())
    # PyYAML's YAML 1.1 resolver treats the GitHub Actions `on` key as True.
    triggers = workflow[True]
    opt_in = triggers["workflow_dispatch"]["inputs"]["run_live_tests"]
    assert opt_in["type"] == "boolean"
    assert opt_in["default"] is False
    assert workflow["jobs"]["integration"]["if"] == (
        "github.event_name == 'workflow_dispatch' && inputs.run_live_tests == true"
    )
    assert "integration" in workflow["jobs"]["ci-success"]["needs"]
