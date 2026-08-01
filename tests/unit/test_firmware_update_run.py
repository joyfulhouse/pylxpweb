"""Unit tests for run_firmware_update_to_completion (eg4_web_monitor#353).

Some devices (6000XP) need standardUpdate/run issued once per firmware
component. The orchestrator loops check → start → poll → re-check until the
device converges; these tests script the device responses to pin every exit
path.
"""

from __future__ import annotations

import asyncio

import pytest

from pylxpweb.devices._firmware_update_mixin import FirmwareUpdateMixin
from pylxpweb.exceptions import LuxpowerAPIError
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
        start_results: list[bool | LuxpowerAPIError] | None = None,
        eligibility: list[bool | LuxpowerAPIError] | None = None,
        failed_statuses: list[bool] | None = None,
    ) -> None:
        self._init_firmware_update_cache()
        # The orchestrator logs against the host's serial (issue #353 chain
        # diagnostics), so the harness must carry one like a real device.
        self.serial_number = "4413740117"
        self._checks = checks
        self._progresses = progresses or []
        self._start_results = start_results or []
        self._eligibility = eligibility or []
        self._failed_statuses = failed_statuses or []
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
            result = self._start_results.pop(0)
            if isinstance(result, LuxpowerAPIError):
                raise result
            return result
        return True

    async def check_update_eligibility(self) -> bool:
        if self._eligibility:
            result = self._eligibility.pop(0)
            if isinstance(result, LuxpowerAPIError):
                raise result
            return result
        return True

    async def _update_step_reported_failed(self) -> bool:
        if self._failed_statuses:
            return self._failed_statuses.pop(0)
        return False


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
async def test_transient_device_busy_rechecks_eligibility_and_retries() -> None:
    """A start race with the previous component must not abort the chain.

    Mid-chain only: the device is settling a component THIS run started, so
    the bounded busy-retry applies (before any step, busy fails fast instead).
    """
    device = ScriptedDevice(
        checks=[STEP1_PENDING, STEP2_PENDING, UP_TO_DATE],
        # step 1 starts cleanly; step 2's start races busy once, then takes.
        start_results=[True, LuxpowerAPIError("deviceBusy"), True],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, busy_grace=60
    )

    assert result.success and result.converged
    assert result.steps_run == 2
    assert device.start_calls == 3


@pytest.mark.asyncio
async def test_inter_step_eligibility_busy_does_not_abort_chain() -> None:
    """A device still settling between components reports not-eligible at the
    inter-step gate; the chain must wait and retry, not abort (issue #353)."""
    installing = _info("ccaa-1E1415", "ccaa-1E1515", in_progress=True)
    done = _info("ccaa-1E1515", "ccaa-1E1515", in_progress=False)
    device = ScriptedDevice(
        checks=[STEP1_PENDING, STEP2_PENDING, UP_TO_DATE],
        progresses=[installing, done, installing, done],
        # step 1 gate eligible; step 2 gate busy once, then eligible.
        eligibility=[True, False, True],
    )

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=60)

    assert result.success and result.converged
    assert result.steps_run == 2
    assert device.start_calls == 2
    assert not device._eligibility  # the busy inter-step gate was re-polled


@pytest.mark.asyncio
async def test_first_step_not_eligible_still_fails_fast_without_write() -> None:
    """Pre-flight (first step) non-eligibility must still fail fast, no write,
    no waiting out the busy budget."""
    device = ScriptedDevice(checks=[STEP1_PENDING], eligibility=[False])

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=60)

    assert not result.success
    assert device.start_calls == 0
    assert "not eligible" in result.message
    assert not device._eligibility


@pytest.mark.asyncio
async def test_busy_error_from_eligibility_is_retried_not_raised() -> None:
    """A busy LuxpowerAPIError raised by the eligibility probe itself must be
    tolerated mid-chain (retried within budget), not escape raw and abort."""
    device = ScriptedDevice(
        checks=[STEP1_PENDING, STEP2_PENDING, UP_TO_DATE],
        # step 1 gate eligible; step 2 gate raises busy once, then eligible.
        eligibility=[True, LuxpowerAPIError("deviceBusy"), True],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, busy_grace=60
    )

    assert result.success and result.converged
    assert result.steps_run == 2
    assert device.start_calls == 2
    assert not device._eligibility  # the busy eligibility probe was re-polled


@pytest.mark.asyncio
async def test_non_busy_error_from_eligibility_propagates() -> None:
    """A non-busy API error from the eligibility probe must propagate."""
    device = ScriptedDevice(
        checks=[STEP1_PENDING],
        eligibility=[LuxpowerAPIError("some other failure")],
    )

    with pytest.raises(LuxpowerAPIError, match="some other failure"):
        await device.run_firmware_update_to_completion(poll_interval=0, start_grace=60)


