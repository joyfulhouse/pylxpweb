# Cache Boundary Issue Analysis

**Date**: 2025-11-22
**Issue**: Cached values near hour boundaries can cause stale data for entire day
**Status**: Identified - Solution Required

## Problem Description

The current cache invalidation strategy has a critical flaw that can cause stale data to persist across date boundaries (midnight), leading to incorrect daily energy values for the entire day.

### Current Implementation

```python
# client.py:634-692
@property
def should_invalidate_cache(self) -> bool:
    """Check if cache should be invalidated for hour/date boundaries."""
    now = datetime.now()
    minutes_to_hour = 60 - now.minute

    # Outside the window before hour boundary (XX:00-XX:54)
    if minutes_to_hour > CACHE_INVALIDATION_WINDOW_MINUTES:  # 5 minutes
        return False

    # Within window (XX:55-XX:59): Consider invalidation
    # ... rate limiting logic ...

    return should_invalidate
```

**Constants**:
- `CACHE_INVALIDATION_WINDOW_MINUTES = 5` (XX:55-XX:59)
- `MIN_CACHE_INVALIDATION_INTERVAL_MINUTES = 10`

### The Critical Flaw

**The `should_invalidate_cache` property is PASSIVE** - it only returns a boolean. Nothing automatically calls it or acts on it.

## Failure Scenario

### Timeline Example

```
23:55:00 - should_invalidate_cache = True (within window)
           ├─ HA integration calls: client.clear_all_caches()
           └─ Cache cleared ✓

23:58:00 - API request: getInverterEnergyInfo
           ├─ Cache miss (was cleared at 23:55)
           ├─ Fetches fresh data: todayYielding = 155 (15.5 kWh)
           └─ Caches response with TTL = 30 seconds ✓

23:58:30 - HA polls again
           └─ Returns cached value: 15.5 kWh ✓

23:59:00 - should_invalidate_cache = True
           ├─ But HA hasn't polled yet, so cache not cleared
           └─ Cached value still valid (TTL not expired)

23:59:30 - HA polls
           └─ Returns cached value: 15.5 kWh ✓

00:00:00 - MIDNIGHT - Date boundary crossed! ⚠️
           ├─ should_invalidate_cache = False (hour just changed, minutes=0)
           └─ Cache invalidation window closed!

00:00:30 - HA polls (first poll of new day)
           ├─ should_invalidate_cache = False (we're at XX:00, outside window)
           ├─ Cache entry still valid:
           │  ├─ Cached at: 23:58:00
           │  ├─ TTL: 30 seconds (expired by 2.5 min, but not checked!)
           │  └─ Wait, TTL check should catch this... 🤔
           └─ Actually, TTL should have expired

Let me check TTL validation logic...
```

Wait - the TTL should catch this. Let me trace through more carefully:

```python
# client.py:338-349
def _is_cache_valid(self, cache_key: str, endpoint_key: str) -> bool:
    """Check if cached response is still valid."""
    if cache_key not in self._response_cache:
        return False

    cache_entry = self._response_cache[cache_key]
    cache_time = cache_entry.get("timestamp")
    if not isinstance(cache_time, datetime):
        return False

    ttl = self._cache_ttl_config.get(endpoint_key, timedelta(seconds=30))
    return datetime.now() < cache_time + ttl  # ✓ Checks TTL expiry
```

So actually, the TTL **should** prevent serving stale data if the default is 30 seconds...

### The REAL Problem

The real issue is **timing-dependent race conditions** at the boundary:

