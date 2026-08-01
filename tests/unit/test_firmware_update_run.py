"""Unit tests for run_firmware_update_to_completion (eg4_web_monitor#353).

Some devices (6000XP) need standardUpdate/run issued once per firmware
component. The orchestrator loops check → start → poll → re-check until the
device converges; these tests script the device responses to pin every exit
path.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pylxpweb.devices._firmware_update_mixin import (
    _MAX_START_ATTEMPTS_PER_STEP,
    FirmwareUpdateMixin,
)
from pylxpweb.exceptions import LuxpowerAPIError
from pylxpweb.models import (
    FirmwareDeviceInfo,
    FirmwareUpdateInfo,
    UpdateEligibilityMessage,
    UpdateEligibilityStatus,
    UpdateStatus,
)


def _info(
    installed: str,
    latest: str,
    *,
    in_progress: bool = False,
    app_current: int | None = None,
    param_current: int | None = None,
    latest_override: str | None = None,
) -> FirmwareUpdateInfo:
    return FirmwareUpdateInfo(
        installed_version=installed,
        latest_version=latest_override if latest_override is not None else latest,
        title="Test Firmware",
        release_summary=None,
        release_url=None,
        in_progress=in_progress,
        update_percentage=None,
        app_version_current=app_current,
        param_version_current=param_current,
    )


def _row(
    *,
    start_time: str,
    in_progress: bool,
    serial: str = "4413740117",
) -> FirmwareDeviceInfo:
    """A ``remoteUpdate/info`` row, in-progress or idle.

    ``startTime`` is the only field that distinguishes one update run from the
    next, which is what lets the orchestrator tell its own step's activity
    from a leftover row (the stale-evidence guard).
    """
    return FirmwareDeviceInfo(
        inverterSn=serial,
        startTime=start_time,
        stopTime="" if in_progress else "2026-08-01 10:00:00",
        standardUpdate=True,
        firmware="ccaa-1E1415",
        firmwareType="STANDARD",
        updateStatus=UpdateStatus.UPLOADING if in_progress else UpdateStatus.COMPLETE,
        isSendStartUpdate=True,
        isSendEndUpdate=not in_progress,
        packageIndex=1,
        updateRate="50% - 280 / 561" if in_progress else "",
    )


class ScriptedDevice(FirmwareUpdateMixin):
    """Mixin host with scripted firmware API responses."""

    def __init__(
        self,
        *,
        checks: list[FirmwareUpdateInfo],
        progresses: list[FirmwareUpdateInfo] | None = None,
        start_results: list[bool | LuxpowerAPIError] | None = None,
        eligibility: list[bool | LuxpowerAPIError | UpdateEligibilityMessage] | None = None,
        failed_statuses: list[bool] | None = None,
        status_rows: list[FirmwareDeviceInfo | None] | None = None,
        firmware_codes: list[str | None] | None = None,
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
        # When None, status rows are SYNTHESISED to model a well-behaved
        # server: each accepted start opens a new record (a fresh startTime),
        # and the row is in-progress whenever the last progress poll was.
        # Tests that need a misbehaving server (a stale row that never
        # changes) script the rows explicitly.
        self._status_rows = status_rows
        self._firmware_codes = firmware_codes
        self._device_code: str | None = None
        self._run_seq = 0
        self._last_progress_in_progress = False
        self.start_calls = 0
        self.check_calls = 0
        self.eligibility_calls = 0
        self.check_force_flags: list[bool] = []

    # Scripted overrides -------------------------------------------------
    async def check_firmware_updates(self, force: bool = False) -> FirmwareUpdateInfo:
        self.check_calls += 1
        self.check_force_flags.append(force)
        info = self._checks.pop(0)
        if info.installed_version:
            # A device whose runtime endpoint agrees with the check endpoint.
            self._device_code = info.installed_version
        return info

    async def get_firmware_update_progress(self, force: bool = False) -> FirmwareUpdateInfo:
        info = self._progresses.pop(0) if self._progresses else _info("X-0000", "X-0000")
        self._last_progress_in_progress = info.in_progress
        # Production caches the raw row it just fetched so the orchestrator can
        # attribute activity without a second call; the harness must too, or it
        # tests a seam the real code does not have.
        self._last_status_row = await self._next_status_row()
        return info

    async def start_firmware_update(self, try_fast_mode: bool = False) -> bool:
        self.start_calls += 1
        if self._start_results:
            result = self._start_results.pop(0)
            if isinstance(result, LuxpowerAPIError):
                raise result
            if result:
                self._run_seq += 1
            return result
        self._run_seq += 1
        return True

    async def _update_eligibility_status(self) -> UpdateEligibilityStatus:
        self.eligibility_calls += 1
        result: bool | LuxpowerAPIError | UpdateEligibilityMessage = True
        if self._eligibility:
            result = self._eligibility.pop(0)
        if isinstance(result, LuxpowerAPIError):
            raise result
        if isinstance(result, UpdateEligibilityMessage):
            return UpdateEligibilityStatus(success=True, msg=result)
        return UpdateEligibilityStatus(
            success=True,
            msg=(
                UpdateEligibilityMessage.ALLOW_TO_UPDATE
                if result
                # Not-allowed defaults to the TRANSIENT code: a permanent
                # refusal has its own message and its own tests.
                else UpdateEligibilityMessage.DEVICE_UPDATING
            ),
        )

    async def _next_status_row(self) -> FirmwareDeviceInfo | None:
        if self._status_rows is not None:
            return self._status_rows.pop(0) if self._status_rows else None
        return _row(
            start_time=f"run-{self._run_seq}",
            in_progress=self._last_progress_in_progress,
        )

    async def _current_status_row(self) -> FirmwareDeviceInfo | None:
        return await self._next_status_row()

    async def _read_device_firmware_code(self) -> str | None:
        """The version the DEVICE reports, independent of checkUpdates.

        Scripted when a test needs the two sources to disagree; otherwise it
        models a device that agrees with the last concrete version the check
        endpoint reported (the sentinel's empty string is not a version).
        """
        if self._firmware_codes is not None:
            return self._firmware_codes.pop(0) if self._firmware_codes else None
        return self._device_code

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
    # steps_run counts steps the SERVER ACCEPTED. A refused start installed
    # nothing, so it must not be counted — the docstring and
    # FirmwareUpdateRunResult both promise that.
    assert result.steps_run == 0
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
        start_results=[True, LuxpowerAPIError("API error (HTTP 200): deviceBusy"), True],
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
        eligibility=[True, LuxpowerAPIError("API error (HTTP 200): deviceBusy"), True],
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
        async def _update_eligibility_status(self) -> UpdateEligibilityStatus:
            status = await super()._update_eligibility_status()
            if self.eligibility_calls >= 3:
                # the step-2 retry probe runs long, past the tiny budget
                await asyncio.sleep(0.2)
            return status

    device = SlowRetryEligibilityDevice(
        checks=[STEP1_PENDING, STEP2_PENDING],
        # step 1 starts cleanly; step 2's start races busy and never recovers.
        start_results=[True, LuxpowerAPIError("API error (HTTP 200): deviceBusy")],
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
        "API error (HTTP 200): deviceBusy",
        "API error (HTTP 200): device busy",
        "API error (HTTP 200): DEVICE_BUSY",
        # A start-call TOCTOU race can report the device/parallel-group as
        # already updating; these busy-family codes AND their standardUpdate/run
        # prose variants must also be tolerated, not escape raw (issue #353).
        "API error (HTTP 200): deviceUpdating",
        "API error (HTTP 200): parallelGroupUpdating",
        "API error (HTTP 200): Device is already updating",
        "HTTP 500: Another device in the parallel group is updating",
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
async def test_up_to_date_sentinel_with_corroboration_is_convergence() -> None:
    """The sentinel IS the documented answer for a converged device.

    ``checkUpdates`` answers an up-to-date device with success:false "already
    the latest version", which the client synthesizes into a record whose
    installed_version is EMPTY. Demanding a concrete version from that answer
    alone reported a device as FAILED at the exact moment it succeeded. The
    sentinel is corroborated against the runtime endpoint's fwCode instead: if
    the device really is on the target, that is convergence.
    """
    sentinel = _info("", "")  # create_up_to_date shape: both fields empty
    device = ScriptedDevice(
        checks=[STEP2_PENDING, sentinel],
        # First read is the pre-run baseline (same source as the
        # corroboration, so the movement test is fwCode-to-fwCode); then the
        # device really did converge.
        firmware_codes=["ccaa-1E1415", "ccaa-1E1515"],
    )

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert result.success and result.converged
    assert result.final_version == "ccaa-1E1515"


@pytest.mark.asyncio
async def test_sentinel_is_not_trusted_when_the_device_says_otherwise() -> None:
    """The complement, and the round-2 finding this must not undo: a sentinel
    while the device is still on the version we started from is a transient
    answer, not convergence — so it must not be reported as success."""
    sentinel = _info("", "")
    device = ScriptedDevice(
        checks=[STEP2_PENDING, sentinel, sentinel, sentinel],
        # Device still reads the pre-run version every time it is asked.
        firmware_codes=["ccaa-1E1415"] * 6,
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, settle_checks=0
    )

    assert not result.success and not result.converged


@pytest.mark.asyncio
async def test_corroborated_move_counts_even_if_it_misses_the_target_string() -> None:
    """The target can be a reconstruction the server never echoes.

    ``from_api_response`` splices version bytes onto the firmware code, and for
    unverified layouts that splice is a guess. If the device moved and the
    server says nothing further is available, accept the device's own reported
    version rather than failing on a string mismatch with our own guess.
    """
    sentinel = _info("", "")
    device = ScriptedDevice(
        checks=[STEP2_PENDING, sentinel],
        # Baseline, then moved — but not to the spliced target string.
        firmware_codes=["ccaa-1E1415", "ccaa-1E15FF"],
    )

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert result.success and result.converged
    assert result.final_version == "ccaa-1E15FF"
    # The message must report what was actually observed and must NOT claim
    # the device reached the target, which this path never verified.
    assert "no further updates" in result.message
    assert "now at ccaa-1E15FF" in result.message
    assert "did not echo back" in result.message


@pytest.mark.asyncio
async def test_convergence_is_indeterminate_without_corroboration() -> None:
    """If the device's version cannot be read back, say so — without implying
    the update failed, because it most likely did not."""
    sentinel = _info("", "")
    device = ScriptedDevice(
        checks=[STEP2_PENDING, sentinel],
        firmware_codes=[None, None],  # runtime read unavailable throughout
    )

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert not result.success and not result.converged
    assert "verify the firmware version on the device" in result.message
    assert "may well have completed" in result.message


@pytest.mark.asyncio
async def test_version_match_is_case_insensitive() -> None:
    """The API is not consistent about case; that is not a version difference."""
    sentinel = _info("", "")
    device = ScriptedDevice(
        checks=[STEP2_PENDING, sentinel],
        firmware_codes=["ccaa-1E1415", "CCAA-1E1515"],
    )

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert result.success and result.converged


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
        poll_interval=0, start_grace=60, settle_checks=0, no_progress_grace=1
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
        eligibility=[LuxpowerAPIError("API error (HTTP 200): deviceBusy")],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, busy_grace=600
    )

    assert not result.success and not result.converged
    assert result.steps_run == 0
    assert device.start_calls == 0
    assert device.eligibility_calls == 1  # probed once, no re-poll
    assert "busy" in result.message.casefold()
    assert result.final_version == "ccaa-1E1415"


@pytest.mark.asyncio
async def test_first_start_busy_error_fails_fast() -> None:
    """Eligibility can pass and the start still lose the race to a busy
    device; before any step that is also an immediate stop, one write only."""
    device = ScriptedDevice(
        checks=[STEP2_PENDING],
        start_results=[LuxpowerAPIError("API error (HTTP 200): deviceBusy")],
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
        eligibility=[LuxpowerAPIError("API error (HTTP 200): deviceBusy")],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=30, start_grace=300, busy_grace=900
    )

    # Structural, not wall-clock: the point is that it does not RETRY, and a
    # timing assertion would both flake under load and pass for the wrong
    # reason if the retry loop were merely fast.
    assert not result.success
    assert device.eligibility_calls == 1
    assert device.start_calls == 0
    assert result.steps_run == 0


def _already_latest() -> LuxpowerAPIError:
    """A fresh instance per use — the harness raises the scripted object."""
    return LuxpowerAPIError(
        "API error (HTTP 200): The current machine firmware is already the latest version"
    )


@pytest.mark.asyncio
async def test_mid_chain_already_latest_start_error_reports_convergence() -> None:
    """If the check endpoint lags a successful final step, the loop can ask for
    one step too many. The server's 'already the latest version' refusal is not
    surfaced as a raw error — but convergence is confirmed by a re-check, never
    declared on the refusal alone."""
    device = ScriptedDevice(
        checks=[STEP1_PENDING, STEP2_PENDING, UP_TO_DATE],
        start_results=[True, _already_latest()],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, settle_checks=0
    )

    assert result.success and result.converged
    assert result.steps_run == 1
    assert device.start_calls == 2  # the refusal really was exercised
    assert result.final_version == "ccaa-1E1515"
    # The confirming re-check must bypass the 24h check cache, or it would
    # simply replay the stale pre-step answer it is meant to supersede.
    assert device.check_force_flags and all(device.check_force_flags)


@pytest.mark.asyncio
async def test_mid_chain_already_latest_without_confirmation_is_not_success() -> None:
    """The refusal alone must never be reported as success: if the re-check
    still says an update remains, the endpoints genuinely disagree and the
    device may be partially upgraded — exactly the failure #353 is about."""
    device = ScriptedDevice(
        checks=[STEP1_PENDING, STEP2_PENDING, STEP2_PENDING],
        start_results=[True, _already_latest()],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, settle_checks=0
    )

    assert not result.success and not result.converged
    assert result.steps_run == 1
    assert device.start_calls == 2
    assert "partially upgraded" in result.message
    # The real installed version, not the target we hoped for.
    assert result.final_version == "ccaa-1E1415"


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


@pytest.mark.asyncio
async def test_grace_resets_after_a_step_that_moves_the_version() -> None:
    """The grace is CONSECUTIVE: a no-op, then a real advance, then another
    no-op must each get their own excuse. Pins the counter reset — without it
    the second no-op would abort the chain."""
    mid = _info("ccaa-1E1465", "ccaa-1E1515", app_current=0x14, param_current=0x65)
    device = ScriptedDevice(
        # step 1 no-op, step 2 advances, step 3 no-op, step 4 converges
        checks=[STEP2_PENDING, STEP2_PENDING, mid, mid, UP_TO_DATE],
        progresses=[NOOP_INSTALLING, NOOP_DONE] * 4,
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, settle_checks=0
    )

    assert result.success and result.converged
    assert result.steps_run == 4
    assert device.start_calls == 4


@pytest.mark.asyncio
async def test_saw_in_progress_does_not_leak_across_steps() -> None:
    """saw_in_progress is per-step evidence. A step that was observed
    installing must not license the NEXT step's unobserved no-progress step."""
    device = ScriptedDevice(
        # step 1 observed installing and advances; step 2 is never observed
        # installing and does not advance -> must abort, unearned grace.
        checks=[STEP1_PENDING, STEP2_PENDING, STEP2_PENDING],
        progresses=[NOOP_INSTALLING, NOOP_DONE],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, settle_checks=0
    )

    assert not result.success
    assert result.steps_run == 2
    assert device.start_calls == 2  # no third write
    assert "No firmware version progress after step 2" in result.message


# --- Tri-model review round (PR #256) --------------------------------------


@pytest.mark.asyncio
async def test_default_config_survives_two_already_current_components() -> None:
    """The eode case with DEFAULT settings, one component deeper.

    A device can have more than one component already at the target and the
    server picks the order. With a grace of 1 this fails with the VERBATIM
    #353 symptom one step later, which is why the default is 2. No explicit
    no_progress_grace here on purpose: this pins the SHIPPED default.
    """
    device = ScriptedDevice(
        checks=[STEP2_PENDING, STEP2_PENDING, STEP2_PENDING, UP_TO_DATE],
        progresses=[NOOP_INSTALLING, NOOP_DONE] * 3,
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, settle_checks=0
    )

    assert result.success and result.converged
    assert result.steps_run == 3
    assert result.final_version == "ccaa-1E1515"


@pytest.mark.asyncio
async def test_default_grace_still_stops_a_stuck_device() -> None:
    """The default grace is 2, so a stuck device costs 3 accepted writes and
    then stops. That coupling (grace + 1) is the blind-reflash bound."""
    device = ScriptedDevice(
        checks=[STEP2_PENDING] * 6,
        progresses=[NOOP_INSTALLING, NOOP_DONE] * 6,
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, settle_checks=0
    )

    assert not result.success
    assert device.start_calls == 3  # grace(2) + 1, well inside max_steps
    assert result.steps_run == 3


@pytest.mark.asyncio
async def test_stale_installing_row_does_not_buy_the_grace() -> None:
    """A leftover in-progress row must not forge the grace's evidence.

    The aggregated progress flag matches ANY in-progress row for the serial.
    A device whose previous run left an UPLOADING row would look "installing"
    for a step the server never ran, spending real firmware writes on the
    strength of someone else's status. Only evidence that appeared or
    transitioned after our start POST counts.
    """
    stale = _row(start_time="run-from-yesterday", in_progress=True)
    device = ScriptedDevice(
        checks=[STEP2_PENDING] * 4,
        progresses=[NOOP_INSTALLING, NOOP_DONE] * 4,
        # Same row, unchanged, before and after our start: stale.
        status_rows=[stale] * 8,
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, settle_checks=0
    )

    assert not result.success
    assert device.start_calls == 1  # grace refused, no second blind write
    assert "No firmware version progress after step 1" in result.message


@pytest.mark.asyncio
async def test_fresh_row_after_our_start_does_buy_the_grace() -> None:
    """The complement: a row whose startTime changes after our POST is ours."""
    before_start = _row(start_time="run-1", in_progress=False)
    ours = _row(start_time="run-2", in_progress=True)
    device = ScriptedDevice(
        checks=[STEP2_PENDING, STEP2_PENDING, UP_TO_DATE],
        progresses=[NOOP_INSTALLING, NOOP_DONE] * 2,
        status_rows=[before_start, ours, before_start, ours],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, settle_checks=0
    )

    assert result.success and result.converged
    assert device.start_calls == 2


@pytest.mark.asyncio
async def test_flapping_check_data_does_not_reset_the_grace() -> None:
    """Alternating stale snapshots are not progress.

    A check endpoint flapping between two states it has already reported is
    not the device advancing. Counting each flap as movement reset the grace
    every time and spent the entire step budget on blind reflashes.
    """
    a = _info("ccaa-1E1413", "ccaa-1E1515", app_current=0x14, param_current=0x13)
    b = _info("ccaa-1E1414", "ccaa-1E1515", app_current=0x14, param_current=0x14)
    device = ScriptedDevice(
        checks=[a, b, a, b, a, b, a, b],
        progresses=[NOOP_INSTALLING, NOOP_DONE] * 8,
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, settle_checks=0
    )

    assert not result.success
    # a->b is genuine novelty once; every later flap revisits a seen state.
    assert device.start_calls <= 4
    assert result.steps_run <= 4


@pytest.mark.asyncio
async def test_permanent_eligibility_denial_surfaces_immediately() -> None:
    """notAllowedInParallel will never clear; do not poll it for 15 minutes."""
    device = ScriptedDevice(
        checks=[STEP1_PENDING, STEP2_PENDING, STEP2_PENDING],
        progresses=[NOOP_INSTALLING, NOOP_DONE],
        eligibility=[
            UpdateEligibilityMessage.ALLOW_TO_UPDATE,
            UpdateEligibilityMessage.NOT_ALLOWED_IN_PARALLEL,
        ],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, busy_grace=600, settle_checks=0
    )

    assert not result.success and not result.converged
    assert device.start_calls == 1  # step 1 only; step 2 never attempted
    assert device.eligibility_calls == 2  # probed once, not re-polled
    assert "notAllowedInParallel" in result.message
    assert "retry once that completes" in result.message


@pytest.mark.asyncio
async def test_transient_denial_is_still_waited_out() -> None:
    """The complement: deviceUpdating IS transient and must still be retried."""
    device = ScriptedDevice(
        checks=[STEP1_PENDING, STEP2_PENDING, UP_TO_DATE],
        eligibility=[
            UpdateEligibilityMessage.ALLOW_TO_UPDATE,
            UpdateEligibilityMessage.DEVICE_UPDATING,
            UpdateEligibilityMessage.ALLOW_TO_UPDATE,
        ],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, busy_grace=60, settle_checks=0
    )

    assert result.success and result.converged
    assert device.start_calls == 2


@pytest.mark.parametrize(
    "message",
    [
        "Failed updating firmware: invalid checksum",
        "Error updating firmware image",
    ],
)
@pytest.mark.asyncio
async def test_permanent_failure_mentioning_updating_is_not_busy(message: str) -> None:
    """A bare "updating" substring is not a busy signal.

    The loose matcher classified these as transient, so a permanent failure
    was retried for the whole busy budget and then reported as "device
    remained busy" — burying the real cause. They must propagate.
    """
    device = ScriptedDevice(
        checks=[STEP1_PENDING, STEP2_PENDING],
        start_results=[True, LuxpowerAPIError(message)],
    )

    with pytest.raises(LuxpowerAPIError, match="updating"):
        await device.run_firmware_update_to_completion(
            poll_interval=0, start_grace=0, busy_grace=60, settle_checks=0
        )


@pytest.mark.asyncio
async def test_refused_starts_are_capped_per_step() -> None:
    """The busy budget bounds elapsed time, not request count.

    With a small backoff and a long budget, an always-busy device could hammer
    the WRITE endpoint indefinitely. Cap the POSTs per step explicitly.
    """

    class AlwaysBusyAfterFirstStep(ScriptedDevice):
        async def start_firmware_update(self, try_fast_mode: bool = False) -> bool:
            self.start_calls += 1
            if self.start_calls == 1:
                self._run_seq += 1
                return True
            raise LuxpowerAPIError("API error (HTTP 200): deviceBusy")

    device = AlwaysBusyAfterFirstStep(checks=[STEP1_PENDING, STEP2_PENDING])

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, busy_grace=600, settle_checks=0
    )

    assert not result.success
    # step 1 accepted + the per-step cap on step 2, and no more.
    assert device.start_calls == 1 + _MAX_START_ATTEMPTS_PER_STEP
    assert "consecutive attempts" in result.message


