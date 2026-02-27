from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer
import os

SECRET_KEY = os.environ.get("SECRET_KEY", "cerberus-dev-secret-key-change-in-prod")
SESSION_SALT = "cerberus-session"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(SECRET_KEY)

# sometimes the bundled bcrypt library doesn't expose version metadata used by
# passlib during backend detection.  when that happens the first call to
# ``pwd_context.hash`` will raise a ValueError about passwords being >72 bytes
# (this is actually triggered by passlib's internal ``bug_hash`` constant).
# we catch that and fall back to directly using the ``bcrypt`` module instead.


# In-memory session store: {token: user_object}
_sessions: dict = {}


def hash_password(plain: str) -> str:
    """Hash a password, falling back to ``bcrypt`` if passlib fails.

    Passlib may raise ``ValueError: password cannot be longer than 72 bytes``
    during its backend autodetection when the underlying ``bcrypt`` module
    is missing version metadata.  This error is unrelated to the actual
    password value, so we catch and handle it here.
    """
    try:
        return pwd_context.hash(plain)
    except ValueError as exc:
        # if the message matches the known passlib bug, fall back
        msg = str(exc)
        if "longer than 72 bytes" in msg:
            import bcrypt

            # bcrypt itself enforces a 72‑byte limit as well, so truncate.
            raw = plain.encode("utf-8") if isinstance(plain, str) else plain
            if len(raw) > 72:
                raw = raw[:72]
            return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")
        # re‑raise unexpected errors
        raise


def verify_password(plain: str, hashed: str) -> bool:
    # try the normal passlib path first; if the backend is busted we fall back
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        try:
            import bcrypt

            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            # if verification completely fails just return False
            return False


def create_session(user) -> str:
    token = serializer.dumps({"user_id": user.id}, salt=SESSION_SALT)
    _sessions[token] = user
    return token


def get_current_user(token: str | None):
    if not token:
        return None
    if token in _sessions:
        return _sessions[token]
    return None


def destroy_session(token: str):
    _sessions.pop(token, None)