```
Scenario: Cache populated just AFTER midnight but BEFORE first check

23:59:50 - HA poll
           ├─ should_invalidate_cache = True (within 55-59 window)
           ├─ HA calls clear_all_caches()
           └─ Cache cleared at 23:59:50

00:00:20 - HA poll (first of new day, 30 sec update interval)
           ├─ should_invalidate_cache = False (minutes=0, outside window)
           ├─ Cache miss (cleared at 23:59:50)
           ├─ API call: todayYielding = 155 (STALE! API hasn't reset yet)
           ├─ Caches: timestamp=00:00:20, value=155
           └─ Returns 15.5 kWh ❌ (yesterday's total!)

00:00:50 - HA poll
           ├─ Cache hit (cached at 00:00:20, only 30 sec old)
           └─ Returns 15.5 kWh ❌ (still wrong)

00:01:20 - HA poll
           ├─ Cache expired (TTL=30s, cached 60s ago)
           ├─ API call: todayYielding = 155 (STILL STALE!)
           ├─ Re-caches: timestamp=00:01:20, value=155
           └─ Returns 15.5 kWh ❌

... This continues until API actually resets (could be minutes/hours) ...

01:00:00 - API finally resets
           ├─ Cache expired
           ├─ API call: todayYielding = 0 (finally reset!)
           ├─ Caches: timestamp=01:00:00, value=0
           └─ Returns 0.0 kWh ✓

01:30:00 - New generation starts
           └─ Returns 0.5 kWh ✓
```

## Root Causes

1. **API Reset Timing Unknown**:
   - We don't know WHEN the API resets daily counters
   - Could be at midnight UTC, server time, or device local time
   - Could lag by minutes or hours after midnight

2. **Passive Cache Invalidation**:
   - `should_invalidate_cache` is a property, not automatic
   - Relies on external caller (HA integration) to check and act
   - If HA update interval doesn't align with boundary window, invalidation is missed

3. **Window Timing Problem**:
   - Invalidation window: XX:55-XX:59 (5 minutes before hour)
   - This clears cache BEFORE midnight
   - But cache can be repopulated immediately after midnight with stale API data
   - Window reopens at 00:55, by which time we've had 55 minutes of stale data

4. **No Post-Boundary Protection**:
   - After crossing midnight, there's no special handling
   - No extended cache invalidation period
   - No detection of "first fetch after midnight might be stale"

## Why Current HA Integration Has This Issue

The HA integration's custom reset detection (which we've already identified as flawed) was probably an attempt to work around this cache timing issue:

```python
# HA integration sensor.py (FLAWED attempt to fix cache issue)
if date_changed:
    # Force reset to 0, ignoring API value
    self._last_valid_state = 0.0
    return 0.0
```

This "solution" causes different problems:
- ❌ Discards valid API data
- ❌ Creates artificial gap at midnight
- ❌ Doesn't actually solve cache problem (just masks it)

## Proposed Solutions

### Option 1: Extended Post-Boundary Invalidation Window (RECOMMENDED)

Extend the cache invalidation logic to cover AFTER the boundary as well:

```python
@property
def should_invalidate_cache(self) -> bool:
    """Check if cache should be invalidated for hour/date boundaries.

    Invalidation windows:
    - Pre-boundary: XX:55-XX:59 (5 minutes before hour)
    - Post-boundary: XX:00-XX:15 (15 minutes after hour)

    This ensures fresh data after midnight when API may have stale counters.
    """
    now = datetime.now()
    current_minute = now.minute

    # Pre-boundary window: XX:55-XX:59
    if 55 <= current_minute <= 59:
        return self._check_invalidation_rate_limit(now)

    # Post-boundary window: XX:00-XX:15
    if 0 <= current_minute <= 15:
        return self._check_invalidation_rate_limit(now)

    return False

def _check_invalidation_rate_limit(self, now: datetime) -> bool:
    """Check rate limit for cache invalidation."""
    # First run - invalidate immediately
    if self._last_cache_invalidation is None:
        return True

    # Hour boundary crossed - always invalidate once
    if now.hour != self._last_cache_invalidation.hour:
        return True

    # Rate limit: minimum interval between invalidations
    time_since_last = now - self._last_cache_invalidation
    min_interval = timedelta(minutes=MIN_CACHE_INVALIDATION_INTERVAL_MINUTES)
    return time_since_last >= min_interval
```

**Pros**:
- ✅ Catches stale API data in first 15 minutes after midnight
- ✅ Minimal code changes
- ✅ Backward compatible
- ✅ Handles API's unknown reset timing

