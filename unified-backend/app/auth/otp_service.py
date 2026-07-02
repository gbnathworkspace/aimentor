"""OTP generation, storage, and verification service.

Generates cryptographically random 6-digit codes, stores them in MongoDB
with a 10-minute TTL expiry, and verifies codes on a single-use basis.
"""

from datetime import datetime, timedelta, timezone
from secrets import randbelow

from app.config.database import get_db
from app.auth.email_sender import send_otp_email

OTP_EXPIRY = timedelta(minutes=10)
OTP_LENGTH = 6


class OTPService:
    async def generate_and_send(self, email: str) -> None:
        """Generate 6-digit code, store with expiry, email to user.

        Invalidates any existing unexpired code for this email.
        """
        db = get_db()
        # Invalidate previous codes
        await db["otp_codes"].delete_many({"email": email})
        # Generate cryptographically random 6-digit code
        code = str(randbelow(10**OTP_LENGTH)).zfill(OTP_LENGTH)
        doc = {
            "email": email,
            "code": code,
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + OTP_EXPIRY,
        }
        await db["otp_codes"].insert_one(doc)
        await send_otp_email(email, code)

    async def verify(self, email: str, code: str) -> bool:
        """Verify code matches stored OTP and is not expired.

        Deletes the code on successful verification (single-use).
        """
        db = get_db()
        now = datetime.now(timezone.utc)
        doc = await db["otp_codes"].find_one_and_delete({
            "email": email,
            "code": code,
            "expires_at": {"$gt": now},
        })
        return doc is not None