@pytest.mark.asyncio
async def test_small_positive_poll_interval_does_not_hot_loop() -> None:
    """A tiny poll_interval must not slip past the backoff floor.

    The floor used to apply only to exactly 0, so 0.001 hot-looped the API.
    """

    class BusyMidChain(ScriptedDevice):
        async def start_firmware_update(self, try_fast_mode: bool = False) -> bool:
            self.start_calls += 1
            if self.start_calls == 1:
                self._run_seq += 1
                return True
            raise LuxpowerAPIError("API error (HTTP 200): deviceBusy")

    device = BusyMidChain(checks=[STEP1_PENDING, STEP2_PENDING])

    result = await device.run_firmware_update_to_completion(
        poll_interval=0.001, start_grace=0, busy_grace=0.3, settle_checks=0
    )

    assert not result.success
    # At a 0.05s floor, a 0.3s budget allows a handful of attempts — not the
    # hundreds an unfloored 0.001s interval would have issued.
    assert device.start_calls <= 1 + _MAX_START_ATTEMPTS_PER_STEP


# --- Round 3: false-negative closures -------------------------------------


@pytest.mark.asyncio
async def test_mid_chain_attribution_tolerates_a_single_session_row() -> None:
    """Steps 2+ must not demand a NEW status row.

    The portal may keep ONE row per update session and update it in place, in
    which case step 2's baseline is already an in-progress row with an
    unchanged startTime — all three freshness clauses fail, the grace is
    refused, and the reporter's verbatim error comes back. The stale-row
    threat is PRE-run leftovers, so strict attribution applies only to step 1;
    from step 2 on, an in-progress row is this run's own activity.
    """
    one_session_row = _row(start_time="session-1", in_progress=True)
    device = ScriptedDevice(
        # Step 1 advances; step 2 is a no-op component; step 3 finishes.
        checks=[STEP1_PENDING, STEP2_PENDING, STEP2_PENDING, UP_TO_DATE],
        progresses=[NOOP_INSTALLING, NOOP_DONE] * 3,
        # The same row throughout, exactly as an in-place portal would report.
        status_rows=[one_session_row] * 12,
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, settle_checks=0
    )

    assert result.success and result.converged
    assert device.start_calls == 3


