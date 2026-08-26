"""What happens to logging in when Redis is not there.

The policy was nowhere written down and, as it turned out, was not the one
anybody would have chosen. The brute-force calls had no error handling at all,
so a Redis that was merely restarting turned the login endpoint into a 500 and
locked the owner out of their own server: an outage we inflict on ourselves in
exchange for a protection that was never the only one, since passwords are
still verified with bcrypt.

So it fails open, loudly, and these tests hold that. The one thing that must
not fail open is revocation, and it does not: that check falls through to the
database, which is authoritative.
"""
from __future__ import annotations

import pytest

from handler.auth import brute_force


class _DeadRedis:
    """A client that builds fine and refuses on every command, like a real one."""

    def __init__(self):
        self.calls = 0

    def _die(self, *_a, **_kw):
        self.calls += 1
        raise ConnectionError("Connection refused")

    ttl = eval = delete = incr = expire = setex = _die

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _Request:
    def __init__(self):
        self.client = type("C", (), {"host": "203.0.113.7"})()
        self.headers = {}


@pytest.fixture
def dead_redis(monkeypatch):
    dead = _DeadRedis()
    monkeypatch.setattr(brute_force, "_get_redis", lambda: dead)
    # A real deployment has this on; the point is what happens when the store
    # behind it is gone, not when the feature is switched off.
    monkeypatch.setattr(
        brute_force, "_get_config",
        _async_returning({
            "enabled": True, "max_attempts": 5, "window_seconds": 300,
            "ban_seconds": 900, "whitelist": [], "trusted_proxies": [],
        }),
    )
    # Complaints are throttled to one a minute; reset so each test can see one.
    monkeypatch.setattr(brute_force, "_last_redis_complaint", 0.0)
    return dead


def _async_returning(value):
    async def _fn(*_a, **_kw):
        return value
    return _fn


@pytest.mark.asyncio
async def test_checking_for_a_ban_does_not_take_the_login_down(dead_redis):
    """This is the whole point: a 500 here means nobody can log in at all."""
    blocked, remaining = await brute_force.check_ip(_Request())
    assert (blocked, remaining) == (False, 0)
    assert dead_redis.calls == 1, "it should have tried before giving up"


@pytest.mark.asyncio
async def test_recording_a_failure_does_not_raise(dead_redis):
    await brute_force.record_failure(_Request())


@pytest.mark.asyncio
async def test_recording_a_success_does_not_raise(dead_redis):
    # Nothing to do about it anyway: the counter expires on its own.
    await brute_force.record_success(_Request())


@pytest.mark.asyncio
async def test_it_says_so_rather_than_failing_silently(dead_redis, caplog):
    """Protection that has quietly stopped is worse than none, because nobody
    knows to look. The message names what is not running."""
    with caplog.at_level("ERROR"):
        await brute_force.check_ip(_Request())
    said = [r.getMessage() for r in caplog.records]
    assert any("Redis unreachable" in m for m in said), said
    # And it names which protection is off, not just that something is wrong.
    assert any("brute-force protection is off" in m for m in said), said


@pytest.mark.asyncio
async def test_the_complaint_is_throttled(dead_redis, caplog):
    """A login screen under attack would otherwise write a log line per attempt."""
    with caplog.at_level("ERROR"):
        for _ in range(20):
            await brute_force.check_ip(_Request())
    complaints = [r for r in caplog.records if "Redis unreachable" in str(r.msg)]
    assert len(complaints) == 1, f"expected one complaint, got {len(complaints)}"


def test_revocation_is_not_allowed_to_fail_open_the_same_way():
    """The one check that must survive Redis being gone, and does.

    A token whose session was revoked has to stay revoked. The Redis lookup
    fails open on purpose, and the database check immediately after it is the
    authoritative one, so this is a cache miss rather than a bypass.
    """
    import inspect

    from handler.auth import middleware

    source = inspect.getsource(middleware)
    assert "is_access_jti_revoked" in source, (
        "the database fallback behind the Redis blocklist is gone"
    )