**Cons**:
- ⚠️ More cache invalidations (performance impact)
- ⚠️ More API calls in post-midnight window

### Option 2: Automatic Cache Invalidation in Request Flow

Make cache invalidation automatic by checking in the request method:

```python
async def _request(
    self,
    method: str,
    endpoint: str,
    *,
    data: dict[str, Any] | None = None,
    cache_key: str | None = None,
    cache_endpoint: str | None = None,
) -> dict[str, Any]:
    """Make an HTTP request to the API."""

    # Auto-invalidate if needed (before checking cache)
    if self.should_invalidate_cache:
        self.clear_all_caches()

    # Check cache if enabled
    if cache_key and cache_endpoint and self._is_cache_valid(cache_key, cache_endpoint):
        cached = self._get_cached_response(cache_key)
        if cached:
            _LOGGER.debug("Using cached response for %s", cache_key)
            return cached

    # ... rest of request logic ...
```

**Pros**:
- ✅ Automatic - no reliance on external caller
- ✅ Every request triggers boundary check
- ✅ Guaranteed to catch boundary crossings

**Cons**:
- ❌ Adds overhead to EVERY request
- ❌ May clear cache unnecessarily
- ❌ Couples invalidation to request flow

### Option 3: Reduce Default TTL for Energy Endpoints

Lower the TTL for energy-related endpoints near boundaries:

```python
self._cache_ttl_config: dict[str, timedelta] = {
    "device_discovery": timedelta(minutes=15),
    "battery_info": timedelta(minutes=5),
    "parameter_read": timedelta(minutes=2),
    "quick_charge": timedelta(minutes=1),
    "inverter_runtime": timedelta(seconds=20),
    "inverter_energy": timedelta(seconds=20),  # Current
    "parallel_energy": timedelta(seconds=20),  # Current
}

# Dynamic TTL based on time
def _get_cache_ttl(self, endpoint_key: str) -> timedelta:
    """Get cache TTL, adjusted for boundary proximity."""
    base_ttl = self._cache_ttl_config.get(endpoint_key, timedelta(seconds=30))

    # If we're near a date boundary (midnight hour: 23:xx or 00:xx)
    current_hour = datetime.now().hour
    if current_hour in (23, 0):
        # Reduce TTL for energy endpoints to prevent stale data
        if "energy" in endpoint_key:
            return timedelta(seconds=10)  # Shorter TTL near midnight

    return base_ttl
```

**Pros**:
- ✅ Surgical fix for the specific problem
- ✅ Minimal performance impact outside boundary window
- ✅ Doesn't require external coordination

**Cons**:
- ⚠️ More complex logic
- ⚠️ Hardcoded hour check (assumes midnight boundary)
- ⚠️ More API calls during 23:xx and 00:xx hours

### Option 4: Expose Raw API Data + Document Limitation (RECOMMENDED)

**Acknowledge that this is fundamentally an API timing issue** that the library cannot fully solve:

1. **Library Level**:
   - Keep current TTL and invalidation logic
   - Document the limitation in docstrings
   - Recommend consumers implement application-specific handling

   ```python
   @property
   def today_yielding(self) -> float:
       """Today's PV generation in kWh.

       Note: This value resets daily at midnight (API server time).
       Due to API-side reset timing and caching, values retrieved
       shortly after midnight (00:00-01:00) may reflect yesterday's
       final total until the API backend resets.

       For critical accuracy at date boundaries, consider:
       - Shorter cache TTL for energy endpoints
       - Manual cache invalidation before/after midnight
       - Application-level staleness detection

       Returns:
           PV generation today in kWh (raw API value, scaled)
       """
       return self._energy.todayYielding / 10.0 if self._energy else 0.0
   ```

2. **Application Level** (HA Integration):
   - Use HA's `SensorStateClass.TOTAL_INCREASING`
   - Let HA's statistics handle value decreases as resets
   - No custom reset detection needed

