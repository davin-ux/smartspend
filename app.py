"""
app.py
SmartSpend Pro — Flask web app.
Same MySQL backend and business logic as the desktop version; this
file replaces the CustomTkinter UI with server-rendered HTML pages
that work in any browser, including phones and tablets.

Run with:  python app.py
Then open: http://localhost:5000  (or http://<your-computer-ip>:5000 from a phone on the same Wi-Fi)
"""

import csv
import io
import os
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_file, g,
)

from config import APP_NAME, SECRET_KEY, CURRENCIES, PAYMENT_MODES, EXPORTS_DIR, OTP_EXPIRY_MINUTES
from database import Database
from utils import (
    generate_salt, hash_password, verify_password,
    is_valid_email, is_valid_username, is_strong_password,
    is_valid_amount, is_valid_date, format_currency, format_date_pretty,
    today_str, month_bounds, generate_otp, send_otp_email,
)

app = Flask(__name__)
app.secret_key = SECRET_KEY

db = None
db_error = None
try:
    db = Database()
except Exception as e:
    db_error = str(e)


@app.before_request
def check_db_connection():
    """Ensure the database is available before handling a request."""
    global db, db_error
    if request.endpoint == "static":
        return None

    if db is None:
        try:
            db = Database()
            db_error = None
        except Exception as e:
            db_error = str(e)
            return render_template("db_error.html", error=db_error), 500

    return None


@app.route("/health")
def health():
    return {"status": "ok", "app": APP_NAME}, 200


@app.route("/api/health")
def api_health():
    return {"status": "ok", "app": APP_NAME}, 200


@app.errorhandler(404)
def page_not_found(error):
    return render_template("login.html"), 404

# ==================================================================
# AUTH HELPERS
# ==================================================================
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def _start_otp_flow(user, context="register"):
    """Generate a fresh code, email it, and stage the user as 'pending verification'."""
    code = generate_otp()
    expires_at = datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    db.create_otp(user["user_id"], code, expires_at)
    session["otp_context"] = context

    sent, error = send_otp_email(user["email"], code)
    session["pending_user_id"] = user["user_id"]

    if sent:
        flash(f"We've sent a 6-digit code to {user['email']}.", "success")
    else:
        # Fall back to showing the code directly so the flow is still testable
        # without real SMTP credentials configured in config.py.
        flash(f"Couldn't send the verification email ({error}). "
              f"For testing, your code is: {code}", "warning")


@app.before_request
def load_current_user():
    g.user = None
    if "user_id" in session:
        g.user = db.get_user_by_id(session["user_id"])
        if g.user is None:
            session.clear()


@app.context_processor
def inject_globals():
    return {"APP_NAME": APP_NAME, "current_user": g.get("user")}


