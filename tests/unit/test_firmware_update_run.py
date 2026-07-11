"""Unit tests for run_firmware_update_to_completion (eg4_web_monitor#353).

Some devices (6000XP) need standardUpdate/run issued once per firmware
component. The orchestrator loops check → start → poll → re-check until the
device converges; these tests script the device responses to pin every exit
path.
"""

from __future__ import annotations

import pytest

from pylxpweb.devices._firmware_update_mixin import FirmwareUpdateMixin
from pylxpweb.models import FirmwareUpdateInfo


def _info(
    installed: str,
    latest: str,
    *,
    in_progress: bool = False,
    app_current: int | None = None,
    param_current: int | None = None,
) -> FirmwareUpdateInfo:
    return FirmwareUpdateInfo(
        installed_version=installed,
        latest_version=latest,
        title="Test Firmware",
        release_summary=None,
        release_url=None,
        in_progress=in_progress,
        update_percentage=None,
        app_version_current=app_current,
        param_version_current=param_current,
    )


class ScriptedDevice(FirmwareUpdateMixin):
    """Mixin host with scripted firmware API responses."""

    def __init__(
        self,
        *,
        checks: list[FirmwareUpdateInfo],
        progresses: list[FirmwareUpdateInfo] | None = None,
        start_results: list[bool] | None = None,
        eligibility: list[bool] | None = None,
    ) -> None:
        self._init_firmware_update_cache()
        self._checks = checks
        self._progresses = progresses or []
        self._start_results = start_results or []
        self._eligibility = eligibility or []
        self.start_calls = 0
        self.check_calls = 0

    # Scripted overrides -------------------------------------------------
    async def check_firmware_updates(self, force: bool = False) -> FirmwareUpdateInfo:
        self.check_calls += 1
        return self._checks.pop(0)

    async def get_firmware_update_progress(self, force: bool = False) -> FirmwareUpdateInfo:
        if self._progresses:
            return self._progresses.pop(0)
        return _info("X-0000", "X-0000")

    async def start_firmware_update(self, try_fast_mode: bool = False) -> bool:
        self.start_calls += 1
        if self._start_results:
            return self._start_results.pop(0)
        return True

    async def check_update_eligibility(self) -> bool:
        if self._eligibility:
            return self._eligibility.pop(0)
        return True


UP_TO_DATE = _info("ccaa-1E1515", "ccaa-1E1515", app_current=0x15, param_current=0x15)
STEP1_PENDING = _info("ccaa-1E1414", "ccaa-1E1515", app_current=0x14, param_current=0x14)
STEP2_PENDING = _info("ccaa-1E1415", "ccaa-1E1515", app_current=0x14, param_current=0x15)


@pytest.mark.asyncio
async def test_already_up_to_date_runs_nothing() -> None:
    device = ScriptedDevice(checks=[UP_TO_DATE])

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert result.success and result.converged
    assert result.steps_run == 0
    assert device.start_calls == 0
    assert result.final_version == "ccaa-1E1515"


@pytest.mark.asyncio
async def test_single_step_convergence() -> None:
    device = ScriptedDevice(checks=[STEP2_PENDING, UP_TO_DATE])

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert result.success and result.converged
    assert result.steps_run == 1
    assert device.start_calls == 1


@pytest.mark.asyncio
async def test_multi_step_chain_converges() -> None:
    """The #353 scenario: step 1 advances param only; step 2 finishes app."""
    device = ScriptedDevice(checks=[STEP1_PENDING, STEP2_PENDING, UP_TO_DATE])

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert result.success and result.converged
    assert result.steps_run == 2
    assert device.start_calls == 2
    assert result.final_version == "ccaa-1E1515"


@pytest.mark.asyncio
async def test_start_refused_reports_failure() -> None:
    device = ScriptedDevice(checks=[STEP1_PENDING], start_results=[False])

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert not result.success and not result.converged
    assert result.steps_run == 1
    assert "refused" in result.message


@pytest.mark.asyncio
async def test_not_eligible_reports_failure_without_write() -> None:
    device = ScriptedDevice(checks=[STEP1_PENDING], eligibility=[False])

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert not result.success
    assert device.start_calls == 0
    assert "not eligible" in result.message


@pytest.mark.asyncio
async def test_no_progress_after_step_aborts() -> None:
    """A completed run with no version delta must stop, not loop writes."""
    device = ScriptedDevice(checks=[STEP1_PENDING, STEP1_PENDING])

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert not result.success
    assert result.steps_run == 1
    assert "No firmware version progress" in result.message


@pytest.mark.asyncio
async def test_step_budget_exhaustion() -> None:
    """Distinct-but-never-converging versions stop at max_steps."""
    checks: list[FirmwareUpdateInfo] = [
        _info("X-0001", "X-9999", app_current=1, param_current=1),
        _info("X-0002", "X-9999", app_current=2, param_current=2),
        _info("X-0003", "X-9999", app_current=3, param_current=3),
    ]
    device = ScriptedDevice(checks=checks)

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, max_steps=2, start_grace=0
    )

    assert not result.success
    assert result.steps_run == 2
    assert "step budget" in result.message


@pytest.mark.asyncio
async def test_polls_installing_step_until_done() -> None:
    """in_progress=True progress responses are polled through before the
    post-step re-check runs."""
    installing = _info("ccaa-1E1414", "ccaa-1E1515", in_progress=True)
    idle = _info("ccaa-1E1415", "ccaa-1E1515", in_progress=False)
    device = ScriptedDevice(
        checks=[STEP2_PENDING, UP_TO_DATE],
        progresses=[installing, installing, idle],
    )

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert result.success
    assert not device._progresses  # all scripted progress states consumed


@pytest.mark.asyncio
async def test_step_timeout_aborts() -> None:
    installing = _info("ccaa-1E1414", "ccaa-1E1515", in_progress=True)
    device = ScriptedDevice(
        checks=[STEP1_PENDING],
        progresses=[installing] * 50,
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, step_timeout=0.0, start_grace=0
    )

    assert not result.success
    assert "did not finish" in result.message


@pytest.mark.asyncio
async def test_idle_polls_within_grace_do_not_end_the_wait() -> None:
    """The server registers an accepted run asynchronously: idle progress
    polls straight after start must NOT be read as instant completion while
    the visibility grace is open (the mid-flash false-abort race)."""
    idle = _info("ccaa-1E1414", "ccaa-1E1515", in_progress=False)
    installing = _info("ccaa-1E1414", "ccaa-1E1515", in_progress=True)
    done = _info("ccaa-1E1415", "ccaa-1E1515", in_progress=False)
    device = ScriptedDevice(
        checks=[STEP2_PENDING, UP_TO_DATE],
        progresses=[idle, idle, installing, done],
    )

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=60)

    assert result.success and result.converged
    assert not device._progresses  # idle polls were tolerated, wait continued


@pytest.mark.asyncio
async def test_grace_expiry_with_completed_fast_step_still_converges() -> None:
    """A step that genuinely finishes between polls (update never became
    visible before grace expiry) is resolved by the post-step re-check."""
    device = ScriptedDevice(checks=[STEP2_PENDING, UP_TO_DATE])

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert result.success and result.converged
    assert result.steps_run == 1


def test_scripted_device_is_mixin() -> None:
    """Guard: the scripted host really exercises the production mixin method."""
    assert (
        ScriptedDevice.run_firmware_update_to_completion
        is FirmwareUpdateMixin.run_firmware_update_to_completion
    )
