"""Password hashing, JWT handling, and the login rate limiter."""

from __future__ import annotations

import datetime as dt

import jwt
import pytest

from caps_dash.config.settings import Settings
from caps_dash.errors.exceptions import AuthError, RateLimitedError
from caps_dash.security.jwt_tokens import decode_token, encode_access, encode_refresh
from caps_dash.security.password_hasher import (
    DUMMY_HASH,
    hash_password,
    needs_rehash,
    verify_password,
)
from caps_dash.security.rate_limiter import SlidingWindowLimiter, ip_key, user_key


@pytest.fixture
def settings() -> Settings:
    return Settings(secret_key="a-test-signing-key-padded-to-32-bytes-min", access_token_ttl_min=15)


# --- Password hashing --------------------------------------------------------


def test_hash_verifies_against_its_own_password() -> None:
    stored = hash_password("correct-horse")
    assert verify_password(stored, "correct-horse")


def test_hash_rejects_a_wrong_password() -> None:
    assert not verify_password(hash_password("correct-horse"), "wrong-horse")


def test_hashes_are_salted_so_two_users_with_one_password_differ() -> None:
    """Identical hashes would let an attacker crack both accounts at once."""
    assert hash_password("same-password") != hash_password("same-password")


def test_hash_is_argon2id_not_a_plain_digest() -> None:
    assert hash_password("x").startswith("$argon2id$")


def test_verify_never_raises_on_a_malformed_stored_hash() -> None:
    """A corrupt row is a failed login, not a 500 on the login endpoint."""
    assert not verify_password("not-a-hash", "anything")
    assert not verify_password("", "anything")


def test_dummy_hash_is_usable_for_timing_equalisation() -> None:
    # Verified against when the username is unknown, so both paths cost the
    # same and account existence cannot be timed.
    assert not verify_password(DUMMY_HASH, "anything")


def test_needs_rehash_flags_an_unparseable_hash() -> None:
    assert needs_rehash("garbage")


def test_needs_rehash_is_false_for_a_current_hash() -> None:
    assert not needs_rehash(hash_password("x"))


# --- JWT ---------------------------------------------------------------------


def test_access_token_round_trips(settings: Settings) -> None:
    token = encode_access(settings, username="guard", role="security", token_version=3)
    claims = decode_token(settings, token, expected_type="access")

    assert claims.subject == "guard"
    assert claims.role == "security"
    assert claims.token_version == 3


def test_refresh_token_carries_a_unique_jti(settings: Settings) -> None:
    first, jti_a, _ = encode_refresh(settings, username="guard", token_version=0)
    _, jti_b, _ = encode_refresh(settings, username="guard", token_version=0)

    assert jti_a != jti_b
    assert decode_token(settings, first, expected_type="refresh").jti == jti_a


def test_a_refresh_token_is_refused_where_an_access_token_is_expected(
    settings: Settings,
) -> None:
    """Token confusion: without the typ check, a 7-day credential would work
    as a 15-minute one."""
    token, _, _ = encode_refresh(settings, username="guard", token_version=0)
    with pytest.raises(AuthError, match="Wrong token type"):
        decode_token(settings, token, expected_type="access")


def test_a_token_signed_with_another_key_is_invalid(settings: Settings) -> None:
    other = Settings(secret_key="a-different-key-padded-to-32-bytes-min")
    token = encode_access(other, username="guard", role="security", token_version=0)

    with pytest.raises(AuthError) as caught:
        decode_token(settings, token, expected_type="access")
    assert caught.value.code == "AUTH_TOKEN_INVALID"


def test_an_expired_token_reports_expiry_not_invalidity(settings: Settings) -> None:
    """The frontend refreshes on expiry and gives up on invalidity, so the two
    must not be collapsed into one code."""
    past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
    token = jwt.encode(
        {"sub": "guard", "typ": "access", "tv": 0, "iat": past, "exp": past},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )

    with pytest.raises(AuthError) as caught:
        decode_token(settings, token, expected_type="access")
    assert caught.value.code == "AUTH_TOKEN_EXPIRED"


def test_a_token_missing_required_claims_is_invalid(settings: Settings) -> None:
    token = jwt.encode(
        {"sub": "guard"}, settings.secret_key.get_secret_value(), algorithm="HS256"
    )
    with pytest.raises(AuthError):
        decode_token(settings, token, expected_type="access")


def test_an_unsigned_token_is_refused(settings: Settings) -> None:
    """The alg=none attack."""
    token = jwt.encode(
        {"sub": "guard", "typ": "access", "iat": 0, "exp": 9_999_999_999},
        key="",
        algorithm="none",
    )
    with pytest.raises(AuthError):
        decode_token(settings, token, expected_type="access")