**Pros**:
- ✅ Honest about limitations
- ✅ Puts responsibility where it belongs (API backend)
- ✅ Allows application-specific solutions
- ✅ No performance overhead

**Cons**:
- ⚠️ Doesn't "fix" the problem
- ⚠️ Users need to understand the limitation

## Alternative Approach: First Read After Hour Change (BEST SOLUTION)

**Insight**: Instead of time-based windows, invalidate cache on the FIRST request after any hour boundary.

### Key Advantages

1. ✅ **Simple Logic**: No complex time window calculations
2. ✅ **Guaranteed Fresh Data**: First request after boundary always fetches from API
3. ✅ **Minimal Performance Impact**: Only ONE extra API call per hour
4. ✅ **Works for All Boundaries**: Not just midnight, but every hour
5. ✅ **No False Invalidations**: Only triggers when actually crossing boundary
6. ✅ **Stateless Hour Tracking**: Just track last request's hour

### Implementation Strategy

```python
class LuxpowerClient:
    def __init__(self, ...):
        # ... existing init ...
        self._last_request_hour: int | None = None  # Track hour of last request

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        data: dict[str, Any] | None = None,
        cache_key: str | None = None,
        cache_endpoint: str | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to the API."""

        # Check if hour has changed since last request
        current_hour = datetime.now().hour
        if self._last_request_hour is not None and current_hour != self._last_request_hour:
            _LOGGER.info(
                "Hour boundary crossed from %d:xx to %d:xx, invalidating all caches",
                self._last_request_hour,
                current_hour,
            )
            self.clear_all_caches()

        self._last_request_hour = current_hour

        # Check cache if enabled
        if cache_key and cache_endpoint and self._is_cache_valid(cache_key, cache_endpoint):
            cached = self._get_cached_response(cache_key)
            if cached:
                _LOGGER.debug("Using cached response for %s", cache_key)
                return cached

        # ... rest of existing request logic ...
```

### Why This Works Better

**Timeline with First-Read Invalidation**:

```
23:58:00 - Request in hour 23
           ├─ self._last_request_hour = 23
           ├─ No hour change, check cache normally
           ├─ Cache miss, fetch: todayYielding = 155 (15.5 kWh)
           └─ Cache entry: timestamp=23:58:00, value=155

23:58:30 - Request in hour 23
           ├─ self._last_request_hour = 23 (no change)
           └─ Cache hit, returns 15.5 kWh ✓

23:59:30 - Request in hour 23
           ├─ self._last_request_hour = 23 (no change)
           └─ Cache hit, returns 15.5 kWh ✓

00:00:30 - Request in hour 0 ← HOUR CHANGED!
           ├─ Hour changed: 23 → 0
           ├─ INVALIDATE ALL CACHES ✅
           ├─ self._last_request_hour = 0
           ├─ Cache miss (just cleared)
           ├─ Fetch fresh: todayYielding = 155 (still stale from API)
           ├─ Cache entry: timestamp=00:00:30, value=155
           └─ Returns 15.5 kWh (stale, but fresh from API)

00:01:00 - Request in hour 0
           ├─ self._last_request_hour = 0 (no change)
           ├─ Cache hit (cached at 00:00:30, only 30s old)
           └─ Returns 15.5 kWh (still showing API stale data)

00:01:30 - Request in hour 0
           ├─ self._last_request_hour = 0 (no change)
           ├─ Cache expired (TTL=30s, cached 60s ago)
           ├─ Fetch fresh: todayYielding = 155 (API still stale!)
           └─ Returns 15.5 kWh

01:00:00 - Request in hour 1 ← HOUR CHANGED AGAIN!
           ├─ Hour changed: 0 → 1
           ├─ INVALIDATE ALL CACHES ✅
           ├─ self._last_request_hour = 1
           ├─ Fetch fresh: todayYielding = 0 (API finally reset!)
           └─ Returns 0.0 kWh ✓

01:30:00 - Request in hour 1
           └─ Returns 0.5 kWh ✓
```

