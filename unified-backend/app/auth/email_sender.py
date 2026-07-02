"""Email delivery abstraction for OTP codes.

Supports two backends:
- "console": Logs OTP to stdout (development)
- "api": Sends via transactional email API (production)
"""

import httpx

from app.config.settings import get_settings


async def send_otp_email(to_email: str, code: str) -> None:
    """Send OTP code via configured email provider.

    Uses transactional email API (e.g., Resend, SendGrid) in production.
    In development, logs to console instead of sending.
    """
    settings = get_settings()

    if settings.EMAIL_BACKEND == "console":
        print(f"[OTP] {to_email}: {code}")
        return

    # Production: send via configured provider
    async with httpx.AsyncClient() as client:
        await client.post(
            settings.EMAIL_API_URL,
            headers={"Authorization": f"Bearer {settings.EMAIL_API_KEY}"},
            json={
                "from": settings.EMAIL_FROM,
                "to": to_email,
                "subject": "Your MentorMan login code",
                "text": f"Your verification code is: {code}\n\nThis code expires in 10 minutes.",
            },
        )