# --- Rate limiter ------------------------------------------------------------


def test_limiter_allows_attempts_below_the_threshold() -> None:
    limiter = SlidingWindowLimiter(max_attempts=3, window_s=60)
    for _ in range(2):
        limiter.check("k")
        limiter.record("k")
    limiter.check("k")


def test_limiter_blocks_at_the_threshold() -> None:
    limiter = SlidingWindowLimiter(max_attempts=3, window_s=60)
    for _ in range(3):
        limiter.record("k")

    with pytest.raises(RateLimitedError) as caught:
        limiter.check("k")
    assert caught.value.retry_after_s is not None
    assert caught.value.retry_after_s > 0


def test_a_successful_login_clears_the_history() -> None:
    limiter = SlidingWindowLimiter(max_attempts=3, window_s=60)
    for _ in range(2):
        limiter.record("k")
    limiter.reset("k")

    for _ in range(2):
        limiter.check("k")
        limiter.record("k")


def test_attempts_age_out_of_the_window() -> None:
    """Stepped clock, not sleep.

    A short real window plus a sleep is a coin flip on Windows, where the
    timer granularity is coarse enough to land either side of the boundary.
    """
    now = [1000.0]
    limiter = SlidingWindowLimiter(max_attempts=2, window_s=60, clock=lambda: now[0])

    limiter.record("k")
    limiter.record("k")
    with pytest.raises(RateLimitedError):
        limiter.check("k")

    now[0] += 61
    limiter.check("k")


def test_retry_after_shrinks_as_the_window_passes() -> None:
    now = [1000.0]
    limiter = SlidingWindowLimiter(max_attempts=1, window_s=60, clock=lambda: now[0])
    limiter.record("k")

    with pytest.raises(RateLimitedError) as first:
        limiter.check("k")
    now[0] += 30
    with pytest.raises(RateLimitedError) as second:
        limiter.check("k")

    assert first.value.retry_after_s is not None
    assert second.value.retry_after_s is not None
    assert second.value.retry_after_s < first.value.retry_after_s


def test_keys_are_independent() -> None:
    limiter = SlidingWindowLimiter(max_attempts=1, window_s=60)
    limiter.record(user_key("guard"))
    limiter.check(user_key("someone-else"))
    limiter.check(ip_key("10.0.0.1"))


def test_usernames_are_normalised_so_case_cannot_dodge_the_limit() -> None:
    assert user_key("Guard") == user_key("  guard  ")


def test_sweep_drops_idle_keys() -> None:
    """Otherwise the dict grows one entry per username ever attempted, which
    is unbounded and attacker-controlled."""
    now = [1000.0]
    limiter = SlidingWindowLimiter(max_attempts=5, window_s=60, clock=lambda: now[0])
    limiter.record("a")
    limiter.record("b")

    assert limiter.sweep_idle() == 0, "keys with live failures must be kept"

    now[0] += 61
    assert limiter.sweep_idle() == 2
    assert limiter.sweep_idle() == 0


def test_custom_message_reaches_the_error() -> None:
    """The limiter can be configured with a custom message; it must appear in the raised error."""
    limiter = SlidingWindowLimiter(
        max_attempts=1, window_s=60, message="Custom rate limit message"
    )
    limiter.record("k")

    with pytest.raises(RateLimitedError) as caught:
        limiter.check("k")
    assert caught.value.message == "Custom rate limit message"


def test_default_message_unchanged() -> None:
    """The default lockout message for a limiter without a custom message."""
    limiter = SlidingWindowLimiter(max_attempts=1, window_s=60)
    limiter.record("k")

    with pytest.raises(RateLimitedError) as caught:
        limiter.check("k")
    # The default message is the class's default, not None or empty
    assert caught.value.message is not None
    assert len(caught.value.message) > 0


def test_check_then_record_without_reset_throttles_like_public_kiosk() -> None:
    """The public plate search uses check-then-record without reset: every search
    counts against the budget, and a successful search doesn't clear it.
    After N calls, the next check raises."""
    limiter = SlidingWindowLimiter(max_attempts=3, window_s=60)

    # First 3 requests: check OK, record counts against budget
    for _ in range(3):
        limiter.check("ip:1.2.3.4")
        limiter.record("ip:1.2.3.4")

    # 4th check fails - no reset happened, so the limit is hit
    with pytest.raises(RateLimitedError):
        limiter.check("ip:1.2.3.4")