**Key Points**:
- ✅ First request after each hour ALWAYS gets fresh data
- ✅ Subsequent requests in same hour can use cache (performance)
- ⚠️ Still subject to API stale data (unavoidable)
- ✅ But we're doing our part: always checking after boundaries

### Comparison with Time-Window Approach

| Aspect | Time Windows (XX:55-XX:14) | First-Read After Hour Change |
|--------|----------------------------|------------------------------|
| **Complexity** | High (window logic, rate limiting) | Low (single hour comparison) |
| **API Calls** | ~40 per boundary (with rate limit ~2) | Exactly 1 per hour boundary |
| **Guaranteed Fresh** | No (depends on polling timing) | Yes (first request always fresh) |
| **Performance** | More API calls during windows | Minimal (1 extra call/hour) |
| **False Positives** | Possible (multiple invalidations in window) | None (one-time per boundary) |
| **Code Maintainability** | Complex logic to maintain | Simple, easy to understand |
| **Testability** | Requires mocking time in windows | Easy to test hour changes |

### Edge Cases Handled

1. **Multiple Rapid Requests After Boundary**:
   ```
   00:00:10 - Request 1: Clears cache, fetches fresh, sets hour=0
   00:00:11 - Request 2: Hour still 0, uses cache from Request 1 ✓
   00:00:12 - Request 3: Hour still 0, uses cache from Request 1 ✓
   ```

2. **Long Gaps Between Requests**:
   ```
   22:30 - Last request (hour=22)
   02:15 - Next request (hour=2)
   ├─ Hour changed: 22 → 2
   ├─ Clear cache ✓
   └─ Fetch fresh data ✓
   ```

3. **Concurrent Requests During Boundary**:
   ```
   Thread 1 @ 00:00:01: hour changed (23→0), starts clearing cache
   Thread 2 @ 00:00:01: hour changed (23→0), starts clearing cache
   ├─ Both call clear_all_caches() (idempotent, safe) ✓
   ├─ Both fetch fresh data independently
   └─ Cache ends up with latest fetch result ✓
   ```

4. **System Clock Changes** (DST, manual adjustment):
   ```
   Hour jumps backward: 02:00 → 01:00 (DST fall back)
   ├─ Hour changed: 2 → 1
   ├─ Clear cache ✓
   └─ Fetch fresh data ✓

   Hour jumps forward: 01:59 → 03:00 (DST spring forward)
   ├─ Hour changed: 1 → 3
   ├─ Clear cache ✓
   └─ Fetch fresh data ✓
   ```

## Recommended Implementation (FINAL)

**Use "First Read After Hour Change" approach:**

1. ✅ **Track last request hour** in `_last_request_hour` field
2. ✅ **Check hour change in `_request()` method**
3. ✅ **Clear all caches on first request after hour change**
4. ✅ **Document limitation** (API stale data unavoidable)
5. ✅ **Remove time-window complexity** (`should_invalidate_cache` becomes simpler)

This provides the best balance of:
- Simplicity (minimal code)
- Performance (1 extra API call/hour)
- Reliability (guaranteed fresh after boundaries)
- Maintainability (easy to understand/test)

## Implementation Code (FINAL RECOMMENDED APPROACH)

### Simplified Client with Hour-Change Detection

