"""Auth router — registration, login, OTP, OAuth, refresh, and logout endpoints."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response, status
from starlette.responses import RedirectResponse

from app.auth.oauth_handler import OAuthHandler
from app.auth.otp_service import OTPService
from app.auth.password_service import PasswordService
from app.auth.rate_limiter import RateLimiter
from app.auth.schemas import (
    LoginRequest,
    MessageResponse,
    OTPRequestBody,
    OTPVerifyBody,
    RegisterRequest,
    TokenResponse,
)
from app.auth.token_manager import TokenManager
from app.config.database import get_db, topics_col
from app.config.settings import get_settings
from app.services.compaction_service import CompactionService
from app.services.session_boundary import close_all_sessions_for_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Auth"])

# Service instances
_token_manager = TokenManager()
_password_service = PasswordService()
_otp_service = OTPService()
_oauth_handler = OAuthHandler()
_compaction_service = CompactionService()
_login_limiter = RateLimiter(max_attempts=5, window_minutes=15)
_otp_request_limiter = RateLimiter(max_attempts=5, window_minutes=15)
_otp_verify_limiter = RateLimiter(max_attempts=5, window_minutes=15)

# Cookie settings for refresh token
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_MAX_AGE = 7 * 24 * 3600  # 7 days in seconds
REFRESH_COOKIE_PATH = "/api/auth"


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Set the refresh token as an HTTP-only cookie on the response."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=True,
        path=REFRESH_COOKIE_PATH,
        max_age=REFRESH_COOKIE_MAX_AGE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie."""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=True,
    )


def _get_frontend_url(request: Request) -> str:
    """Base URL to send the browser back to after OAuth.

    Defaults to the same origin that reached this callback — correct for the
    same-origin deploy where the API serves the SPA. Override with FRONTEND_URL
    when the SPA lives on a different origin (e.g. Vite dev on :5173).
    """
    settings = get_settings()
    base = settings.FRONTEND_URL or str(request.base_url)
    return base.rstrip("/")


# ---------------------------------------------------------------------------
# Registration and Login (Requirements 1.1–1.7, 2.1–2.6)
# ---------------------------------------------------------------------------


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, response: Response):
    """Create a new user with email+password, return tokens."""
    db = get_db()

    # Check for duplicate email
    existing = await db["users"].find_one({"email": body.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    # Hash password and create user document
    hashed_password = _password_service.hash_password(body.password)
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    user_doc = {
        "user_id": user_id,
        "email": body.email,
        "hashed_password": hashed_password,
        "created_at": now,
        "auth_method": "email",
        "is_active": True,
        "is_admin": False,
    }
    await db["users"].insert_one(user_doc)

    # Issue tokens
    access_token = _token_manager.create_access_token(user_id)
    refresh_token = await _token_manager.create_refresh_token(user_id)
    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(access_token=access_token)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response):
    """Authenticate with email+password, return tokens."""
    # Rate limit check
    await _login_limiter.check_and_increment(body.email, "login")

    db = get_db()

    # Find user by email
    user = await db["users"].find_one({"email": body.email})

    # Same error for non-existent email and wrong password (prevent enumeration)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Verify password
    if not _password_service.verify_password(body.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Check if user is active
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deactivated",
        )

    # Reset rate limit on successful login
    await _login_limiter.reset(body.email, "login")

    # Issue tokens
    user_id = user["user_id"]
    access_token = _token_manager.create_access_token(user_id)
    refresh_token = await _token_manager.create_refresh_token(user_id)
    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(access_token=access_token)


# ---------------------------------------------------------------------------
# OTP Endpoints (Requirements 3.1–3.9)
# ---------------------------------------------------------------------------


@router.post("/otp/request", response_model=MessageResponse)
async def request_otp(body: OTPRequestBody):
    """Generate and send a 6-digit OTP to the email."""
    # Rate limit check (5 requests per 15 minutes)
    await _otp_request_limiter.check_and_increment(body.email, "otp_request")

    # Generate and send OTP
    await _otp_service.generate_and_send(body.email)

    return MessageResponse(message="OTP sent to your email")


@router.post("/otp/verify", response_model=TokenResponse)
async def verify_otp(body: OTPVerifyBody, response: Response):
    """Verify OTP code and return tokens."""
    # Rate limit check (5 attempts per 15 minutes)
    await _otp_verify_limiter.check_and_increment(body.email, "otp_verify")

    # Verify OTP code
    is_valid = await _otp_service.verify(body.email, body.code)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired code",
        )

    db = get_db()

    # Find or create user (auto-register on first OTP verification)
    user = await db["users"].find_one({"email": body.email})
    if not user:
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        user_doc = {
            "user_id": user_id,
            "email": body.email,
            "hashed_password": None,
            "created_at": now,
            "auth_method": "otp",
            "is_active": True,
            "is_admin": False,
        }
        await db["users"].insert_one(user_doc)
    else:
        user_id = user["user_id"]

    # Issue tokens
    access_token = _token_manager.create_access_token(user_id)
    refresh_token = await _token_manager.create_refresh_token(user_id)
    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(access_token=access_token)


# ---------------------------------------------------------------------------
# OAuth Endpoints (Requirements 4.1–4.7)
# ---------------------------------------------------------------------------


