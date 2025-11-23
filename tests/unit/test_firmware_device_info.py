"""Unit tests for FirmwareDeviceInfo model."""

from __future__ import annotations

from pylxpweb.models import FirmwareDeviceInfo, UpdateStatus


class TestFirmwareDeviceInfoIsInProgress:
    """Tests for is_in_progress property."""

    def test_is_in_progress_true_when_uploading_and_not_ended(self) -> None:
        """Test is_in_progress returns True during active upload."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.UPLOADING,
            isSendStartUpdate=True,
            isSendEndUpdate=False,
            packageIndex=280,
            updateRate="50% - 280 / 561",
        )

        assert device_info.is_in_progress is True

    def test_is_in_progress_true_when_ready_and_not_ended(self) -> None:
        """Test is_in_progress returns True when status is READY."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.READY,
            isSendStartUpdate=True,
            isSendEndUpdate=False,
            packageIndex=0,
            updateRate="0% - 0 / 561",
        )

        assert device_info.is_in_progress is True

    def test_is_in_progress_false_when_update_ended(self) -> None:
        """Test is_in_progress returns False when isSendEndUpdate is True."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="2025-11-23 10:25:00",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.SUCCESS,
            isSendStartUpdate=True,
            isSendEndUpdate=True,  # End notification sent
            packageIndex=560,
            updateRate="100% - 561 / 561",
        )

        assert device_info.is_in_progress is False

    def test_is_in_progress_false_when_not_started(self) -> None:
        """Test is_in_progress returns False when isSendStartUpdate is False."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="",
            stopTime="",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.READY,
            isSendStartUpdate=False,  # Not started yet
            isSendEndUpdate=False,
            packageIndex=0,
            updateRate="0% - 0 / 561",
        )

        assert device_info.is_in_progress is False

    def test_is_in_progress_false_when_failed(self) -> None:
        """Test is_in_progress returns False when update failed."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="2025-11-23 10:15:00",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.FAILED,
            isSendStartUpdate=True,
            isSendEndUpdate=True,
            packageIndex=150,
            updateRate="26% - 150 / 561",
        )

        assert device_info.is_in_progress is False

    def test_is_in_progress_false_when_complete_status(self) -> None:
        """Test is_in_progress returns False when status is COMPLETE."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="2025-11-23 10:25:00",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.COMPLETE,
            isSendStartUpdate=True,
            isSendEndUpdate=True,
            packageIndex=560,
            updateRate="100% - 561 / 561",
        )

        assert device_info.is_in_progress is False


class TestFirmwareDeviceInfoIsComplete:
    """Tests for is_complete property."""

    def test_is_complete_true_when_success_and_ended(self) -> None:
        """Test is_complete returns True when update succeeded."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="2025-11-23 10:25:00",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.SUCCESS,
            isSendStartUpdate=True,
            isSendEndUpdate=True,
            packageIndex=560,
            updateRate="100% - 561 / 561",
        )

        assert device_info.is_complete is True

    def test_is_complete_true_when_complete_status_and_ended(self) -> None:
        """Test is_complete returns True when status is COMPLETE."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="2025-11-23 10:25:00",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.COMPLETE,
            isSendStartUpdate=True,
            isSendEndUpdate=True,
            packageIndex=560,
            updateRate="100% - 561 / 561",
        )

        assert device_info.is_complete is True

    def test_is_complete_false_when_not_ended(self) -> None:
        """Test is_complete returns False when isSendEndUpdate is False."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.SUCCESS,
            isSendStartUpdate=True,
            isSendEndUpdate=False,  # Not ended yet
            packageIndex=560,
            updateRate="100% - 561 / 561",
        )

        assert device_info.is_complete is False

    def test_is_complete_false_when_no_stop_time(self) -> None:
        """Test is_complete returns False when stopTime is empty."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="",  # Empty stop time
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.SUCCESS,
            isSendStartUpdate=True,
            isSendEndUpdate=True,
            packageIndex=560,
            updateRate="100% - 561 / 561",
        )

        assert device_info.is_complete is False

    def test_is_complete_false_when_stop_time_whitespace(self) -> None:
        """Test is_complete returns False when stopTime is whitespace."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="   ",  # Whitespace only
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.SUCCESS,
            isSendStartUpdate=True,
            isSendEndUpdate=True,
            packageIndex=560,
            updateRate="100% - 561 / 561",
        )

        assert device_info.is_complete is False

    def test_is_complete_false_when_in_progress(self) -> None:
        """Test is_complete returns False when update is in progress."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.UPLOADING,
            isSendStartUpdate=True,
            isSendEndUpdate=False,
            packageIndex=280,
            updateRate="50% - 280 / 561",
        )

        assert device_info.is_complete is False

    def test_is_complete_false_when_failed(self) -> None:
        """Test is_complete returns False when update failed."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="2025-11-23 10:15:00",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.FAILED,
            isSendStartUpdate=True,
            isSendEndUpdate=True,
            packageIndex=150,
            updateRate="26% - 150 / 561",
        )

        assert device_info.is_complete is False


class TestFirmwareDeviceInfoIsFailed:
    """Tests for is_failed property."""

    def test_is_failed_true_when_failed_status(self) -> None:
        """Test is_failed returns True when status is FAILED."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="2025-11-23 10:15:00",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.FAILED,
            isSendStartUpdate=True,
            isSendEndUpdate=True,
            packageIndex=150,
            updateRate="26% - 150 / 561",
        )

        assert device_info.is_failed is True

    def test_is_failed_false_when_uploading(self) -> None:
        """Test is_failed returns False when status is UPLOADING."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.UPLOADING,
            isSendStartUpdate=True,
            isSendEndUpdate=False,
            packageIndex=280,
            updateRate="50% - 280 / 561",
        )

        assert device_info.is_failed is False

    def test_is_failed_false_when_success(self) -> None:
        """Test is_failed returns False when status is SUCCESS."""
        device_info = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="2025-11-23 10:25:00",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.SUCCESS,
            isSendStartUpdate=True,
            isSendEndUpdate=True,
            packageIndex=560,
            updateRate="100% - 561 / 561",
        )

        assert device_info.is_failed is False


class TestFirmwareDeviceInfoEdgeCases:
    """Tests for edge cases and corner scenarios."""

    def test_mutual_exclusivity_of_states(self) -> None:
        """Test that is_in_progress, is_complete, and is_failed are mutually exclusive."""
        # Active update
        active = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.UPLOADING,
            isSendStartUpdate=True,
            isSendEndUpdate=False,
            packageIndex=280,
            updateRate="50% - 280 / 561",
        )
        assert active.is_in_progress is True
        assert active.is_complete is False
        assert active.is_failed is False

        # Completed update
        complete = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="2025-11-23 10:25:00",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.SUCCESS,
            isSendStartUpdate=True,
            isSendEndUpdate=True,
            packageIndex=560,
            updateRate="100% - 561 / 561",
        )
        assert complete.is_in_progress is False
        assert complete.is_complete is True
        assert complete.is_failed is False

        # Failed update
        failed = FirmwareDeviceInfo.model_construct(
            inverterSn="1234567890",
            startTime="2025-11-23 10:00:00",
            stopTime="2025-11-23 10:15:00",
            standardUpdate=True,
            firmware="IAAB-0E00",
            firmwareType="PCS",
            updateStatus=UpdateStatus.FAILED,
            isSendStartUpdate=True,
            isSendEndUpdate=True,
            packageIndex=150,
            updateRate="26% - 150 / 561",
        )
        assert failed.is_in_progress is False
        assert failed.is_complete is False
        assert failed.is_failed is True
