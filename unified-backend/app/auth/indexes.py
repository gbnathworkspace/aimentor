"""MongoDB index definitions for authentication collections.

Ensures all required indexes for the self-hosted auth system are created
on application startup. Includes unique constraints, TTL indexes for
automatic document expiration, and compound indexes for query performance.
"""

from pymongo import ASCENDING

from app.config.database import get_db


async def ensure_auth_indexes() -> None:
    """Create indexes for all auth-related collections.

    Collections and their indexes:
      - users: unique user_id, unique email
      - refresh_tokens: unique token, index on user_id, TTL on expires_at
      - otp_codes: index on email, TTL on expires_at
      - oauth_states: unique state, TTL on expires_at
      - rate_limits: compound on key+action+timestamp, TTL on expires_at
    """
    db = get_db()

    # --- users collection ---
    users = db["users"]
    await users.create_index("user_id", unique=True, name="idx_users_user_id")
    await users.create_index("email", unique=True, name="idx_users_email")

    # --- refresh_tokens collection ---
    refresh_tokens = db["refresh_tokens"]
    await refresh_tokens.create_index("token", unique=True, name="idx_refresh_tokens_token")
    await refresh_tokens.create_index("user_id", name="idx_refresh_tokens_user_id")
    await refresh_tokens.create_index(
        "expires_at",
        expireAfterSeconds=0,
        name="idx_refresh_tokens_ttl",
    )

    # --- otp_codes collection ---
    otp_codes = db["otp_codes"]
    await otp_codes.create_index("email", name="idx_otp_codes_email")
    await otp_codes.create_index(
        "expires_at",
        expireAfterSeconds=0,
        name="idx_otp_codes_ttl",
    )

    # --- oauth_states collection ---
    oauth_states = db["oauth_states"]
    await oauth_states.create_index("state", unique=True, name="idx_oauth_states_state")
    await oauth_states.create_index(
        "expires_at",
        expireAfterSeconds=0,
        name="idx_oauth_states_ttl",
    )

    # --- rate_limits collection ---
    rate_limits = db["rate_limits"]
    await rate_limits.create_index(
        [("key", ASCENDING), ("action", ASCENDING), ("timestamp", ASCENDING)],
        name="idx_rate_limits_key_action_timestamp",
    )
    await rate_limits.create_index(
        "expires_at",
        expireAfterSeconds=0,
        name="idx_rate_limits_ttl",
    )