@pytest.mark.asyncio
async def test_non_busy_error_from_start_propagates() -> None:
    """A non-busy start error (e.g. 'no update available') must NOT be swallowed
    by the busy-retry — it propagates so a genuine failure surfaces."""
    device = ScriptedDevice(
        checks=[STEP1_PENDING],
        start_results=[LuxpowerAPIError("no update available")],
    )

    with pytest.raises(LuxpowerAPIError, match="no update available"):
        await device.run_firmware_update_to_completion(poll_interval=0, start_grace=60)


@pytest.mark.asyncio
async def test_no_start_write_fires_after_deadline_on_retry() -> None:
    """If the eligibility probe on a mid-chain retry straddles the deadline, no
    start write may fire past it — the budget is a hard bound on retry writes."""

    class SlowRetryEligibilityDevice(ScriptedDevice):
        elig_calls = 0

        async def check_update_eligibility(self) -> bool:
            self.elig_calls += 1
            if self.elig_calls >= 3:
                # the step-2 retry probe runs long, past the tiny budget
                await asyncio.sleep(0.2)
            return True

    device = SlowRetryEligibilityDevice(
        checks=[STEP1_PENDING, STEP2_PENDING],
        # step 1 starts cleanly; step 2's start races busy and never recovers.
        start_results=[True, LuxpowerAPIError("deviceBusy")],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, busy_grace=0.1
    )

    assert not result.success
    # Step 1 plus step 2's single in-budget attempt; the retry bailed before
    # writing again.
    assert device.start_calls == 2
    assert "busy" in result.message.casefold()


@pytest.mark.parametrize(
    "message",
    [
        "deviceBusy",
        "device busy",
        "DEVICE_BUSY",
        # A start-call TOCTOU race can report the device/parallel-group as
        # already updating; these busy-family codes AND their standardUpdate/run
        # prose variants must also be tolerated, not escape raw (issue #353).
        "deviceUpdating",
        "parallelGroupUpdating",
        "Device is already updating",
        "Another device in the parallel group is updating",
    ],
)
@pytest.mark.asyncio
async def test_device_busy_past_start_budget_returns_clean_failure(message: str) -> None:
    """A persistent MID-CHAIN busy response exhausts its budget without
    escaping raw (before any step, busy fails fast instead — see
    test_first_start_busy_error_fails_fast)."""

    class BusyAfterFirstStepDevice(ScriptedDevice):
        async def start_firmware_update(self, try_fast_mode: bool = False) -> bool:
            self.start_calls += 1
            if self.start_calls == 1:
                return True
            raise LuxpowerAPIError(message)

    device = BusyAfterFirstStepDevice(checks=[STEP1_PENDING, STEP2_PENDING])

    # A budget wide enough for several retries within it, so we verify the loop
    # retries multiple times AND stops cleanly at the deadline (no write past it).
    result = await device.run_firmware_update_to_completion(
        poll_interval=0.02, start_grace=0, busy_grace=0.2
    )

    assert not result.success and not result.converged
    assert result.steps_run == 1
    assert device.start_calls > 2
    assert "busy" in result.message.casefold()


@pytest.mark.asyncio
async def test_no_progress_after_step_aborts() -> None:
    """A completed run with no version delta must stop, not loop writes."""
    device = ScriptedDevice(checks=[STEP1_PENDING, STEP1_PENDING])

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, settle_checks=0
    )

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
        poll_interval=0, max_steps=2, start_grace=0, settle_checks=0
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


@pytest.mark.asyncio
async def test_failed_step_stops_the_chain() -> None:
    """A step the server reports as FAILED must abort — even if versions
    advanced partially, firing another run against a failed chain is the
    blind-write class this orchestrator exists to prevent (codex P1)."""
    device = ScriptedDevice(
        # Post-FAILED re-check shows a partial advance (1414 -> 1415): the
        # result must report the actual current version, not the pre-step one.
        checks=[STEP1_PENDING, STEP2_PENDING],
        failed_statuses=[True],
    )

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert not result.success and not result.converged
    assert result.steps_run == 1
    assert device.start_calls == 1
    assert "FAILED" in result.message
    assert result.final_version == "ccaa-1E1415"


@pytest.mark.asyncio
async def test_settle_window_recovers_lagging_check_data() -> None:
    """The check endpoint can lag the status endpoint: an unchanged version
    on the immediate re-check must retry within the settle window instead of
    declaring no progress (codex P2)."""
    device = ScriptedDevice(
        checks=[STEP1_PENDING, STEP1_PENDING, STEP2_PENDING, UP_TO_DATE],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, settle_checks=2, settle_interval=0
    )

    assert result.success and result.converged
    assert result.steps_run == 2  # lagging first re-check did not abort step 1