@pytest.mark.asyncio
async def test_first_step_attribution_is_still_strict() -> None:
    """The complement: a pre-run leftover row still buys nothing on step 1."""
    leftover = _row(start_time="yesterday", in_progress=True)
    device = ScriptedDevice(
        checks=[STEP2_PENDING] * 4,
        progresses=[NOOP_INSTALLING, NOOP_DONE] * 4,
        status_rows=[leftover] * 8,
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, settle_checks=0
    )

    assert not result.success
    assert device.start_calls == 1  # no second blind write


@pytest.mark.parametrize(
    "message",
    [
        "API error (HTTP 200): systemBusy",
        "API error (HTTP 200): Device is updating, please try again",
        "HTTP 503: SYSTEM_BUSY",
        "API error (HTTP 200): The inverter is busy",
    ],
)
@pytest.mark.asyncio
async def test_unrecognised_busy_phrasings_are_still_tolerated(message: str) -> None:
    """Breadth restored: an enumerated code list was too narrow.

    The portal emits phrasings we have never catalogued. Treating an
    unrecognised busy response as permanent aborts a chain that would have
    succeeded moments later, so any busy/updating wording without failure
    prose counts as busy.
    """
    device = ScriptedDevice(
        checks=[STEP1_PENDING, STEP2_PENDING, UP_TO_DATE],
        start_results=[True, LuxpowerAPIError(message), True],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, busy_grace=60, settle_checks=0
    )

    assert result.success and result.converged
    assert device.start_calls == 3