```python
# client.py - Modified sections only

class LuxpowerClient:
    """Async client for Luxpower/EG4 API with automatic hour-boundary cache invalidation."""

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str = DEFAULT_BASE_URL,
        *,
        verify_ssl: bool = True,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the client."""
        # ... existing initialization ...

        # Response cache with TTL configuration
        self._response_cache: dict[str, dict[str, Any]] = {}
        self._cache_ttl_config: dict[str, timedelta] = {
            "device_discovery": timedelta(minutes=15),
            "battery_info": timedelta(minutes=5),
            "parameter_read": timedelta(minutes=2),
            "quick_charge": timedelta(minutes=1),
            "inverter_runtime": timedelta(seconds=20),
            "inverter_energy": timedelta(seconds=20),
            "parallel_energy": timedelta(seconds=20),
        }

        # Hour tracking for automatic cache invalidation
        self._last_request_hour: int | None = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        data: dict[str, Any] | None = None,
        cache_key: str | None = None,
        cache_endpoint: str | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to the API.

        Automatically invalidates cache on first request after hour boundary
        to ensure fresh data at date rollovers (especially midnight).

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (will be joined with base_url)
            data: Request data (will be form-encoded for POST)
            cache_key: Optional cache key for response caching
            cache_endpoint: Optional endpoint key for cache TTL lookup

        Returns:
            dict: JSON response from the API

        Raises:
            LuxpowerAuthError: If authentication fails
            LuxpowerConnectionError: If connection fails
            LuxpowerAPIError: If API returns an error
        """
        await self._ensure_session()

        # Auto-invalidate cache on first request after hour change
        current_hour = datetime.now().hour
        if self._last_request_hour is not None and current_hour != self._last_request_hour:
            _LOGGER.info(
                "Hour boundary crossed (hour %d → %d), invalidating all caches to ensure fresh data",
                self._last_request_hour,
                current_hour,
            )
            self.clear_cache()

        self._last_request_hour = current_hour

        # Check cache if enabled
        if cache_key and cache_endpoint and self._is_cache_valid(cache_key, cache_endpoint):
            cached = self._get_cached_response(cache_key)
            if cached:
                _LOGGER.debug("Using cached response for %s", cache_key)
                return cached

        # Apply backoff if needed
        await self._apply_backoff()

        # ... rest of existing request logic (unchanged) ...
```

### Remove Old should_invalidate_cache Property

The `should_invalidate_cache` property and related time-window logic can be removed entirely:

```python
# REMOVE THESE (no longer needed):
# - should_invalidate_cache property (lines 634-692)
# - _last_cache_invalidation field
# - clear_all_caches() method (use clear_cache() instead)
# - CACHE_INVALIDATION_WINDOW_MINUTES constant
# - MIN_CACHE_INVALIDATION_INTERVAL_MINUTES constant

# KEEP THESE:
# - clear_cache() method (existing simple cache clearing)
# - invalidate_cache_for_device() method (device-specific clearing)
# - cache_stats property (debugging/monitoring)
```

### Simplified Constants

```python
# constants.py - REMOVE old constants

# REMOVE:
# CACHE_INVALIDATION_WINDOW_MINUTES = 5
# MIN_CACHE_INVALIDATION_INTERVAL_MINUTES = 10

# These are no longer needed with the hour-change approach
```

### Testing

