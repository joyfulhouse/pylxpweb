"""API-related constants for HTTP communication and error handling.

This module contains HTTP status codes, backoff/retry configuration,
and transient error detection for API communication.
"""

from __future__ import annotations

# HTTP Status Codes
# ==============================================================================
# Standard HTTP status codes used throughout the library
HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403

# ==============================================================================
# Device Type Constants
# ==============================================================================
# Device type identifiers from the Luxpower API
DEVICE_TYPE_INVERTER = 6  # Standard inverter
DEVICE_TYPE_GRIDBOSS = 9  # GridBOSS/MID device (parallel group controller)

# ==============================================================================
# Backoff and Retry Constants
# ==============================================================================
# Base delay (in seconds) for exponential backoff on API errors
BACKOFF_BASE_DELAY_SECONDS = 1.0

# Maximum delay (in seconds) for exponential backoff
BACKOFF_MAX_DELAY_SECONDS = 60.0

# Maximum number of retry attempts for transient errors
MAX_TRANSIENT_ERROR_RETRIES = 3

# Maximum number of retry attempts for login (re-authentication)
# This allows recovery from transient network issues during re-auth
# without requiring manual user intervention (fixes issue #70)
MAX_LOGIN_RETRIES = 3

# Known transient error messages that should trigger automatic retry
# These are hardware/network communication errors that may succeed on retry
TRANSIENT_ERROR_MESSAGES = {
    "DATAFRAME_TIMEOUT",  # Inverter dataframe communication timeout
    "TIMEOUT",  # Generic timeout error
    "BUSY",  # Device busy, try again
    "COMMUNICATION_ERROR",  # Communication failure with device
    "DEVICE_BUSY",  # Device is busy processing another request
}