@pytest.mark.parametrize(
    "message",
    [
        "API error (HTTP 200): Failed updating firmware: invalid checksum",
        "API error (HTTP 200): Error updating firmware image",
        "API error (HTTP 200): Firmware image corrupt",
        "API error (HTTP 200): Update timed out while updating",
    ],
)
@pytest.mark.asyncio
async def test_failure_prose_beats_busy_wording(message: str) -> None:
    """Stage 1 wins: failure prose is permanent even when it says "updating"."""
    device = ScriptedDevice(
        checks=[STEP1_PENDING, STEP2_PENDING],
        start_results=[True, LuxpowerAPIError(message)],
    )

    with pytest.raises(LuxpowerAPIError):
        await device.run_firmware_update_to_completion(
            poll_interval=0, start_grace=0, busy_grace=60, settle_checks=0
        )


@pytest.mark.asyncio
async def test_attribution_reuses_the_polled_row() -> None:
    """Attribution must not issue its own remoteUpdate/info call.

    A second read doubles the call rate and can disagree with the progress
    call about the same instant. The row cached by the progress poll is the
    one used.
    """
    extra_reads = 0

    class RowCallCounting(ScriptedDevice):
        async def _current_status_row(self) -> FirmwareDeviceInfo | None:
            nonlocal extra_reads
            extra_reads += 1
            return await super()._current_status_row()

    device = RowCallCounting(
        checks=[STEP2_PENDING, STEP2_PENDING, UP_TO_DATE],
        progresses=[NOOP_INSTALLING, NOOP_DONE] * 2,
    )

    await device.run_firmware_update_to_completion(poll_interval=0, start_grace=60, settle_checks=0)

    # One pre-POST baseline read per accepted step, and nothing more: the
    # polling path reads the cached row instead of calling again.
    assert extra_reads == device.start_calls


