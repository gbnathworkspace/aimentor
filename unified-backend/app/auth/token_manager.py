"""JWT access token and opaque refresh token lifecycle management."""

from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

import jwt
from fastapi import HTTPException, status

from app.config.database import get_db
from app.config.settings import get_settings

ACCESS_TOKEN_EXPIRE = timedelta(minutes=15)
REFRESH_TOKEN_EXPIRE = timedelta(days=7)
REFRESH_TOKEN_BYTES = 32  # 32 bytes = 43 chars base64url


class TokenManager:
    def __init__(self):
        self.settings = get_settings()

    def create_access_token(self, user_id: str) -> str:
        """Issue a HS256 JWT with sub, iat, exp claims."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "iat": now,
            "exp": now + ACCESS_TOKEN_EXPIRE,
        }
        return jwt.encode(payload, self.settings.JWT_SECRET, algorithm="HS256")

    def verify_access_token(self, token: str) -> str:
        """Verify JWT signature + expiration, return user_id (sub).

        Raises jwt.PyJWTError on failure.
        """
        claims = jwt.decode(
            token,
            self.settings.JWT_SECRET,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub"]},
        )
        return claims["sub"]

    async def create_refresh_token(self, user_id: str) -> str:
        """Generate opaque refresh token, store in MongoDB, return value."""
        token_value = token_urlsafe(REFRESH_TOKEN_BYTES)
        doc = {
            "token": token_value,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + REFRESH_TOKEN_EXPIRE,
            "is_used": False,
        }
        db = get_db()
        await db["refresh_tokens"].insert_one(doc)
        return token_value

    async def rotate_refresh_token(self, old_token: str) -> tuple[str, str, str]:
        """Validate old refresh token, issue new pair.

        Returns (access_token, new_refresh_token, user_id).
        Raises HTTPException on invalid/expired/reused token.
        """
        db = get_db()
        now = datetime.now(timezone.utc)

        # Find the token document
        token_doc = await db["refresh_tokens"].find_one({"token": old_token})

        # Token not found or expired
        if not token_doc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        if token_doc["expires_at"] <= now:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired",
            )

        # Rotation attack detected: token already used
        if token_doc["is_used"]:
            # Revoke ALL tokens for this user (compromised session)
            await self.revoke_all_user_tokens(token_doc["user_id"])
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token reuse detected",
            )

        # Mark old token as used
        await db["refresh_tokens"].update_one(
            {"_id": token_doc["_id"]},
            {"$set": {"is_used": True}},
        )

        # Issue new token pair
        user_id = token_doc["user_id"]
        access_token = self.create_access_token(user_id)
        new_refresh_token = await self.create_refresh_token(user_id)

        return access_token, new_refresh_token, user_id

    async def revoke_refresh_token(self, token_value: str) -> None:
        """Delete a single refresh token document."""
        db = get_db()
        await db["refresh_tokens"].delete_one({"token": token_value})

    async def revoke_all_user_tokens(self, user_id: str) -> None:
        """Delete all refresh tokens for a user (rotation violation or admin action)."""
        db = get_db()
        await db["refresh_tokens"].delete_many({"user_id": user_id})
