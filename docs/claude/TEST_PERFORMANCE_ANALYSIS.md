# Test Performance Analysis & Recommendations

**Date**: 2025-11-19
**Analysis**: Unit test suite performance bottlenecks

## Executive Summary

All packages are up to date, but unit tests are extremely slow (timing out after 60s+). Root cause identified: **inefficient test fixture scoping** causing the mock API server to be created and destroyed for every single test.

## Package Status

All dependencies are at their latest PyPI versions ✅:

| Package | Current | Latest | Status |
|---------|---------|--------|--------|
| aiohttp | 3.13.2 | 3.13.2 | ✓ Up to date |
| pydantic | 2.12.4 | 2.12.4 | ✓ Up to date |
| pytest | 9.0.1 | 9.0.1 | ✓ Up to date |
| pytest-asyncio | 1.3.0 | 1.3.0 | ✓ Up to date |
| pytest-cov | 7.0.0 | 7.0.0 | ✓ Up to date |
| pytest-aiohttp | 1.1.0 | 1.1.0 | ✓ Up to date |
| mypy | 1.18.2 | 1.18.2 | ✓ Up to date |
| ruff | 0.14.5 | 0.14.5 | ✓ Up to date |
| python-dotenv | 1.2.1 | 1.2.1 | ✓ Up to date |

## Performance Benchmarks

- **Non-async tests** (test_constants.py): 34 tests in **0.10s** ✅ (excellent)
- **Single async test**: 1 test in **0.05s** ✅ (excellent)
- **Full async test suite**: 136 tests **timing out after 60s+** ⚠️ (critical issue)

**Expected**: 136 tests should complete in < 10 seconds
**Actual**: Tests timeout or take 60+ seconds

## Root Cause Analysis

### Primary Issue: Inefficient Fixture Scoping

The `mock_api_server` fixture in `tests/conftest.py:307` is **function-scoped** (default), causing it to:

1. **Create** a full aiohttp TestServer for EVERY test
2. **Tear down** the server after EVERY test
3. Multiply: 136 tests × (server startup + teardown) = massive overhead

**Evidence**:
```python
@pytest.fixture  # ← No scope parameter = function scope (default)
async def mock_api_server(
    login_response: dict[str, Any],
    plants_response: dict[str, Any],
    ...
) -> AsyncGenerator[TestServer, None]:
    """Create a mock API server for testing."""

    # 600+ lines of route setup
    app = web.Application()
    app.router.add_post("/WManage/api/login", handle_login)
    # ... 30+ routes

    server = TestServer(app)
    await server.start_server()  # ← Expensive operation × 136 tests
    yield server
    await server.close()  # ← Expensive operation × 136 tests
```

### Secondary Issues

1. **Large fixture dependency chain**: 10 fixture dependencies loaded for every test
2. **No parallel test execution**: Tests run serially despite being independent
3. **Hook overhead**: Custom `pytest_runtest_call` hook in conftest.py redirects stdout/stderr for EVERY test
4. **Missing coverage optimization**: Coverage disabled (per git history) but still configured

## Recommendations

### 🔴 Critical (Immediate Impact)

#### 1. Change Fixture Scope to `session`

**Impact**: Reduce 136 server startups to just 1
**Expected speedup**: 50-100x faster (60s → 0.5-1.0s)

```python
@pytest.fixture(scope="session")  # ← Add scope="session"
async def mock_api_server(...) -> AsyncGenerator[TestServer, None]:
```

**Trade-off**: Server state is shared across tests, but since:
- Tests use different URLs/endpoints
- Server handlers are stateless
- Each test creates its own client instance
This is SAFE and recommended for unit tests.

#### 2. Simplify Fixture Dependency Chain

Move to lazy fixture loading:

```python
# Instead of injecting all 10 fixtures
@pytest.fixture(scope="session")
async def mock_api_server() -> AsyncGenerator[TestServer, None]:
    # Load samples inside the fixture
    login_response = load_sample("login.json")
    plants_response = {"total": 1, "rows": load_sample("plants.json")}
    # ...
```

**Impact**: Reduce fixture initialization overhead
**Expected speedup**: Additional 2-5x faster

### 🟡 High Priority (Significant Impact)

#### 3. Enable Parallel Test Execution

Install and configure pytest-xdist:

```bash
uv add --dev pytest-xdist
```