@pytest.mark.asyncio
async def test_blank_installed_version_is_not_novel_progress() -> None:
    """A sentinel is not a distinct firmware state.

    An endpoint alternating between real data and the sentinel would otherwise
    look like movement on every other check and reset the grace forever.
    """
    sentinel = _info("", "", latest_override="ccaa-1E1515")
    device = ScriptedDevice(
        checks=[STEP2_PENDING, sentinel, STEP2_PENDING, sentinel, STEP2_PENDING, sentinel],
        progresses=[NOOP_INSTALLING, NOOP_DONE] * 6,
        firmware_codes=["ccaa-1E1415"] * 12,
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=60, settle_checks=0
    )

    assert not result.success
    # grace(2) + 1 — the alternating sentinel never bought an extra step.
    assert device.start_calls == 3


@pytest.mark.asyncio
async def test_sentinel_does_not_converge_on_a_cross_source_shape_difference() -> None:
    """The movement test must compare like with like.

    The runtime endpoint's fwCode and the check endpoint's fwCodeBeforeUpload
    are different sources, and this repo documents check-side strings as
    synthesized reconstructions. If their shapes differ by more than case, a
    check-vs-runtime movement test is PERMANENTLY unequal, so every sentinel
    would report converged on its first occurrence — silent, and always toward
    false success. Baselining from the same source removes the mismatch.
    """
    sentinel = _info("", "")
    device = ScriptedDevice(
        # Check-side strings carry a prefix the runtime endpoint omits.
        checks=[
            _info("PFX/ccaa-1E1415", "PFX/ccaa-1E1515", app_current=0x14, param_current=0x15),
            sentinel,
            sentinel,
            sentinel,
        ],
        # Runtime consistently reports the short form, and never moves.
        firmware_codes=["ccaa-1E1415"] * 8,
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, settle_checks=0
    )

    assert not result.success and not result.converged
    assert "complete" not in result.message


