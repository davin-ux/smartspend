"""
utils.py
Shared helper functions used across the app: password hashing,
validation, formatting, and small UI helpers.
"""

import re
import hashlib
import secrets
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, date
from config import CURRENCIES, EMAIL_CONFIG, OTP_EXPIRY_MINUTES, OTP_LENGTH, APP_NAME


# ---------------------------------------------------------------
# PASSWORD SECURITY
# ---------------------------------------------------------------
def generate_salt() -> str:
    """Generate a random 16-byte hex salt."""
    return secrets.token_hex(16)


def hash_password(password: str, salt: str) -> str:
    """Hash a password with the given salt using SHA-256 (PBKDF2)."""
    pw_bytes = (password + salt).encode("utf-8")
    hashed = hashlib.pbkdf2_hmac("sha256", pw_bytes, salt.encode("utf-8"), 100_000)
    return hashed.hex()


def verify_password(password: str, salt: str, stored_hash: str) -> bool:
    """Check a plaintext password against a stored hash+salt."""
    return hash_password(password, salt) == stored_hash


# ---------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------
EMAIL_REGEX = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email.strip()))


def is_valid_username(username: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9_]{3,20}$", username.strip()))


def is_strong_password(password: str) -> tuple[bool, str]:
    """Return (is_valid, message) for password strength rules."""
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if not re.search(r"[A-Za-z]", password):
        return False, "Password must contain at least one letter."
    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one number."
    return True, ""


def is_valid_amount(value: str) -> tuple[bool, float]:
    """Return (is_valid, parsed_float)."""
    try:
        amount = float(value)
        return amount > 0, amount
    except (ValueError, TypeError):
        return False, 0.0


def is_valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------
# FORMATTING
# ---------------------------------------------------------------
def format_currency(amount: float, currency_code: str = "INR") -> str:
    symbol = CURRENCIES.get(currency_code, "₹")
    return f"{symbol}{amount:,.2f}"


def format_date_pretty(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' -> 'DD Mon YYYY'."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return d.strftime("%d %b %Y")
    except (ValueError, TypeError):
        return date_str


def today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


def month_bounds(year: int, month: int) -> tuple[str, str]:
    """Return (first_day, last_day) strings for a given year/month."""
    first = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    from datetime import timedelta
    last = next_month - timedelta(days=1)
    return first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")


def truncate(text: str, length: int = 24) -> str:
    text = text or ""
    return text if len(text) <= length else text[: length - 1] + "…"


# ---------------------------------------------------------------
# EMAIL OTP VERIFICATION
# ---------------------------------------------------------------
def generate_otp(length: int = OTP_LENGTH) -> str:
    """Generate a cryptographically random numeric OTP, zero-padded."""
    max_value = (10 ** length) - 1
    number = secrets.randbelow(max_value + 1)
    return str(number).zfill(length)


def send_otp_email(to_email: str, otp_code: str) -> tuple[bool, str]:
    """
    Send a verification code by email via SMTP.
    Returns (success, error_message). error_message is "" on success.
    Requires EMAIL_CONFIG in config.py to be filled in with real
    sender credentials (e.g. a Gmail address + App Password).
    """
    sender = EMAIL_CONFIG.get("sender_email", "").strip()
    password = EMAIL_CONFIG.get("sender_password", "").strip()
    if not sender or not password:
        return False, ("Email sending is not configured yet. Set sender_email and "
                        "sender_password in EMAIL_CONFIG (config.py).")

    subject = f"{APP_NAME} — Your verification code"
    body = (
        f"Your {APP_NAME} verification code is:\n\n"
        f"    {otp_code}\n\n"
        f"This code expires in {OTP_EXPIRY_MINUTES} minutes.\n"
        f"If you didn't request this, you can safely ignore this email."
    )
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email

    try:
        with smtplib.SMTP(EMAIL_CONFIG["smtp_host"], EMAIL_CONFIG["smtp_port"], timeout=15) as server:
            if EMAIL_CONFIG.get("use_tls", True):
                server.starttls()
            server.login(sender, password)
            server.sendmail(sender, [to_email], msg.as_string())
        return True, ""
    except Exception as e:
        return False, f"Couldn't send verification email: {e}"
