"""Direct RS485 battery Modbus transport.

Connects to an RS485-to-TCP bridge (e.g., Waveshare) on the battery
daisy chain, separate from the inverter's Modbus connection.

Each battery unit has a unique Modbus unit ID (1=master, 2+=slave).
The transport auto-detects the protocol (master vs slave) per unit.

Data overlay (master battery only):
  The master protocol cannot provide per-cell temperatures via RS485
  (only aggregate MAX at reg 24). When ``read_all()`` receives inverter
  BMS data (already read during the inverter's normal refresh cycle),
  it overlays the missing fields onto the master's BatteryData.
  Slave batteries have complete data from RS485 and need no overlay.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Self

from pymodbus.client import AsyncModbusTcpClient

from pylxpweb.battery_protocols.base import BatteryProtocol
from pylxpweb.battery_protocols.detection import detect_protocol
from pylxpweb.battery_protocols.eg4_master import EG4MasterProtocol
from pylxpweb.battery_protocols.eg4_slave import EG4SlaveProtocol
from pylxpweb.transports.data import BatteryData, InverterRuntimeData

_LOGGER = logging.getLogger(__name__)

# Number of registers to read for initial runtime block (covers both protocols)
_INITIAL_BLOCK_COUNT = 42

# Small delay between sequential register reads to avoid bus congestion (seconds)
_INTER_READ_DELAY = 0.1

# Delay between sequential unit reads during scan or read_all (seconds)
_INTER_UNIT_DELAY = 0.2

# Protocol name -> class mapping
_PROTOCOL_MAP: dict[str, type[BatteryProtocol]] = {
    "eg4_master": EG4MasterProtocol,
    "eg4_slave": EG4SlaveProtocol,
}


class BatteryModbusTransport:
    """Direct RS485 connection to battery BMS units.

    Connects to an RS485-to-TCP bridge that sits on the battery daisy
    chain. Each battery has its own Modbus unit ID.

    Supports async context manager for automatic connection management::

        async with BatteryModbusTransport(host="10.100.3.27") as bus:
            data = await bus.read_all()

    Args:
        host: Bridge IP address (e.g., "10.100.3.27").
        port: Modbus TCP port (default 502).
        unit_ids: Specific unit IDs to read. None = scan up to max_units.
        max_units: Maximum unit IDs to scan when unit_ids is None.
        protocol: Protocol name or "auto" for auto-detection.
        inverter_serial: Serial number of the inverter these batteries belong to.
        timeout: Modbus connection and read timeout in seconds.
    """

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_ids: list[int] | None = None,
        max_units: int = 8,
        protocol: str = "auto",
        inverter_serial: str = "",
        timeout: float = 3.0,
    ) -> None:
        self.host = host
        self.port = port
        self.unit_ids = unit_ids
        self.max_units = max_units
        self.protocol_name = protocol
        self.inverter_serial = inverter_serial
        self.timeout = timeout
        self._client: AsyncModbusTcpClient | None = None
        self._connected = False
        # Cache detected protocols per unit ID
        self._detected_protocols: dict[int, BatteryProtocol] = {}

    @property
    def is_connected(self) -> bool:
        """Check if transport is connected to the RS485 bridge."""
        return self._connected

    async def __aenter__(self) -> Self:
        """Enter async context manager, connecting the transport."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit async context manager, disconnecting the transport."""
        await self.disconnect()

    async def connect(self) -> None:
        """Establish Modbus TCP connection to the RS485 bridge."""
        self._client = AsyncModbusTcpClient(self.host, port=self.port, timeout=self.timeout)
        await self._client.connect()
        self._connected = self._client.connected
        if self._connected:
            _LOGGER.info("Connected to battery RS485 bridge at %s:%d", self.host, self.port)
        else:
            _LOGGER.error(
                "Failed to connect to battery RS485 bridge at %s:%d",
                self.host,
                self.port,
            )

    async def disconnect(self) -> None:
        """Close the Modbus TCP connection."""
        if self._client:
            self._client.close()
        self._connected = False

    async def _read_registers(self, start: int, count: int, unit_id: int) -> list[int] | None:
        """Read holding registers from a battery unit.

        Args:
            start: First register address to read.
            count: Number of contiguous registers to read.
            unit_id: Modbus unit/slave ID.

        Returns:
            List of register values, or None on error/timeout.
        """
        if not self._client:
            return None
        try:
            result = await self._client.read_holding_registers(
                start, count=count, device_id=unit_id
            )
            if result.isError():
                return None
            return list(result.registers)
        except Exception:
            _LOGGER.debug("Read failed: unit=%d start=%d count=%d", unit_id, start, count)
            return None

    def _get_protocol(self, unit_id: int, raw_regs: dict[int, int]) -> BatteryProtocol:
        """Get the protocol for a unit, auto-detecting if needed.

        Args:
            unit_id: Modbus unit/slave ID.
            raw_regs: Dict mapping register address to raw 16-bit value.

        Returns:
            BatteryProtocol instance for decoding this unit's registers.
        """
        if self.protocol_name != "auto":
            proto_cls = _PROTOCOL_MAP.get(self.protocol_name)
            if proto_cls:
                return proto_cls()
            _LOGGER.warning("Unknown protocol '%s', falling back to auto", self.protocol_name)

        # Check cache
        if unit_id in self._detected_protocols:
            return self._detected_protocols[unit_id]

        # Auto-detect from register values
        protocol = detect_protocol(raw_regs)
        self._detected_protocols[unit_id] = protocol
        _LOGGER.info("Auto-detected protocol '%s' for unit %d", protocol.name, unit_id)
        return protocol

    async def read_unit(self, unit_id: int) -> BatteryData | None:
        """Read a single battery unit, returning decoded BatteryData.

        Auto-detects the protocol (master vs slave) on first read.
        For master battery with slave context and BMS overlay, use
        ``read_all()`` instead.

        Args:
            unit_id: Modbus unit/slave ID (1=master, 2+=slave).

        Returns:
            BatteryData with all values scaled, or None if unit doesn't respond.
        """
        _, data = await self._read_unit_raw(unit_id)
        return data

    async def scan_units(self) -> list[int]:
        """Discover which unit IDs respond on the bus.

        If explicit unit_ids were provided at construction, returns them
        without probing. Otherwise, probes unit IDs 1 through max_units.

        Returns:
            List of responding unit IDs.
        """
        if self.unit_ids is not None:
            return self.unit_ids

        responding: list[int] = []
        for uid in range(1, self.max_units + 1):
            regs = await self._read_registers(0, 1, uid)
            if regs is not None:
                responding.append(uid)
            await asyncio.sleep(_INTER_UNIT_DELAY)

        _LOGGER.info(
            "Battery bus scan: %d/%d units responding",
            len(responding),
            self.max_units,
        )
        return responding

    async def read_all(
        self,
        inverter_bms_data: InverterRuntimeData | None = None,
    ) -> list[BatteryData]:
        """Read all battery units with master SOC back-calculation and BMS overlay.

        Reads slaves first, then re-decodes the master using slave context
        (for individual SOC/remaining capacity). If inverter BMS data is
        provided, overlays missing master fields (per-cell temperatures)
        that are only available via the inverter's CAN bus connection.

        Args:
            inverter_bms_data: Already-read inverter runtime data containing
                BMS fields (bms_max_cell_temperature, bms_min_cell_temperature,
                etc.). Passed from the inverter's normal refresh cycle to avoid
                redundant reads. Only used for the master battery.

        Returns:
            List of BatteryData objects for responding units, master first.
        """
        units = self.unit_ids or await self.scan_units()

        # Read all units, keeping track of raw registers for master re-decode
        raw_by_unit: dict[int, dict[int, int]] = {}
        slave_results: list[BatteryData] = []
        master_uid: int | None = None
        master_data: BatteryData | None = None

        for uid in units:
            raw, data = await self._read_unit_raw(uid)
            if data is None:
                continue

            raw_by_unit[uid] = raw
            protocol = self._get_protocol(uid, raw)

            if isinstance(protocol, EG4MasterProtocol):
                master_uid = uid
                master_data = data
            else:
                slave_results.append(data)

            await asyncio.sleep(_INTER_UNIT_DELAY)

        # Re-decode master with slave context for individual SOC
        if master_uid is not None and master_data is not None and slave_results:
            master_proto = self._get_protocol(master_uid, raw_by_unit[master_uid])
            if isinstance(master_proto, EG4MasterProtocol):
                master_data = master_proto.decode_with_slaves(
                    raw_by_unit[master_uid],
                    slave_results,
                    battery_index=master_uid - 1,
                )

        # Overlay inverter BMS data onto master (fills RS485 gaps)
        if master_data is not None and inverter_bms_data is not None:
            master_data = self._overlay_inverter_bms(master_data, inverter_bms_data)

        # Assemble results: master first, then slaves in order
        results: list[BatteryData] = []
        if master_data is not None:
            results.append(master_data)
        results.extend(slave_results)

        _LOGGER.info(
            "Read %d batteries from RS485 bus %s:%d",
            len(results),
            self.host,
            self.port,
        )
        return results

    async def _read_unit_raw(self, unit_id: int) -> tuple[dict[int, int], BatteryData | None]:
        """Read a single unit, returning both raw registers and decoded data.

        Args:
            unit_id: Modbus unit/slave ID.

        Returns:
            Tuple of (raw_registers, decoded_data). Raw registers are always
            returned (may be empty). Decoded data is None on read failure.
        """
        runtime_regs = await self._read_registers(0, _INITIAL_BLOCK_COUNT, unit_id)
        if runtime_regs is None:
            return {}, None

        raw: dict[int, int] = dict(enumerate(runtime_regs))
        protocol = self._get_protocol(unit_id, raw)

        for block in protocol.register_blocks:
            if block.start >= _INITIAL_BLOCK_COUNT:
                extra = await self._read_registers(block.start, block.count, unit_id)
                if extra:
                    for i, v in enumerate(extra):
                        raw[block.start + i] = v
                await asyncio.sleep(_INTER_READ_DELAY)

        battery_index = unit_id - 1
        data = protocol.decode(raw, battery_index=battery_index)
        return raw, data

    @staticmethod
    def _overlay_inverter_bms(
        master: BatteryData,
        bms: InverterRuntimeData,
    ) -> BatteryData:
        """Overlay inverter BMS fields onto master battery data.

        The master RS485 protocol only provides aggregate MAX temperature
        (reg 24) with no per-cell or min temperature. The inverter reads
        this data from the battery CAN bus and exposes it in its own
        registers. This method fills those gaps without overwriting any
        field that RS485 already provides accurately.

        Args:
            master: Master BatteryData from RS485 decode.
            bms: Inverter runtime data with BMS fields already populated.

        Returns:
            New BatteryData with gaps filled from inverter BMS.
        """
        # Only overlay temperature fields that RS485 can't provide.
        # Master RS485 sets both min and max to reg 24 (aggregate MAX),
        # so if inverter BMS has actual per-cell temps, use those.
        min_cell_temp = master.min_cell_temperature
        max_cell_temp = master.max_cell_temperature
        if bms.bms_min_cell_temperature is not None:
            min_cell_temp = bms.bms_min_cell_temperature
        if bms.bms_max_cell_temperature is not None:
            max_cell_temp = bms.bms_max_cell_temperature

        return BatteryData(
            battery_index=master.battery_index,
            serial_number=master.serial_number,
            voltage=master.voltage,
            current=master.current,
            soc=master.soc,
            soh=master.soh,
            temperature=master.temperature,
            max_capacity=master.max_capacity,
            current_capacity=master.current_capacity,
            cycle_count=master.cycle_count,
            cell_count=master.cell_count,
            cell_voltages=master.cell_voltages,
            cell_temperatures=master.cell_temperatures,
            min_cell_voltage=master.min_cell_voltage,
            max_cell_voltage=master.max_cell_voltage,
            min_cell_temperature=min_cell_temp,
            max_cell_temperature=max_cell_temp,
            max_cell_num_voltage=master.max_cell_num_voltage,
            min_cell_num_voltage=master.min_cell_num_voltage,
            max_cell_num_temp=master.max_cell_num_temp,
            min_cell_num_temp=master.min_cell_num_temp,
            charge_voltage_ref=master.charge_voltage_ref,
            charge_current_limit=master.charge_current_limit,
            discharge_current_limit=master.discharge_current_limit,
            discharge_voltage_cutoff=master.discharge_voltage_cutoff,
            model=master.model,
            firmware_version=master.firmware_version,
            status=master.status,
            fault_code=master.fault_code,
            warning_code=master.warning_code,
        )