def test_login_style_reset_on_success_clears_the_limit() -> None:
    """The login route uses reset() on successful login: a correct password clears
    the failure count. This is a lockout limiter, not a throttle."""
    limiter = SlidingWindowLimiter(max_attempts=3, window_s=60)

    # 2 failures
    limiter.record("user:guard")
    limiter.record("user:guard")

    # Success: reset clears it
    limiter.reset("user:guard")

    # Now we can do 3 more attempts before hitting the limit
    for _ in range(3):
        limiter.check("user:guard")
        limiter.record("user:guard")
    with pytest.raises(RateLimitedError):
        limiter.check("user:guard")


def test_sweep_idle_on_two_independent_limiters() -> None:
    """The job runs both limiters' sweep_idle and sums the counts.
    This verifies that each limiter can independently track and clean stale keys."""
    now = [1000.0]
    login_limiter = SlidingWindowLimiter(max_attempts=5, window_s=60, clock=lambda: now[0])
    kiosk_limiter = SlidingWindowLimiter(max_attempts=3, window_s=60, clock=lambda: now[0])

    # Record some keys in each
    login_limiter.record(user_key("guard"))
    login_limiter.record(user_key("admin"))
    kiosk_limiter.record(ip_key("1.2.3.4"))
    kiosk_limiter.record(ip_key("1.2.3.5"))

    # Before window expires, both are kept
    assert login_limiter.sweep_idle() == 0
    assert kiosk_limiter.sweep_idle() == 0

    # After window expires, sweep removes from both
    now[0] += 61
    login_removed = login_limiter.sweep_idle()
    kiosk_removed = kiosk_limiter.sweep_idle()
    assert login_removed == 2
    assert kiosk_removed == 2

    # A fresh entry is kept after sweep
    login_limiter.record(user_key("newuser"))
    kiosk_limiter.record(ip_key("5.6.7.8"))
    now[0] += 1  # Still in window
    assert login_limiter.sweep_idle() == 0
    assert kiosk_limiter.sweep_idle() == 0


def test_ip_key_creates_distinct_keys_for_distinct_ips() -> None:
    """ip_key('1.2.3.4') != ip_key('1.2.3.5'): each IP is its own bucket."""
    key_a = ip_key("1.2.3.4")
    key_b = ip_key("1.2.3.5")
    key_a_again = ip_key("1.2.3.4")

    assert key_a != key_b
    assert key_a == key_a_again


def test_client_ip_returns_empty_string_when_request_client_is_none() -> None:
    """Some ASGI transports set request.client to None. client_ip must handle it gracefully."""
    from unittest.mock import MagicMock

    from caps_dash.security.client_ip import client_ip as client_ip_fn

    # Mock request with client=None
    request = MagicMock()
    request.client = None

    result = client_ip_fn(request)
    assert result == ""


def test_client_ip_returns_host_when_client_exists() -> None:
    """When request.client is set, client_ip returns the host part."""
    from unittest.mock import MagicMock

    from caps_dash.security.client_ip import client_ip as client_ip_fn

    # Mock request.client as an object with .host attribute
    request = MagicMock()
    client_obj = MagicMock()
    client_obj.host = "192.168.1.100"
    request.client = client_obj

    result = client_ip_fn(request)
    assert result == "192.168.1.100"


def test_try_acquire_admits_exactly_the_budget_under_concurrency() -> None:
    """The public search throttle must not overshoot when threads race.

    `check()` then `record()` takes the lock twice, so N threads can all pass
    the check before any records - admitting far more than the budget. This
    drives the real threadpool situation: the sum of admitted requests must
    never exceed `max_attempts`, however the interleaving falls.
    """
    import threading

    limiter = SlidingWindowLimiter(max_attempts=10, window_s=60)
    admitted = 0
    admitted_lock = threading.Lock()
    start = threading.Barrier(24)

    def attempt() -> None:
        nonlocal admitted
        start.wait()
        try:
            limiter.try_acquire(ip_key("1.2.3.4"))
        except RateLimitedError:
            return
        with admitted_lock:
            admitted += 1

    threads = [threading.Thread(target=attempt) for _ in range(24)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert admitted == 10


def test_try_acquire_does_not_spend_budget_on_a_refused_call() -> None:
    """An over-budget caller must not extend its own lockout by retrying."""
    now = [1000.0]
    limiter = SlidingWindowLimiter(max_attempts=2, window_s=60, clock=lambda: now[0])

    limiter.try_acquire("k")
    limiter.try_acquire("k")
    for _ in range(5):
        with pytest.raises(RateLimitedError):
            limiter.try_acquire("k")

    # The 5 refused calls recorded nothing, so the window clears on schedule.
    now[0] += 61
    limiter.try_acquire("k")
