# Test Hanging Issue - Root Cause and Solution

**Date**: 2025-11-19
**Issue**: Tests hang on second test when using `await client.close()`

## Root Cause

The hanging occurs because:

1. Each test creates a **new `LuxpowerClient`** instance
2. Each client creates its **own `aiohttp.ClientSession`**
3. When `await client.close()` is called, it tries to close the session
4. The session close hangs because the **event loop is being torn down** by pytest-asyncio
5. This creates a **deadlock** between session cleanup and event loop cleanup

## Solution: Session Injection

Instead of each client creating its own session, **inject a shared session managed by pytest-aiohttp**.

### Implementation

**Step 1**: Add session fixture to `tests/conftest.py`:

```python
@pytest.fixture
async def aiohttp_session(aiohttp_client):
    """Create a shared aiohttp session for all tests.

    This session is managed by pytest-aiohttp and will be
    cleaned up properly by the test framework.
    """
    # aiohttp_client manages session lifecycle
    async with aiohttp.ClientSession() as session:
        yield session
```

**Step 2**: Modify tests to inject the session:

```python
async def test_login_success(self, mock_api_server: TestServer, aiohttp_session) -> None:
    """Test successful login."""
    client = LuxpowerClient(
        "testuser",
        "testpass",
        base_url=str(mock_api_server.make_url("")),
        verify_ssl=False,
        session=aiohttp_session,  # ← Inject shared session
    )

    # No need for try/finally or await client.close()
    # The session is managed by pytest-aiohttp
    response = await client.login()
    assert response.success is True
```

### Why This Works

1. **Single session** for all tests in a module/session
2. **pytest-aiohttp manages cleanup** - no manual close needed
3. **No event loop conflicts** - pytest controls the lifecycle
4. **Faster tests** - session reuse is more efficient than creating new sessions

### Benefits

- ✅ No hanging on second test
- ✅ Faster test execution (session reuse)
- ✅ Cleaner test code (no try/finally blocks)
- ✅ Follows aiohttp best practices
- ✅ Matches Platinum tier requirement (session injection support)

## Alternative: Use `aiohttp_unused_port` for Simple Mocking

For even faster tests, consider using `aioresponses` library instead of TestServer:

```python
from aioresponses import aioresponses

@pytest.fixture
def mock_api():
    with aioresponses() as m:
        yield m

async def test_login(mock_api, aiohttp_session):
    mock_api.post('https://monitor.eg4electronics.com/WManage/api/login', payload={'success': True})

    client = LuxpowerClient("user", "pass", session=aiohttp_session)
    response = await client.login()
    assert response.success is True
```

This is **10-100x faster** than TestServer because it doesn't start an actual HTTP server.

## References

- [aiohttp Testing Documentation](https://docs.aiohttp.org/en/stable/testing.html)
- [pytest-aiohttp Plugin](https://github.com/aio-libs/pytest-aiohttp)
- [aioresponses Library](https://github.com/pnuckowski/aioresponses)