```python
# tests/unit/test_cache_hour_boundary.py

import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock
from pylxpweb.client import LuxpowerClient


@pytest.mark.asyncio
async def test_cache_cleared_on_hour_change():
    """Test that cache is cleared on first request after hour changes."""
    client = LuxpowerClient("user", "pass")

    # Mock the request method to avoid actual API calls
    with patch.object(client, '_ensure_session', new_callable=AsyncMock):
        with patch.object(client, '_apply_backoff', new_callable=AsyncMock):
            # First request at hour 23
            with patch('pylxpweb.client.datetime') as mock_dt:
                mock_dt.now.return_value = datetime(2025, 1, 1, 23, 30, 0)
                client._last_request_hour = None  # Simulate first run

                # Populate cache
                client._response_cache["test_key"] = {
                    "timestamp": datetime.now(),
                    "response": {"data": "old"}
                }
                assert len(client._response_cache) == 1

                # Make request (should set hour to 23)
                # ... trigger _request() ...

                assert client._last_request_hour == 23
                assert len(client._response_cache) == 1  # Cache still there

            # Second request at hour 0 (midnight crossed)
            with patch('pylxpweb.client.datetime') as mock_dt:
                mock_dt.now.return_value = datetime(2025, 1, 2, 0, 1, 0)

                # Make request (should detect hour change and clear cache)
                # ... trigger _request() ...

                assert client._last_request_hour == 0
                assert len(client._response_cache) == 0  # Cache cleared! ✓


@pytest.mark.asyncio
async def test_cache_not_cleared_within_same_hour():
    """Test that cache is NOT cleared for requests within same hour."""
    client = LuxpowerClient("user", "pass")

    with patch.object(client, '_ensure_session', new_callable=AsyncMock):
        with patch.object(client, '_apply_backoff', new_callable=AsyncMock):
            # All requests at hour 14
            with patch('pylxpweb.client.datetime') as mock_dt:
                # Request 1
                mock_dt.now.return_value = datetime(2025, 1, 1, 14, 10, 0)
                client._last_request_hour = None

                client._response_cache["test_key"] = {
                    "timestamp": datetime.now(),
                    "response": {"data": "value1"}
                }
                # ... trigger _request() ...
                assert client._last_request_hour == 14
                assert len(client._response_cache) == 1

                # Request 2 (same hour, cache should remain)
                mock_dt.now.return_value = datetime(2025, 1, 1, 14, 45, 0)
                # ... trigger _request() ...
                assert client._last_request_hour == 14
                assert len(client._response_cache) == 1  # Still there ✓


@pytest.mark.asyncio
async def test_dst_hour_changes():
    """Test hour boundary detection across DST transitions."""
    client = LuxpowerClient("user", "pass")

    # DST spring forward: 01:59 → 03:00
    with patch('pylxpweb.client.datetime') as mock_dt:
        # Before DST
        mock_dt.now.return_value = datetime(2025, 3, 9, 1, 59, 0)
        client._last_request_hour = 1

        client._response_cache["test"] = {"timestamp": datetime.now(), "response": {}}

        # After DST (hour jumped to 3)
        mock_dt.now.return_value = datetime(2025, 3, 9, 3, 0, 0)
        # ... trigger _request() ...

        # Hour changed from 1 to 3, cache should be cleared
        assert client._last_request_hour == 3
        assert len(client._response_cache) == 0  # Cleared ✓
```

## Old Extended Invalidation Window Approach (DEPRECATED)

**NOTE**: The following approach was considered but rejected in favor of the simpler "first-read after hour change" approach above.

### Extended Invalidation Window

```python
# constants.py
CACHE_INVALIDATION_PRE_WINDOW_MINUTES = 5   # XX:55-XX:59
CACHE_INVALIDATION_POST_WINDOW_MINUTES = 15  # XX:00-XX:14
MIN_CACHE_INVALIDATION_INTERVAL_MINUTES = 10

# client.py
@property
def should_invalidate_cache(self) -> bool:
    """Check if cache should be invalidated for hour/date boundaries.

    Invalidation occurs in two windows:
    1. Pre-boundary: XX:55-XX:59 (before hour rolls over)
    2. Post-boundary: XX:00-XX:14 (after hour rolls over)

    The post-boundary window is critical for midnight (00:00-00:14)
    to handle API stale data after date rollover.

    Rate limiting: Minimum 10 minutes between invalidations.

    Returns:
        True if cache should be cleared now, False otherwise.
    """
    now = datetime.now()
    current_minute = now.minute

    # Check if we're in either invalidation window
    in_pre_window = (60 - current_minute) <= CACHE_INVALIDATION_PRE_WINDOW_MINUTES
    in_post_window = current_minute <= (CACHE_INVALIDATION_POST_WINDOW_MINUTES - 1)

    if not (in_pre_window or in_post_window):
        return False

    # First run - invalidate immediately if within either window
    if self._last_cache_invalidation is None:
        _LOGGER.debug(
            "First run within invalidation window (minute=%d), will invalidate cache",
            current_minute,
        )
        return True

    # Check if we've crossed into a new hour
    last_hour = self._last_cache_invalidation.hour
    current_hour = now.hour
    if current_hour != last_hour:
        window_type = "post-boundary" if in_post_window else "pre-boundary"
        _LOGGER.debug(
            "Hour boundary crossed from %d:xx to %d:xx in %s window, will invalidate cache",
            last_hour,
            current_hour,
            window_type,
        )
        return True

    # Within window but check rate limit
    time_since_last = now - self._last_cache_invalidation
    min_interval = timedelta(minutes=MIN_CACHE_INVALIDATION_INTERVAL_MINUTES)
    should_invalidate = time_since_last >= min_interval

    if should_invalidate:
        window_type = "post-boundary" if in_post_window else "pre-boundary"
        _LOGGER.debug(
            "Within %s window (minute=%d) and %s since last invalidation, will invalidate cache",
            window_type,
            current_minute,
            time_since_last,
        )

    return should_invalidate
```