@pytest.mark.asyncio
async def test_prefix_only_progress_is_progress() -> None:
    """A step that advances only the leading prefix byte (ccaa-1D -> ccaa-1E)
    with unchanged trailing v1/v2 counts as progress — the comparison uses
    the full installed code, not just the (v1, v2) pair (codex P1)."""
    before = _info("ccaa-1D1415", "ccaa-1E1515", app_current=0x14, param_current=0x15)
    after = _info("ccaa-1E1415", "ccaa-1E1515", app_current=0x14, param_current=0x15)
    device = ScriptedDevice(checks=[before, after, UP_TO_DATE])

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, settle_checks=0
    )

    assert result.success and result.converged
    assert result.steps_run == 2


def test_scripted_device_is_mixin() -> None:
    """Guard: the scripted host really exercises the production mixin method."""
    assert (
        ScriptedDevice.run_firmware_update_to_completion
        is FirmwareUpdateMixin.run_firmware_update_to_completion
    )


@pytest.mark.asyncio
async def test_converged_final_version_survives_up_to_date_sentinel() -> None:
    """When the post-step check answers with the bare 'already latest'
    sentinel (empty version strings), the result reports the target we
    converged to, not an empty string (agy review finding)."""
    sentinel = _info("", "")  # create_up_to_date shape: both fields empty
    device = ScriptedDevice(checks=[STEP2_PENDING, sentinel])

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert result.success and result.converged
    assert result.final_version == "ccaa-1E1515"


@pytest.mark.asyncio
async def test_every_progress_poll_is_forced() -> None:
    """Regression pin (post-beta.1 scan P1): get_firmware_update_progress
    caches a not-in-progress snapshot for 5 MINUTES, so any unforced poll
    inside the orchestrator would replay the pre-registration idle snapshot
    for the whole start-grace window and abandon a genuinely running step
    as "no progress". Every poll must bypass the cache."""
    forced_flags: list[bool] = []

    class ForceRecordingDevice(ScriptedDevice):
        async def get_firmware_update_progress(self, force: bool = False) -> FirmwareUpdateInfo:
            forced_flags.append(force)
            return await super().get_firmware_update_progress(force)

    installing = _info("ccaa-1E1414", "ccaa-1E1515", in_progress=True)
    done = _info("ccaa-1E1415", "ccaa-1E1515", in_progress=False)
    device = ForceRecordingDevice(
        checks=[STEP2_PENDING, UP_TO_DATE],
        progresses=[installing, installing, done],
    )

    result = await device.run_firmware_update_to_completion(poll_interval=0)

    assert result.success
    assert forced_flags and all(forced_flags)


# --- Partial-upgrade skip (issue #353 round 3) -----------------------------
#
# eode's 6000XP sat at ccaa-1E1415 with target ccaa-1E1515. standardUpdate/run
# takes no component selector, so the server picked the component already at
# the target: it downloaded and flashed normally (the entity showed 0% -> 100%)
# but COULD NOT move the version string. Aborting on that first unchanged
# version meant the component that actually needed 14 -> 15 never ran, and
# every retry reproduced the same loop.

# A step that visibly installs but leaves the version untouched.
NOOP_INSTALLING = _info("ccaa-1E1415", "ccaa-1E1515", in_progress=True)
NOOP_DONE = _info("ccaa-1E1415", "ccaa-1E1515", in_progress=False)


@pytest.mark.asyncio
async def test_no_op_component_does_not_end_the_chain() -> None:
    """The #353 partial-upgrade case: step 1 re-flashes an already-current
    component (visible install, no version change), step 2 finishes the job."""
    device = ScriptedDevice(
        checks=[STEP2_PENDING, STEP2_PENDING, UP_TO_DATE],
        progresses=[NOOP_INSTALLING, NOOP_DONE, NOOP_INSTALLING, NOOP_DONE],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, settle_checks=0
    )

    assert result.success and result.converged
    assert result.steps_run == 2
    assert device.start_calls == 2
    assert result.final_version == "ccaa-1E1515"


@pytest.mark.asyncio
async def test_no_progress_grace_is_not_unlimited() -> None:
    """A genuinely stuck device still stops: the grace excuses ONE consecutive
    unchanged step, not an open-ended run of firmware writes."""
    device = ScriptedDevice(
        checks=[STEP2_PENDING, STEP2_PENDING, STEP2_PENDING],
        progresses=[NOOP_INSTALLING, NOOP_DONE] * 2,
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, settle_checks=0
    )

    assert not result.success and not result.converged
    assert result.steps_run == 2
    assert device.start_calls == 2  # no third write
    assert "No firmware version progress after step 2" in result.message