@pytest.mark.asyncio
async def test_no_same_source_baseline_is_indeterminate_not_movement() -> None:
    """If the pre-run baseline read failed, "did it move?" is unanswerable.

    Counting inequality as movement there would be guessing in the direction
    of success, so the run reports indeterminate instead.
    """
    sentinel = _info("", "")
    device = ScriptedDevice(
        checks=[STEP2_PENDING, sentinel],
        # The baseline read fails on every attempt INCLUDING its retries (a
        # single None would now be retried away); the later corroboration
        # succeeds with some other value.
        firmware_codes=[None, None, None, None, "ccaa-1E9999"],
    )

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert not result.success and not result.converged
    assert "verify the firmware version on the device" in result.message
    # The corroborated version IS known here, so the message must say it
    # rather than claiming the version could not be read.
    assert "device reports ccaa-1E9999" in result.message
    assert "no pre-run version to compare" in result.message
    assert result.final_version == "ccaa-1E9999"


# --- Round 4 ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("wrapped", "is_busy"),
    [
        # The EXACT shapes LuxpowerClient emits — bare codes never reach here.
        ("API error (HTTP 200): deviceBusy", True),
        ("API error (HTTP 200): systemBusy", True),
        ("API error (HTTP 200): Device is updating, please try again", True),
        ("HTTP 500: deviceBusy", True),
        ("API error (HTTP 200): Failed updating firmware: invalid checksum", False),
        ("API error (HTTP 200): Firmware image corrupt", False),
        ("Unexpected error: boom", False),
    ],
)
def test_busy_classification_uses_the_real_client_error_shape(wrapped: str, is_busy: bool) -> None:
    """Regression: the classifier ran against the client's WRAPPER.

    LuxpowerClient raises "API error (HTTP {status}): {msg}" and "Unexpected
    error: {err}" — both contain the word "error", which the permanent-failure
    stage matched, so EVERY busy response was ruled permanent and the busy
    path was dead in production. Unit tests passed only because they injected
    a bare "deviceBusy", a shape the client never emits.
    """
    from pylxpweb.devices._firmware_update_mixin import (
        _BUSY_PROSE,
        _PERMANENT_FAILURE_PROSE,
        _server_message,
    )

    message = _server_message(LuxpowerAPIError(wrapped)).casefold()
    permanent = any(p in message for p in _PERMANENT_FAILURE_PROSE)
    classified_busy = (not permanent) and any(p in message for p in _BUSY_PROSE)

    assert classified_busy is is_busy


