"""
config.py
Central configuration for the SmartSpend Pro Flask web app.
"""

import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(BASE_DIR, "sql", "smartspend.sql")
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
os.makedirs(EXPORTS_DIR, exist_ok=True)

APP_NAME = "SmartSpend Pro"

# Flask needs a secret key to sign session cookies. A random one is
# generated on every restart by default — set SMARTSPEND_SECRET_KEY
# as an environment variable in production so sessions survive restarts.
SECRET_KEY = os.environ.get("SMARTSPEND_SECRET_KEY", secrets.token_hex(32))

# ---------------------------------------------------------------
# MYSQL CONNECTION
# ---------------------------------------------------------------
# Update these to match your local MySQL server. The database itself
# (smartspend_pro) is created automatically on first run.
MYSQL_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "dbxcbe",          # <-- put your MySQL root/user password here
    "database": "smartspend_pro",
}

# ---------------------------------------------------------------
# EMAIL (for OTP signup verification)
# ---------------------------------------------------------------
# Gmail example: enable 2-Step Verification on the sender account, then
# create an "App Password" at https://myaccount.google.com/apppasswords
# and use that here — NOT your normal Gmail password.
EMAIL_CONFIG = {
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "use_tls": True,
    "sender_email": "",       # <-- your sending email address
    "sender_password": "",    # <-- your SMTP / app password
}
OTP_EXPIRY_MINUTES = 10
OTP_LENGTH = 6

DEFAULT_INCOME_CATEGORIES = [
    ("Salary", "💼"), ("Freelance", "🧑‍💻"), ("Business", "🏪"),
    ("Investment", "📈"), ("Gift", "🎁"), ("Other", "➕"),
]

DEFAULT_EXPENSE_CATEGORIES = [
    ("Food & Dining", "🍔"), ("Transport", "🚌"), ("Shopping", "🛍️"),
    ("Bills & Utilities", "💡"), ("Entertainment", "🎬"), ("Health", "🏥"),
    ("Education", "📚"), ("Rent", "🏠"), ("Other", "➕"),
]

PAYMENT_MODES = ["Cash", "Debit Card", "Credit Card", "UPI", "Net Banking", "Wallet"]

CURRENCIES = {
    "INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥",
}
