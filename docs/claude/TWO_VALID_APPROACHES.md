# Two Valid Approaches for Testing aiohttp Clients

**Date**: 2025-11-19

Both approaches work well for testing aiohttp client libraries. Choose based on your needs.

## Approach 1: aioresponses (Our Solution)

**Speed**: ⚡ Fastest (1.1s for 4 tests)
**Complexity**: Low
**Use Case**: Pure unit tests, no actual HTTP server needed

### Pros
- Extremely fast (no real server)
- Simple setup
- Industry standard for client testing
- Works with any base URL

### Cons
- Mocks at HTTP level (less realistic)
- Need to maintain mock responses

### Implementation
```python
# conftest.py
@pytest.fixture
def mocked_api():
    with aioresponses() as m:
        yield m

# test_client.py
@pytest.mark.asyncio
async def test_login(mocked_api, login_response):
    mocked_api.post("https://api.example.com/login", payload=login_response)

    client = MyClient("user", "pass")
    result = await client.login()
    await client.close()
```

### Performance
- **180 tests**: ~1-2 seconds estimated
- **No hanging issues**
- **Minimal overhead**

---

## Approach 2: pytest-aiohttp with Session Injection (pythermacell style)

**Speed**: ⚡ Very Fast (1.43s for 180 tests - proven!)
**Complexity**: Medium
**Use Case**: Integration-style tests with realistic HTTP flow

### Pros
- Real HTTP server (more realistic)
- Tests actual aiohttp request/response cycle
- Catches networking edge cases
- Proven fast (1.43s for 180 tests in production)

### Cons
- Slightly more complex setup
- Need to inject session into client
- App fixture per test file

### Implementation
```python
# test_client.py (app fixture in each test file)
@pytest.fixture
def app():
    """Create test aiohttp app with mock endpoints."""
    app = web.Application()

    async def handle_login(request):
        return web.json_response({"success": True, "userId": 123})

    app.router.add_post("/api/login", handle_login)
    return app

@pytest.mark.asyncio
async def test_login(aiohttp_client, app):
    # aiohttp_client creates test server automatically
    client = await aiohttp_client(app)

    # CRITICAL: Inject test client's session
    my_client = MyClient("user", "pass")
    my_client._session = client.session
    my_client._base_url = str(client.make_url(""))

    result = await my_client.login()
    # No manual close needed - aiohttp_client handles cleanup
```

### Why It Works
1. **Session reuse**: `aiohttp_client` creates one server per test
2. **Automatic cleanup**: pytest-aiohttp handles server lifecycle
3. **No manual close**: Session managed by fixture
4. **Fast startup**: Modern pytest-aiohttp is optimized

### Performance (Proven)
- **180 tests**: 1.43 seconds
- **No hanging issues**
- **Real HTTP testing**

---

## Comparison

| Metric | aioresponses | pytest-aiohttp |
|--------|--------------|----------------|
| Speed (180 tests) | ~1-2s (estimated) | 1.43s (proven) |
| Complexity | Low | Medium |
| Realism | HTTP mocking | Real HTTP server |
| Setup | Minimal | Per-file app fixture |
| Maintenance | Mock responses | Route handlers |
| Hanging issues | None | None (with session injection) |

## Why Our Original Approach Failed

**Problem**: We used `TestServer` directly with:
- Global `mock_api_server` fixture in conftest.py
- Manual session management (`await client.close()`)
- No session injection

**Result**: Server lifecycle conflicts, hanging on cleanup

## Recommendation

**For this project**: Either approach works!

### Use aioresponses if:
- You want simplest possible tests
- Speed is critical (though both are fast)
- You're testing pure API client logic

### Use pytest-aiohttp if:
- You want integration-style testing
- You need to test HTTP-specific behavior (redirects, cookies, etc.)
- You want proven 1.43s/180 tests performance

## Migration Note

Our current `aioresponses` solution works perfectly. We could also adopt the pythermacell pattern by:

1. Moving app fixture to test files
2. Injecting `client.session` from aiohttp_client
3. Removing manual `await client.close()` calls

Both approaches are professional and production-ready.

## References

- [pythermacell tests](https://github.com/joyfulhouse/pythermacell/tree/main/tests) - Proven pytest-aiohttp approach
- [aioresponses](https://github.com/pnuckowski/aioresponses) - Industry standard HTTP mocking
- [pytest-aiohttp](https://github.com/aio-libs/pytest-aiohttp) - Official pytest plugin