@pytest.mark.asyncio
async def test_wrapped_busy_error_is_tolerated_end_to_end() -> None:
    """The production error shape must actually drive the busy path."""
    device = ScriptedDevice(
        checks=[STEP1_PENDING, STEP2_PENDING, UP_TO_DATE],
        start_results=[
            True,
            LuxpowerAPIError("API error (HTTP 200): deviceBusy"),
            True,
        ],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, busy_grace=60, settle_checks=0
    )

    assert result.success and result.converged
    assert device.start_calls == 3


@pytest.mark.asyncio
async def test_wrapped_permanent_failure_still_propagates() -> None:
    """...without letting the wrapper make everything permanent again."""
    device = ScriptedDevice(
        checks=[STEP1_PENDING, STEP2_PENDING],
        start_results=[
            True,
            LuxpowerAPIError("API error (HTTP 200): Failed updating firmware: invalid checksum"),
        ],
    )

    with pytest.raises(LuxpowerAPIError, match="invalid checksum"):
        await device.run_firmware_update_to_completion(
            poll_interval=0, start_grace=0, busy_grace=60, settle_checks=0
        )


@pytest.mark.asyncio
async def test_preflight_sentinel_is_confirmed_before_being_believed() -> None:
    """A blinking sentinel on the FIRST check must not report up-to-date.

    The pre-flight path returned success on `not update_available` with no
    corroboration, so round 2's headline false positive survived at the front
    door: a partially updated device whose first check blinked would be told
    it needs no update at all.
    """
    sentinel = _info("", "")
    device = ScriptedDevice(
        # First check blinks; the confirming re-check reports the real work.
        checks=[sentinel, STEP2_PENDING, UP_TO_DATE],
        firmware_codes=["ccaa-1E1415"] * 4,
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, settle_checks=0, preflight_confirm_delay=0
    )

    assert result.success and result.converged
    assert device.start_calls == 1  # it really did run the update
    assert device.check_calls >= 3  # blink + confirmation + post-step