```toml
# pyproject.toml
[tool.pytest.ini_options]
addopts = [
    "--strict-markers",
    "-n auto",  # ← Run tests in parallel using all CPU cores
]
```

**Impact**: Utilize all CPU cores for parallel execution
**Expected speedup**: 4-8x faster (depending on CPU cores)

#### 4. Optimize CI Configuration

```yaml
# .github/workflows/ci.yml
- name: Run unit tests
  run: uv run pytest tests/unit/ -v -n auto  # ← Add -n auto for parallel execution
```

**Impact**: Faster CI builds
**Expected time**: < 5 seconds for unit tests

### 🟢 Medium Priority (Optimization)

#### 5. Remove Redaction Hook Overhead

The `pytest_runtest_call` hook in conftest.py:56-107 intercepts EVERY test to redact output. This adds overhead even when not in CI.

```python
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    """Hook to redact sensitive information from test output in CI."""
    if is_ci_environment():  # ← Only runs in CI, but ALWAYS evaluated
        # Capture and redact output (expensive)
```

**Optimization**: Use pytest marks instead:

```python
# Only apply to integration tests that might leak data
@pytest.mark.integration
@pytest.mark.redact_output
def test_with_real_data():
    ...
```

#### 6. Optimize Coverage Collection

Currently disabled in CI (per commit `caf1b43`), but still configured in pyproject.toml.

Options:
1. **Remove coverage** from unit test run (keep for integration tests only)
2. **Re-enable** with optimized settings:

```toml
[tool.coverage.run]
parallel = true  # Enable parallel coverage collection
concurrency = ["multiprocessing"]  # Support pytest-xdist
```

### 🔵 Low Priority (Nice to Have)

#### 7. Test Organization

Split test files by execution speed:
- `tests/unit/fast/` - Pure Python tests (< 0.1s each)
- `tests/unit/slow/` - Tests requiring mock server (< 1s each)

CI can run fast tests first for rapid feedback.

#### 8. Add Test Timing Monitoring

```toml
[tool.pytest.ini_options]
addopts = [
    "--strict-markers",
    "--durations=10",  # Always show 10 slowest tests
]
```

## Implementation Priority

### Phase 1: Immediate Fixes (< 5 minutes, 50-100x speedup)
1. ✅ Add `scope="session"` to `mock_api_server` fixture
2. ✅ Test locally to verify performance improvement
3. ✅ Commit and push to trigger CI

### Phase 2: Parallel Execution (< 10 minutes, additional 4-8x speedup)
1. ✅ Add pytest-xdist dependency
2. ✅ Update pytest config with `-n auto`
3. ✅ Update CI workflow
4. ✅ Verify tests still pass in parallel

### Phase 3: Optimizations (< 30 minutes, marginal improvements)
1. Refactor fixture loading (lazy loading)
2. Optimize redaction hook
3. Re-enable coverage with parallel support

## Expected Results

| Phase | Time | Speedup | Total Time |
|-------|------|---------|------------|
| Current | N/A | 1x | 60+ seconds (timeout) |
| Phase 1 | 5 min | 50-100x | **0.5-1.0 seconds** ✅ |
| Phase 2 | 10 min | 4-8x | **0.1-0.2 seconds** ✅ |
| Phase 3 | 30 min | 1.5-2x | **< 0.1 seconds** ✅ |

## Verification Commands

```bash
# Baseline (current - slow)
time uv run pytest tests/unit/ -v

# After Phase 1 (session scope)
time uv run pytest tests/unit/ -v

# After Phase 2 (parallel)
time uv run pytest tests/unit/ -v -n auto

# Check fixture scope is working
uv run pytest tests/unit/ -v --setup-show | grep mock_api_server
```

## CI Impact

**Current CI timeout**: 15 minutes (hitting timeout)
**After fixes**: < 10 seconds for unit tests

**Cost savings**:
- Faster feedback loops (seconds vs minutes)
- Lower GitHub Actions minutes consumption
- Better developer experience

## References

- pytest fixtures: https://docs.pytest.org/en/stable/how-to/fixtures.html#scope-sharing-fixtures-across-classes-modules-packages-or-session
- pytest-xdist: https://pytest-xdist.readthedocs.io/
- pytest-asyncio: https://pytest-asyncio.readthedocs.io/
- Test performance: https://docs.pytest.org/en/stable/how-to/failures.html#duration-profiling