@pytest.mark.asyncio
async def test_no_progress_grace_zero_restores_immediate_abort() -> None:
    """no_progress_grace=0 is the pre-#353 behaviour: abort on the first
    unchanged version, one write only."""
    device = ScriptedDevice(
        checks=[STEP2_PENDING, STEP2_PENDING],
        progresses=[NOOP_INSTALLING, NOOP_DONE],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, settle_checks=0, no_progress_grace=0
    )

    assert not result.success
    assert result.steps_run == 1
    assert device.start_calls == 1


@pytest.mark.asyncio
async def test_unobserved_step_is_not_excused_by_the_grace() -> None:
    """The grace requires positive evidence the step ran: a step that never
    became visible as installing must NOT authorize another firmware write."""
    device = ScriptedDevice(
        # start_grace=0 with no in-progress poll => saw_in_progress stays False
        checks=[STEP2_PENDING, STEP2_PENDING],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, settle_checks=0
    )

    assert not result.success
    assert result.steps_run == 1
    assert device.start_calls == 1  # grace available, but unearned
    assert "No firmware version progress after step 1" in result.message


@pytest.mark.asyncio
async def test_failed_step_still_aborts_with_grace_available() -> None:
    """A server-reported FAILED step outranks the no-progress grace."""
    device = ScriptedDevice(
        checks=[STEP2_PENDING, STEP2_PENDING],
        progresses=[NOOP_INSTALLING, NOOP_DONE],
        failed_statuses=[True],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, settle_checks=0
    )

    assert not result.success and not result.converged
    assert result.steps_run == 1
    assert device.start_calls == 1
    assert "FAILED" in result.message


# --- Pre-flight busy fails fast (issue #353 round 3) -----------------------


@pytest.mark.asyncio
async def test_first_eligibility_busy_error_fails_fast() -> None:
    """A device already busy when the user asks must be reported immediately,
    not after the multi-minute mid-chain retry budget."""
    device = ScriptedDevice(
        checks=[STEP2_PENDING],
        eligibility=[LuxpowerAPIError("deviceBusy")],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, busy_grace=600
    )

    assert not result.success and not result.converged
    assert result.steps_run == 0
    assert device.start_calls == 0
    assert not device._eligibility  # probed exactly once, no re-poll
    assert "busy" in result.message.casefold()
    assert result.final_version == "ccaa-1E1415"


@pytest.mark.asyncio
async def test_first_start_busy_error_fails_fast() -> None:
    """Eligibility can pass and the start still lose the race to a busy
    device; before any step that is also an immediate stop, one write only."""
    device = ScriptedDevice(
        checks=[STEP2_PENDING],
        start_results=[LuxpowerAPIError("deviceBusy")],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, busy_grace=600
    )

    assert not result.success and not result.converged
    assert result.steps_run == 0
    assert device.start_calls == 1  # the one attempt, then stop
    assert "busy" in result.message.casefold()


@pytest.mark.asyncio
async def test_pre_flight_busy_does_not_wait_out_the_budget() -> None:
    """Pin the UX complaint itself: the fast-fail must return promptly even
    when a large busy budget is configured."""
    device = ScriptedDevice(
        checks=[STEP2_PENDING],
        eligibility=[LuxpowerAPIError("deviceBusy")],
    )

    started = asyncio.get_running_loop().time()
    result = await device.run_firmware_update_to_completion(
        poll_interval=30, start_grace=300, busy_grace=900
    )
    elapsed = asyncio.get_running_loop().time() - started

    assert not result.success
    assert elapsed < 1.0  # not the 900s budget, and not one 30s backoff


@pytest.mark.asyncio
async def test_mid_chain_already_latest_start_error_reports_convergence() -> None:
    """If the check endpoint lags a successful final step, the grace can ask
    for one step too many; the server's 'already the latest version' refusal
    is convergence, not an error to surface after a successful update."""
    device = ScriptedDevice(
        checks=[STEP1_PENDING, STEP2_PENDING],
        start_results=[
            True,
            LuxpowerAPIError(
                "API error (HTTP 200): The current machine firmware is already the latest version"
            ),
        ],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, settle_checks=0
    )

    assert result.success and result.converged
    assert result.steps_run == 1
    assert result.final_version == "ccaa-1E1515"


@pytest.mark.asyncio
async def test_pre_flight_already_latest_start_error_still_propagates() -> None:
    """Before any step, check-says-update / run-says-latest is a genuine
    endpoint disagreement about an untouched device and must still surface."""
    device = ScriptedDevice(
        checks=[STEP2_PENDING],
        start_results=[LuxpowerAPIError("already the latest version")],
    )

    with pytest.raises(LuxpowerAPIError, match="already the latest version"):
        await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)