@pytest.mark.asyncio
async def test_preflight_sentinel_confirmed_twice_is_up_to_date() -> None:
    """Two agreeing reads are believed — no update is attempted."""
    sentinel = _info("", "")
    device = ScriptedDevice(checks=[sentinel, sentinel])

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, preflight_confirm_delay=0
    )

    assert result.success and result.converged
    assert result.steps_run == 0
    assert device.start_calls == 0


@pytest.mark.asyncio
async def test_preflight_concrete_up_to_date_needs_no_confirmation() -> None:
    """A concrete version with nothing newer is trusted on one read."""
    device = ScriptedDevice(checks=[UP_TO_DATE])

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, preflight_confirm_delay=0
    )

    assert result.success and result.converged
    assert device.check_calls == 1  # no second call


@pytest.mark.asyncio
async def test_corroboration_read_is_retried_before_giving_up() -> None:
    """A transient read failure must not turn success into a red error.

    The device reboots after its final component; a single failed runtime read
    in that window would report a COMPLETED update as unconfirmable.
    """
    sentinel = _info("", "")
    device = ScriptedDevice(
        checks=[STEP2_PENDING, sentinel],
        # baseline ok, then two failures, then the truth.
        firmware_codes=["ccaa-1E1415", None, None, "ccaa-1E1515"],
    )

    result = await device.run_firmware_update_to_completion(
        poll_interval=0, start_grace=0, settle_checks=0
    )

    assert result.success and result.converged
    assert result.final_version == "ccaa-1E1515"


@pytest.mark.asyncio
async def test_pre_run_baseline_read_is_retried() -> None:
    """The baseline read gets the same retry as the corroboration reads.

    Run start is itself a transient-failure moment — the reporter's device was
    literally recovering from an earlier update attempt — and a failed
    baseline disables the movement test for the WHOLE run, turning a
    successful update into an indeterminate red error.
    """
    sentinel = _info("", "")
    device = ScriptedDevice(
        checks=[STEP2_PENDING, sentinel],
        # Baseline fails once then succeeds; the corroboration then shows the
        # device on the target. Without the retry the baseline stays None and
        # the run cannot conclude anything.
        firmware_codes=[None, "ccaa-1E1415", "ccaa-1E1515"],
    )

    result = await device.run_firmware_update_to_completion(poll_interval=0, start_grace=0)

    assert result.success and result.converged
    assert result.final_version == "ccaa-1E1515"


# --- Direct coverage of the REAL _read_device_firmware_code body ------------
#
# ScriptedDevice overrides this method wholesale, so every orchestration test
# above exercises the harness, not production. The previous ValidationError
# test was a tautology: it re-implemented the except clause inside a subclass,
# so reverting the production catch left it green. These drive the actual body.


class _BareHost(FirmwareUpdateMixin):
    """Mixin host with nothing but what the production body touches."""

    def __init__(self, runtime_result: object) -> None:
        self._init_firmware_update_cache()
        self.serial_number = "4413740117"
        self._runtime_result = runtime_result
        self._client = self._build_client()

    def _build_client(self) -> MagicMock:
        async def _get_inverter_runtime(serial: str) -> object:
            if isinstance(self._runtime_result, Exception):
                raise self._runtime_result
            return self._runtime_result

        client = MagicMock()
        client.api.devices.get_inverter_runtime = _get_inverter_runtime
        return client


@pytest.mark.asyncio
async def test_read_device_firmware_code_returns_the_code() -> None:
    host = _BareHost(SimpleNamespace(fwCode="ccaa-1E1515"))

    assert await host._read_device_firmware_code() == "ccaa-1E1515"


@pytest.mark.asyncio
async def test_read_device_firmware_code_treats_empty_as_unknown() -> None:
    """An empty string is not a version; it must not be reported as one."""
    host = _BareHost(SimpleNamespace(fwCode=""))

    assert await host._read_device_firmware_code() is None


@pytest.mark.asyncio
async def test_read_device_firmware_code_swallows_api_errors() -> None:
    host = _BareHost(LuxpowerAPIError("API error (HTTP 500): boom"))

    assert await host._read_device_firmware_code() is None


@pytest.mark.asyncio
async def test_read_device_firmware_code_swallows_validation_errors() -> None:
    """fwCode is a required str, so a device omitting it mid-reboot raises
    ValidationError — which would escape into the HA install action."""
    from pydantic import ValidationError

    host = _BareHost(ValidationError.from_exception_data("InverterRuntime", []))

    assert await host._read_device_firmware_code() is None


@pytest.mark.asyncio
async def test_read_device_firmware_code_does_not_swallow_everything() -> None:
    """The catch is narrow on purpose: a programming error must still surface."""
    host = _BareHost(RuntimeError("not an API failure"))

    with pytest.raises(RuntimeError, match="not an API failure"):
        await host._read_device_firmware_code()
