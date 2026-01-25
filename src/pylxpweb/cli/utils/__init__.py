"""Utility modules for the Modbus diagnostic CLI tool."""

from .github import generate_gh_command, generate_issue_body
from .prompts import (
    prompt_base_url,
    prompt_confirm,
    prompt_credentials,
    prompt_host,
    prompt_register_ranges,
    prompt_serial,
    prompt_transport,
)
from .serial_detect import detect_serial_from_registers, parse_firmware_version

__all__ = [
    # Prompts
    "prompt_transport",
    "prompt_host",
    "prompt_serial",
    "prompt_credentials",
    "prompt_base_url",
    "prompt_register_ranges",
    "prompt_confirm",
    # GitHub
    "generate_gh_command",
    "generate_issue_body",
    # Serial detection
    "detect_serial_from_registers",
    "parse_firmware_version",
]