@router.get("/oauth/callback")
async def oauth_callback(code: str, state: str, request: Request):
    """Handle OAuth provider callback, issue tokens via redirect."""
    frontend_url = _get_frontend_url(request)

    try:
        # Validate state, exchange code, fetch user profile
        user_info = await _oauth_handler.handle_callback(code, state)

        # Check for missing email
        if not user_info.get("email"):
            error_msg = "Email address is required from OAuth provider"
            return RedirectResponse(
                url=f"{frontend_url}/login?error={quote(error_msg)}",
                status_code=status.HTTP_302_FOUND,
            )

        db = get_db()

        # Find or create user
        email = user_info["email"]
        user = await db["users"].find_one({"email": email})

        if not user:
            # Create new user from OAuth
            user_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            user_doc = {
                "user_id": user_id,
                "email": email,
                "hashed_password": None,
                "created_at": now,
                "auth_method": user_info["provider"],
                "is_active": True,
                "is_admin": False,
                "oauth_identities": [
                    {
                        "provider": user_info["provider"],
                        "provider_user_id": user_info["provider_user_id"],
                        "name": user_info.get("name"),
                    }
                ],
            }
            await db["users"].insert_one(user_doc)
        else:
            user_id = user["user_id"]

            # Link OAuth identity if not already linked
            existing_identities = user.get("oauth_identities", [])
            already_linked = any(
                ident["provider"] == user_info["provider"]
                and ident["provider_user_id"] == user_info["provider_user_id"]
                for ident in existing_identities
            )
            if not already_linked:
                await db["users"].update_one(
                    {"user_id": user_id},
                    {
                        "$push": {
                            "oauth_identities": {
                                "provider": user_info["provider"],
                                "provider_user_id": user_info["provider_user_id"],
                                "name": user_info.get("name"),
                            }
                        }
                    },
                )

        # Issue tokens
        access_token = _token_manager.create_access_token(user_id)
        refresh_token = await _token_manager.create_refresh_token(user_id)

        # Redirect to frontend with token, set refresh cookie on redirect response
        redirect_url = f"{frontend_url}/auth/callback?token={access_token}"
        redirect_response = RedirectResponse(
            url=redirect_url, status_code=status.HTTP_302_FOUND
        )
        _set_refresh_cookie(redirect_response, refresh_token)

        return redirect_response

    except (ValueError, Exception) as e:
        # On any failure, redirect to login with error
        error_msg = str(e) if str(e) else "OAuth authentication failed"
        return RedirectResponse(
            url=f"{frontend_url}/login?error={quote(error_msg)}",
            status_code=status.HTTP_302_FOUND,
        )


@router.get("/oauth/{provider}")
async def oauth_initiate(provider: str):
    """Redirect to OAuth provider authorization URL.

    Declared after /oauth/callback so the static callback route matches first —
    otherwise {provider} captures "callback" and OAuth returns from the provider
    into the wrong handler.
    """
    try:
        authorization_url = await _oauth_handler.get_authorization_url(provider)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return RedirectResponse(url=authorization_url, status_code=status.HTTP_302_FOUND)


# ---------------------------------------------------------------------------
# Refresh and Logout (Requirements 5.7–5.10)
# ---------------------------------------------------------------------------


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: Request, response: Response):
    """Exchange valid refresh token for new token pair."""
    # Extract refresh token from HTTP-only cookie
    old_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not old_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )

    # Rotate token pair (raises HTTPException on invalid/expired/reused)
    access_token, new_refresh_token, _user_id = await _token_manager.rotate_refresh_token(
        old_token
    )

    # Set new refresh cookie
    _set_refresh_cookie(response, new_refresh_token)

    return TokenResponse(access_token=access_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response):
    """Invalidate refresh token, clear cookie, and close out any open topic sessions."""
    # Extract refresh token from cookie
    token_value = request.cookies.get(REFRESH_COOKIE_NAME)

    if token_value:
        user_id = await _user_id_from_refresh_cookie(token_value)
        # Revoke the refresh token in the database
        await _token_manager.revoke_refresh_token(token_value)
        if user_id:
            asyncio.create_task(close_all_sessions_for_user(user_id))

    # Clear the cookie regardless
    _clear_refresh_cookie(response)

    return MessageResponse(message="Logged out successfully")


@router.post("/checkpoint", response_model=MessageResponse)
async def checkpoint(request: Request):
    """Fire-and-forget skill checkpoint for an unexpected tab/browser close.

    Called via navigator.sendBeacon on pagehide — unlike /logout, this does NOT
    revoke the session, it only catches skill-graph progress the periodic
    in-session checkpoint hasn't reached yet. sendBeacon can't carry a bearer
    token, so — like /logout — this identifies the user via the refresh-token
    cookie, which sendBeacon sends automatically for a same-origin request.
    """
    token_value = request.cookies.get(REFRESH_COOKIE_NAME)
    if token_value:
        user_id = await _user_id_from_refresh_cookie(token_value)
        if user_id:
            asyncio.create_task(_skill_checkpoint_for_user(user_id))
    return MessageResponse(message="ok")


async def _user_id_from_refresh_cookie(token_value: str) -> str | None:
    token_doc = await get_db()["refresh_tokens"].find_one(
        {"token": token_value}, {"user_id": 1}
    )
    return token_doc.get("user_id") if token_doc else None


async def _skill_checkpoint_for_user(user_id: str) -> None:
    """Fire-and-forget: catch any active topics' progress the periodic
    per-message checkpoint hasn't reached yet before the session ends."""
    try:
        topics = await topics_col().find(
            {"userId": user_id, "status": "active"}, {"topicId": 1, "_id": 0}
        ).to_list(length=None)
        for t in topics:
            await _compaction_service.extract_skill_updates_only(t["topicId"], user_id)
    except Exception as e:
        logger.error("Skill checkpoint failed for user %s: %s", user_id, str(e))