# ==================================================================
# AUTH ROUTES
# ==================================================================
@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Please fill in both fields.", "error")
            return render_template("login.html")

        user = db.get_user_by_username(username)
        if not user or not verify_password(password, user["salt"], user["password_hash"]):
            flash("Invalid username or password.", "error")
            return render_template("login.html")

        if not db.is_user_verified(user["user_id"]):
            _start_otp_flow(user, context="login")
            return redirect(url_for("verify_otp"))

        session["user_id"] = user["user_id"]
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        error = None
        if not all([name, username, email, password, confirm]):
            error = "All fields are required."
        elif not is_valid_username(username):
            error = "Username must be 3-20 letters, numbers, or underscores."
        elif not is_valid_email(email):
            error = "Please enter a valid email address."
        else:
            ok, msg = is_strong_password(password)
            if not ok:
                error = msg
            elif password != confirm:
                error = "Passwords do not match."
            elif db.get_user_by_username(username):
                error = "Username already taken."
            elif db.get_user_by_email(email):
                error = "Email already registered."

        if error:
            flash(error, "error")
            return render_template("register.html")

        salt = generate_salt()
        pw_hash = hash_password(password, salt)
        user_id = db.create_user(name, username, email, pw_hash, salt)
        user = db.get_user_by_id(user_id)
        _start_otp_flow(user)
        return redirect(url_for("verify_otp"))

    return render_template("register.html")


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    pending_id = session.get("pending_user_id")
    if not pending_id:
        return redirect(url_for("login"))

    user = db.get_user_by_id(pending_id)
    if not user:
        session.pop("pending_user_id", None)
        return redirect(url_for("login"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        if not code:
            flash("Enter the code sent to your email.", "error")
            return render_template("verify_otp.html", email=user["email"])

        success, error = db.verify_and_consume_otp(pending_id, code)
        if not success:
            flash(error, "error")
            return render_template("verify_otp.html", email=user["email"])

        session.pop("pending_user_id", None)
        was_registering = session.pop("otp_context", "register") == "register"
        session["user_id"] = pending_id

        if was_registering:
            return redirect(url_for("account_created"))

        flash("Email verified! Welcome back.", "success")
        return redirect(url_for("dashboard"))

    return render_template("verify_otp.html", email=user["email"])


@app.route("/account-created")
@login_required
def account_created():
    return render_template("account_created.html")


@app.route("/verify-otp/resend", methods=["POST"])
def verify_otp_resend():
    pending_id = session.get("pending_user_id")
    if not pending_id:
        return redirect(url_for("login"))
    user = db.get_user_by_id(pending_id)
    if user:
        _start_otp_flow(user, context=session.get("otp_context", "register"))
    return redirect(url_for("verify_otp"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ==================================================================
# DASHBOARD
# ==================================================================
@app.route("/dashboard")
@login_required
def dashboard():
    user = g.user
    today = date.today()
    start, end = month_bounds(today.year, today.month)

    income_total = db.total_income(user["user_id"], start, end)
    expense_total = db.total_expense(user["user_id"], start, end)
    balance = income_total - expense_total
    budget = user["monthly_budget"] or 0
    budget_left = max(budget - expense_total, 0)
    pct = min(expense_total / budget, 1.0) * 100 if budget > 0 else 0

    recent = db.recent_transactions(user["user_id"], limit=8)

    return render_template(
        "dashboard.html",
        income_total=income_total, expense_total=expense_total, balance=balance,
        budget=budget, budget_left=budget_left, pct=pct, recent=recent,
        currency=user["currency"], fmt=format_currency, pretty_date=format_date_pretty,
    )


# ==================================================================
# INCOME
# ==================================================================
@app.route("/income")
@login_required
def income_page():
    user = g.user
    categories = db.get_categories(user["user_id"], "income")
    records = db.get_income(user["user_id"])
    return render_template(
        "income.html", categories=categories, records=records,
        currency=user["currency"], fmt=format_currency, pretty_date=format_date_pretty,
        today=today_str(), edit_record=None,
    )


@app.route("/income/edit/<int:income_id>")
@login_required
def income_edit(income_id):
    user = g.user
    categories = db.get_categories(user["user_id"], "income")
    records = db.get_income(user["user_id"])
    edit_record = next((r for r in records if r["income_id"] == income_id), None)
    return render_template(
        "income.html", categories=categories, records=records,
        currency=user["currency"], fmt=format_currency, pretty_date=format_date_pretty,
        today=today_str(), edit_record=edit_record,
    )


@app.route("/income/save", methods=["POST"])
@login_required
def income_save():
    user = g.user
    income_id = request.form.get("income_id", "").strip()
    category_id = request.form.get("category_id") or None
    valid_amt, amount = is_valid_amount(request.form.get("amount", ""))
    source = request.form.get("source", "").strip()
    date_val = request.form.get("date", "").strip()
    note = request.form.get("note", "").strip()

    if not valid_amt:
        flash("Enter a valid positive amount.", "error")
    elif not source:
        flash("Source is required.", "error")
    elif not is_valid_date(date_val):
        flash("Date must be in YYYY-MM-DD format.", "error")
    elif not db.category_belongs_to_user(category_id, user["user_id"], "income"):
        flash("Invalid income category.", "error")
    else:
        if income_id:
            db.update_income(int(income_id), category_id, amount, source, date_val, note)
            flash("Income updated.", "success")
        else:
            db.add_income(user["user_id"], category_id, amount, source, date_val, note)
            flash("Income added.", "success")

    return redirect(url_for("income_page"))


@app.route("/income/delete/<int:income_id>", methods=["POST"])
@login_required
def income_delete(income_id):
    db.delete_income(income_id)
    flash("Income record deleted.", "success")
    return redirect(url_for("income_page"))


# ==================================================================
# EXPENSE
# ==================================================================
@app.route("/expense")
@login_required
def expense_page():
    user = g.user
    categories = db.get_categories(user["user_id"], "expense")
    records = db.get_expense(user["user_id"])
    return render_template(
        "expense.html", categories=categories, records=records,
        currency=user["currency"], fmt=format_currency, pretty_date=format_date_pretty,
        today=today_str(), payment_modes=PAYMENT_MODES, edit_record=None,
    )


@app.route("/expense/edit/<int:expense_id>")
@login_required
def expense_edit(expense_id):
    user = g.user
    categories = db.get_categories(user["user_id"], "expense")
    records = db.get_expense(user["user_id"])
    edit_record = next((r for r in records if r["expense_id"] == expense_id), None)
    return render_template(
        "expense.html", categories=categories, records=records,
        currency=user["currency"], fmt=format_currency, pretty_date=format_date_pretty,
        today=today_str(), payment_modes=PAYMENT_MODES, edit_record=edit_record,
    )


@app.route("/expense/save", methods=["POST"])
@login_required
def expense_save():
    user = g.user
    expense_id = request.form.get("expense_id", "").strip()
    category_id = request.form.get("category_id") or None
    valid_amt, amount = is_valid_amount(request.form.get("amount", ""))
    payee = request.form.get("payee", "").strip()
    date_val = request.form.get("date", "").strip()
    mode = request.form.get("payment_mode", "Cash")
    note = request.form.get("note", "").strip()

    if not valid_amt:
        flash("Enter a valid positive amount.", "error")
    elif not payee:
        flash("Payee is required.", "error")
    elif not is_valid_date(date_val):
        flash("Date must be in YYYY-MM-DD format.", "error")
    elif mode not in PAYMENT_MODES:
        flash("Invalid payment mode.", "error")
    elif not db.category_belongs_to_user(category_id, user["user_id"], "expense"):
        flash("Invalid expense category.", "error")
    else:
        if expense_id:
            db.update_expense(int(expense_id), category_id, amount, payee, date_val, mode, note)
            flash("Expense updated.", "success")
        else:
            db.add_expense(user["user_id"], category_id, amount, payee, date_val, mode, note)
            flash("Expense added.", "success")

    return redirect(url_for("expense_page"))


@app.route("/expense/delete/<int:expense_id>", methods=["POST"])
@login_required
def expense_delete(expense_id):
    db.delete_expense(expense_id)
    flash("Expense record deleted.", "success")
    return redirect(url_for("expense_page"))


# ==================================================================
# REPORTS
# ==================================================================
def _report_results(user_id, ttype, start, end):
    results = []
    if ttype in ("All", "Income"):
        for r in db.get_income(user_id, start, end):
            results.append({"type": "Income", "amount": r["amount"], "label": r["source"],
                             "category": r["category_name"], "date": r["date"]})
    if ttype in ("All", "Expense"):
        for r in db.get_expense(user_id, start, end):
            results.append({"type": "Expense", "amount": r["amount"], "label": r["payee"],
                             "category": r["category_name"], "date": r["date"]})
    results.sort(key=lambda r: str(r["date"]), reverse=True)
    return results


@app.route("/reports")
@login_required
def reports_page():
    user = g.user
    today = date.today()
    default_start, default_end = month_bounds(today.year, today.month)
    ttype = request.args.get("type", "All")
    start = request.args.get("start", default_start)
    end = request.args.get("end", default_end)

    if not (is_valid_date(start) and is_valid_date(end)):
        start, end = default_start, default_end

    results = _report_results(user["user_id"], ttype, start, end)
    total_in = sum(r["amount"] for r in results if r["type"] == "Income")
    total_out = sum(r["amount"] for r in results if r["type"] == "Expense")

    return render_template(
        "reports.html", results=results, total_in=total_in, total_out=total_out,
        net=total_in - total_out, currency=user["currency"], fmt=format_currency,
        pretty_date=format_date_pretty, ttype=ttype, start=start, end=end,
    )


@app.route("/reports/export")
@login_required
def reports_export():
    user = g.user
    ttype = request.args.get("type", "All")
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    results = _report_results(user["user_id"], ttype, start, end)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Type", "Amount", "Label", "Category", "Date"])
    for r in results:
        writer.writerow([r["type"], r["amount"], r["label"], r["category"] or "Uncategorized", r["date"]])

    mem = io.BytesIO(buffer.getvalue().encode("utf-8"))
    filename = f"smartspend_report_{user['username']}.csv"
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name=filename)


# ==================================================================
# ANALYTICS
# ==================================================================
@app.route("/analytics")
@login_required
def analytics_page():
    user = g.user
    by_cat = db.expense_by_category(user["user_id"])
    income_trend = db.monthly_income_trend(user["user_id"])
    expense_trend = db.monthly_trend(user["user_id"])

    months = sorted({r["ym"] for r in income_trend} | {r["ym"] for r in expense_trend})
    income_map = {r["ym"]: float(r["total"]) for r in income_trend}
    expense_map = {r["ym"]: float(r["total"]) for r in expense_trend}

    chart_data = {
        "pie_labels": [f"{r['icon']} {r['category_name']}" for r in by_cat],
        "pie_values": [float(r["total"]) for r in by_cat],
        "trend_labels": months,
        "trend_income": [income_map.get(m, 0) for m in months],
        "trend_expense": [expense_map.get(m, 0) for m in months],
    }
    return render_template("analytics.html", chart_data=chart_data)


# ==================================================================
# PROFILE
# ==================================================================
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile_page():
    user = g.user

    if request.method == "POST" and request.form.get("form_name") == "info":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        if not name or not email:
            flash("Name and email cannot be empty.", "error")
        elif not is_valid_email(email):
            flash("Enter a valid email address.", "error")
        else:
            existing = db.get_user_by_email(email)
            if existing and existing["user_id"] != user["user_id"]:
                flash("That email is already used by another account.", "error")
            else:
                db.update_user_profile(user["user_id"], name, email, user["currency"], user["monthly_budget"])
                flash("Profile updated.", "success")
                return redirect(url_for("profile_page"))
        return redirect(url_for("profile_page"))

    if request.method == "POST" and request.form.get("form_name") == "password":
        old_pw = request.form.get("old_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if not all([old_pw, new_pw, confirm_pw]):
            flash("All password fields are required.", "error")
        elif not verify_password(old_pw, user["salt"], user["password_hash"]):
            flash("Current password is incorrect.", "error")
        else:
            ok, msg = is_strong_password(new_pw)
            if not ok:
                flash(msg, "error")
            elif new_pw != confirm_pw:
                flash("New passwords do not match.", "error")
            else:
                salt = generate_salt()
                pw_hash = hash_password(new_pw, salt)
                db.update_user_password(user["user_id"], pw_hash, salt)
                flash("Password updated.", "success")
        return redirect(url_for("profile_page"))

    return render_template("profile.html")


# ==================================================================
# SETTINGS
# ==================================================================
@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
    user = g.user

    if request.method == "POST":
        form_name = request.form.get("form_name")

        if form_name == "currency":
            currency = request.form.get("currency", user["currency"])
            if currency not in CURRENCIES:
                flash("Invalid currency.", "error")
                return redirect(url_for("settings_page"))
            db.update_user_profile(user["user_id"], user["full_name"], user["email"],
                                    currency, user["monthly_budget"])
            flash(f"Currency changed to {currency} ({CURRENCIES.get(currency, '')}).", "success")

        elif form_name == "budget":
            raw = request.form.get("budget", "").strip()
            if raw == "":
                budget = 0.0
                valid = True
            else:
                valid, budget = is_valid_amount(raw)
            if not valid:
                flash("Enter a valid positive number.", "error")
            else:
                db.update_user_profile(user["user_id"], user["full_name"], user["email"],
                                        user["currency"], budget)
                flash("Monthly budget updated.", "success")

        return redirect(url_for("settings_page"))

    return render_template("settings.html", currencies=CURRENCIES)


if __name__ == "__main__":
    # host="0.0.0.0" makes the server reachable from other devices on the
    # same Wi-Fi (e.g. your phone) via http://<your-computer-ip>:5000
    app.run(host="0.0.0.0", port=5000, debug=False)
