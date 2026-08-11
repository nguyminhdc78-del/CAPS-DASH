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
        limiter.record_failure("k")
    limiter.check("k")


def test_limiter_blocks_at_the_threshold() -> None:
    limiter = SlidingWindowLimiter(max_attempts=3, window_s=60)
    for _ in range(3):
        limiter.record_failure("k")

    with pytest.raises(RateLimitedError) as caught:
        limiter.check("k")
    assert caught.value.retry_after_s is not None
    assert caught.value.retry_after_s > 0


def test_a_successful_login_clears_the_history() -> None:
    limiter = SlidingWindowLimiter(max_attempts=3, window_s=60)
    for _ in range(2):
        limiter.record_failure("k")
    limiter.reset("k")

    for _ in range(2):
        limiter.check("k")
        limiter.record_failure("k")


def test_attempts_age_out_of_the_window() -> None:
    """Stepped clock, not sleep.

    A short real window plus a sleep is a coin flip on Windows, where the
    timer granularity is coarse enough to land either side of the boundary.
    """
    now = [1000.0]
    limiter = SlidingWindowLimiter(max_attempts=2, window_s=60, clock=lambda: now[0])

    limiter.record_failure("k")
    limiter.record_failure("k")
    with pytest.raises(RateLimitedError):
        limiter.check("k")

    now[0] += 61
    limiter.check("k")


def test_retry_after_shrinks_as_the_window_passes() -> None:
    now = [1000.0]
    limiter = SlidingWindowLimiter(max_attempts=1, window_s=60, clock=lambda: now[0])
    limiter.record_failure("k")

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
    limiter.record_failure(user_key("guard"))
    limiter.check(user_key("someone-else"))
    limiter.check(ip_key("10.0.0.1"))


def test_usernames_are_normalised_so_case_cannot_dodge_the_limit() -> None:
    assert user_key("Guard") == user_key("  guard  ")


def test_sweep_drops_idle_keys() -> None:
    """Otherwise the dict grows one entry per username ever attempted, which
    is unbounded and attacker-controlled."""
    now = [1000.0]
    limiter = SlidingWindowLimiter(max_attempts=5, window_s=60, clock=lambda: now[0])
    limiter.record_failure("a")
    limiter.record_failure("b")

    assert limiter.sweep_idle() == 0, "keys with live failures must be kept"

    now[0] += 61
    assert limiter.sweep_idle() == 2
    assert limiter.sweep_idle() == 0