### Updated Property Docstrings

```python
@property
def today_yielding(self) -> float:
    """Today's PV generation in kWh.

    This value represents cumulative PV energy generated since midnight
    and resets daily at 00:00 (API server time).

    **Important Notes**:
    - Reset timing is controlled by the API backend
    - Values retrieved shortly after midnight (00:00-01:00) may be stale
    - The library implements extended cache invalidation (00:00-00:15) to
      minimize exposure to stale data, but cannot guarantee freshness
    - For Home Assistant: Use SensorStateClass.TOTAL_INCREASING and let
      HA's statistics system handle resets automatically

    Returns:
        PV generation today in kWh (0.0 if no data available)

    See Also:
        docs/MONOTONIC_INCREASING_VALUES.md - Detailed reset behavior analysis
        docs/CACHE_BOUNDARY_ISSUE.md - Cache timing and boundary handling
    """
    return self._energy.todayYielding / 10.0 if self._energy else 0.0
```

## Testing Strategy

### Unit Tests

```python
def test_cache_invalidation_pre_window():
    """Test cache invalidation in pre-boundary window (XX:55-XX:59)."""
    client = LuxpowerClient(...)

    # Mock time to 23:56
    with freeze_time("2025-01-01 23:56:00"):
        assert client.should_invalidate_cache is True

def test_cache_invalidation_post_window():
    """Test cache invalidation in post-boundary window (XX:00-XX:14)."""
    client = LuxpowerClient(...)

    # Mock time to 00:05 (just after midnight)
    with freeze_time("2025-01-02 00:05:00"):
        assert client.should_invalidate_cache is True

def test_cache_invalidation_outside_windows():
    """Test that cache is NOT invalidated outside windows."""
    client = LuxpowerClient(...)

    # Mock time to 00:20 (past post-window)
    with freeze_time("2025-01-02 00:20:00"):
        assert client.should_invalidate_cache is False

    # Mock time to 12:30 (midday, nowhere near boundary)
    with freeze_time("2025-01-02 12:30:00"):
        assert client.should_invalidate_cache is False
```

### Integration Tests

Test with real API to verify:
1. Cache clears during pre-window (23:55-23:59)
2. Cache clears during post-window (00:00-00:14)
3. Fresh data fetched after midnight despite potential API staleness
4. Rate limiting prevents excessive invalidations

## Performance Impact

### Current Behavior
- Invalidation window: 5 minutes/hour = 8.3% of time
- With 30-second HA update interval: ~10 invalidations per boundary

### Proposed Behavior
- Invalidation windows: 20 minutes/hour = 33.3% of time
- With 30-second HA update interval: ~40 invalidations per boundary

### Mitigation
- Rate limiting (10-minute minimum) reduces to ~2 invalidations per boundary
- Post-window only critical for midnight (00:00-00:14)
- Could make post-window conditional: `if current_hour == 0: check_post_window()`

## Conclusion

**The cache boundary issue is real and affects daily energy accuracy.**

**Recommended Solution**:
1. Implement extended post-boundary invalidation window (00:00-00:14)
2. Document API timing limitations in property docstrings
3. Recommend HA integration use `SensorStateClass.TOTAL_INCREASING`
4. Add comprehensive tests for boundary behavior

**This addresses the root cause (stale API data) while being honest about limitations (API timing unknown).**

---

**Status**: ✅ Analysis Complete - Implementation Needed
**Priority**: High (affects data accuracy at critical boundary)
**Target**: v0.4.0
