"""Data collectors for Modbus diagnostic tool.

This module provides collectors for acquiring register data from various sources:
- ModbusCollector: Direct Modbus TCP connection via RS485-to-Ethernet adapter
- DongleCollector: WiFi dongle TCP connection (port 8000)
- CloudCollector: Luxpower/EG4 cloud API

All collectors implement the BaseCollector protocol and return CollectionResult objects.
"""

from .base import BaseCollector, CollectionResult, ComparisonResult, compare_collections
from .cloud import CloudCollector
from .dongle import DongleCollector
from .modbus import ModbusCollector

__all__ = [
    "BaseCollector",
    "CollectionResult",
    "ComparisonResult",
    "compare_collections",
    "ModbusCollector",
    "DongleCollector",
    "CloudCollector",
]
