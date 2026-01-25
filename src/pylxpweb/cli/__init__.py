"""Command-line interface tools for pylxpweb.

This package contains command-line tools for working with Luxpower/EG4 inverters:

- `pylxpweb-modbus-diag`: Modbus register diagnostic tool
- `pylxpweb-collect`: Device data collection tool
"""

from __future__ import annotations

from .modbus_diag import main as modbus_diag_main

__all__ = ["modbus_diag_main"]
