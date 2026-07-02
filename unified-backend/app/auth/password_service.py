import bcrypt

WORK_FACTOR = 12


class PasswordService:
    def hash_password(self, password: str) -> str:
        """Hash password with bcrypt, work factor 12. Returns encoded string."""
        salt = bcrypt.gensalt(rounds=WORK_FACTOR)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify plaintext password against stored bcrypt hash."""
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
