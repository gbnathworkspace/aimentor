"""OAuth authorization code flow handler for Google and GitHub."""

from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from urllib.parse import urlencode

import httpx

from app.config.database import get_db
from app.config.settings import get_settings

OAUTH_STATE_EXPIRY = timedelta(minutes=5)

PROVIDER_CONFIG = {
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
        "scopes": ["openid", "email", "profile"],
    },
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "emails_url": "https://api.github.com/user/emails",
        "scopes": ["user:email"],
    },
}


class OAuthHandler:
    """Handles OAuth 2.0 authorization code flow for Google and GitHub."""

    def __init__(self):
        self.settings = get_settings()

    async def get_authorization_url(self, provider: str) -> str:
        """Generate OAuth authorize URL with random state parameter.

        Creates a cryptographically random state token, stores it in MongoDB
        with a 5-minute TTL for CSRF protection, and builds the provider's
        authorization URL with appropriate scopes.
        """
        if provider not in PROVIDER_CONFIG:
            raise ValueError(f"Unsupported OAuth provider: {provider}")

        config = PROVIDER_CONFIG[provider]
        state = token_urlsafe(32)

        # Store state for CSRF verification
        db = get_db()
        await db["oauth_states"].insert_one({
            "state": state,
            "provider": provider,
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + OAUTH_STATE_EXPIRY,
        })

        params = {
            "client_id": self._get_client_id(provider),
            "redirect_uri": self.settings.OAUTH_REDIRECT_URI,
            "scope": " ".join(config["scopes"]),
            "state": state,
            "response_type": "code",
        }

        return f"{config['authorize_url']}?{urlencode(params)}"

    async def handle_callback(self, code: str, state: str) -> dict:
        """Validate state, exchange code for tokens, fetch user profile.

        Returns dict with keys: email, name, provider, provider_user_id.
        Raises ValueError if state is invalid or expired.
        """
        db = get_db()

        # Verify state (find and delete atomically to prevent reuse)
        state_doc = await db["oauth_states"].find_one_and_delete({
            "state": state,
            "expires_at": {"$gt": datetime.now(timezone.utc)},
        })
        if not state_doc:
            raise ValueError("Invalid or expired OAuth state")

        provider = state_doc["provider"]

        # Exchange code for access token
        token_data = await self._exchange_code(provider, code)

        # Fetch user profile
        user_info = await self._fetch_user_info(provider, token_data["access_token"])
        return user_info

    async def _exchange_code(self, provider: str, code: str) -> dict:
        """Exchange authorization code for provider access token."""
        config = PROVIDER_CONFIG[provider]
        data = {
            "client_id": self._get_client_id(provider),
            "client_secret": self._get_client_secret(provider),
            "code": code,
            "redirect_uri": self.settings.OAUTH_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        headers = {"Accept": "application/json"}

        async with httpx.AsyncClient() as client:
            resp = await client.post(config["token_url"], data=data, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def _fetch_user_info(self, provider: str, access_token: str) -> dict:
        """Fetch email and display name from provider API.

        For Google: uses the userinfo endpoint directly.
        For GitHub: fetches user profile and may need a separate emails API call
        if the primary email isn't public.
        """
        config = PROVIDER_CONFIG[provider]
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient() as client:
            resp = await client.get(config["userinfo_url"], headers=headers)
            resp.raise_for_status()
            data = resp.json()

            if provider == "google":
                return {
                    "email": data.get("email"),
                    "name": data.get("name"),
                    "provider": "google",
                    "provider_user_id": data.get("sub"),
                }
            elif provider == "github":
                email = data.get("email")
                if not email:
                    # GitHub may not return email in user profile — fetch from emails API
                    emails_resp = await client.get(
                        config["emails_url"], headers=headers
                    )
                    emails_resp.raise_for_status()
                    emails = emails_resp.json()
                    primary = next(
                        (e for e in emails if e.get("primary")), None
                    )
                    email = primary["email"] if primary else None
                return {
                    "email": email,
                    "name": data.get("name") or data.get("login"),
                    "provider": "github",
                    "provider_user_id": str(data.get("id")),
                }

        raise ValueError(f"Unsupported provider: {provider}")

    def _get_client_id(self, provider: str) -> str:
        """Return the OAuth client ID for the given provider."""
        if provider == "google":
            return self.settings.GOOGLE_CLIENT_ID
        return self.settings.GITHUB_CLIENT_ID

    def _get_client_secret(self, provider: str) -> str:
        """Return the OAuth client secret for the given provider."""
        if provider == "google":
            return self.settings.GOOGLE_CLIENT_SECRET
        return self.settings.GITHUB_CLIENT_SECRET
