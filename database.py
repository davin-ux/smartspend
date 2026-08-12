"""
database.py
Handles all MySQL interaction for SmartSpend-Pro: connection setup,
schema initialization, and CRUD operations for users, categories,
income, and expense records.
"""

import mysql.connector
from mysql.connector import Error as MySQLError
from config import MYSQL_CONFIG, SCHEMA_PATH, DEFAULT_INCOME_CATEGORIES, DEFAULT_EXPENSE_CATEGORIES

DUPLICATE_KEY_ERRNO = 1061     # "Duplicate key name" — safe to ignore on repeat launches
DUPLICATE_COLUMN_ERRNO = 1060  # "Duplicate column name" — safe to ignore on repeat launches


class Database:
    """Thin wrapper around mysql-connector-python for the whole application."""

    def __init__(self, config: dict = None):
        self.config = config or MYSQL_CONFIG
        self._ensure_database_exists()
        self.conn = mysql.connector.connect(**self.config)
        self._init_schema()
        self._run_migrations()

    # ------------------------------------------------------------
    def _ensure_database_exists(self):
        """Connect without selecting a database and create it if missing."""
        server_config = {k: v for k, v in self.config.items() if k != "database"}
        temp_conn = mysql.connector.connect(**server_config)
        cur = temp_conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {self.config['database']}")
        temp_conn.commit()
        cur.close()
        temp_conn.close()

    def _init_schema(self):
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            script = f.read()

        statements = []
        for raw_stmt in script.split(";"):
            lines = [l for l in raw_stmt.splitlines() if not l.strip().startswith("--")]
            stmt = "\n".join(lines).strip()
            if stmt:
                statements.append(stmt)

        cur = self.conn.cursor()
        for stmt in statements:
            try:
                cur.execute(stmt)
            except MySQLError as e:
                if e.errno == DUPLICATE_KEY_ERRNO:
                    continue
                raise
        self.conn.commit()
        cur.close()

    def _run_migrations(self):
        """
        Adds columns/tables introduced after someone may have already run
        the app once (so their `users` table predates `is_verified`).
        Safe to run on every startup — duplicate-column errors are ignored.
        """
        cur = self.conn.cursor()
        try:
            cur.execute("ALTER TABLE users ADD COLUMN is_verified TINYINT(1) NOT NULL DEFAULT 0")
            self.conn.commit()
        except MySQLError as e:
            if e.errno != DUPLICATE_COLUMN_ERRNO:
                raise
        cur.close()

    def close(self):
        try:
            if self.conn and self.conn.is_connected():
                self.conn.close()
        except Exception:
            pass

    def _ensure_connection(self):
        """Reconnect automatically if MySQL dropped the connection."""
        try:
            if not self.conn.is_connected():
                self.conn.reconnect(attempts=3, delay=1)
        except Exception:
            self.conn = mysql.connector.connect(**self.config)

    # ------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------
    def _fetchone(self, sql, params=None):
        self._ensure_connection()
        cur = self.conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        row = cur.fetchone()
        cur.close()
        return row

    def _fetchall(self, sql, params=None):
        self._ensure_connection()
        cur = self.conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        cur.close()
        return rows

    def _execute(self, sql, params=None):
        """Run an INSERT/UPDATE/DELETE, commit, and return lastrowid."""
        self._ensure_connection()
        cur = self.conn.cursor()
        cur.execute(sql, params or ())
        self.conn.commit()
        last_id = cur.lastrowid
        cur.close()
        return last_id

    # ==============================================================
    # USERS
    # ==============================================================
    def create_user(self, full_name, username, email, password_hash, salt):
        user_id = self._execute(
            """INSERT INTO users (full_name, username, email, password_hash, salt)
               VALUES (%s, %s, %s, %s, %s)""",
            (full_name, username, email, password_hash, salt),
        )
        self._seed_default_categories(user_id)
        return user_id

    def _seed_default_categories(self, user_id):
        for name, icon in DEFAULT_INCOME_CATEGORIES:
            self.add_category(user_id, name, "income", icon)
        for name, icon in DEFAULT_EXPENSE_CATEGORIES:
            self.add_category(user_id, name, "expense", icon)

    def get_user_by_username(self, username):
        return self._fetchone("SELECT * FROM users WHERE username = %s", (username,))

    def get_user_by_email(self, email):
        return self._fetchone("SELECT * FROM users WHERE email = %s", (email,))

    def get_user_by_id(self, user_id):
        return self._fetchone("SELECT * FROM users WHERE user_id = %s", (user_id,))

    def update_user_profile(self, user_id, full_name, email, currency, monthly_budget):
        self._execute(
            """UPDATE users SET full_name=%s, email=%s, currency=%s, monthly_budget=%s
               WHERE user_id=%s""",
            (full_name, email, currency, monthly_budget, user_id),
        )

    def update_user_password(self, user_id, password_hash, salt):
        self._execute(
            "UPDATE users SET password_hash=%s, salt=%s WHERE user_id=%s",
            (password_hash, salt, user_id),
        )

    def update_user_theme(self, user_id, theme):
        self._execute("UPDATE users SET theme=%s WHERE user_id=%s", (theme, user_id))

    # ==============================================================
    # EMAIL VERIFICATION (OTP)
    # ==============================================================
    def is_user_verified(self, user_id) -> bool:
        row = self._fetchone("SELECT is_verified FROM users WHERE user_id=%s", (user_id,))
        return bool(row["is_verified"]) if row else False

    def mark_user_verified(self, user_id):
        self._execute("UPDATE users SET is_verified=1 WHERE user_id=%s", (user_id,))

    def create_otp(self, user_id, code, expires_at):
        """Store a fresh OTP for this user, replacing any previous one."""
        self._execute("DELETE FROM email_otp WHERE user_id=%s", (user_id,))
        return self._execute(
            "INSERT INTO email_otp (user_id, code, expires_at) VALUES (%s, %s, %s)",
            (user_id, code, expires_at),
        )

    def delete_otp(self, user_id):
        self._execute("DELETE FROM email_otp WHERE user_id=%s", (user_id,))

    def verify_and_consume_otp(self, user_id, code) -> tuple[bool, str]:
        """
        Check a submitted code against the stored OTP for this user.
        On success, marks the user verified and deletes the OTP.
        Returns (success, error_message).
        """
        from datetime import datetime
        row = self._fetchone("SELECT * FROM email_otp WHERE user_id=%s", (user_id,))
        if not row:
            return False, "No verification code found. Please request a new one."
        if str(row["code"]) != str(code).strip():
            return False, "Incorrect code. Please try again."
        if datetime.now() > row["expires_at"]:
            return False, "This code has expired. Please request a new one."
        self.delete_otp(user_id)
        self.mark_user_verified(user_id)
        return True, ""

    # ==============================================================
    # CATEGORIES
    # ==============================================================
    def add_category(self, user_id, name, ctype, icon="💰"):
        return self._execute(
            "INSERT INTO categories (user_id, name, type, icon) VALUES (%s, %s, %s, %s)",
            (user_id, name, ctype, icon),
        )

    def category_belongs_to_user(self, category_id, user_id, ctype=None):
        if not category_id:
            return True
        query = "SELECT category_id FROM categories WHERE category_id=%s AND user_id=%s"
        params = [category_id, user_id]
        if ctype:
            query += " AND type=%s"
            params.append(ctype)
        return self._fetchone(query, params) is not None

    def get_categories(self, user_id, ctype=None):
        if ctype:
            return self._fetchall(
                "SELECT * FROM categories WHERE user_id=%s AND type=%s ORDER BY name",
                (user_id, ctype),
            )
        return self._fetchall(
            "SELECT * FROM categories WHERE user_id=%s ORDER BY type, name", (user_id,)
        )

    def delete_category(self, category_id):
        self._execute("DELETE FROM categories WHERE category_id=%s", (category_id,))

    # ==============================================================
    # INCOME
    # ==============================================================
    def add_income(self, user_id, category_id, amount, source, date, note=""):
        return self._execute(
            """INSERT INTO income (user_id, category_id, amount, source, date, note)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, category_id, amount, source, date, note),
        )

    def update_income(self, user_id, income_id, category_id, amount, source, date, note):
        self._execute(
            """UPDATE income SET category_id=%s, amount=%s, source=%s, date=%s, note=%s
               WHERE income_id=%s AND user_id=%s""",
            (category_id, amount, source, date, note, income_id, user_id),
        )

    def delete_income(self, user_id, income_id):
        self._execute("DELETE FROM income WHERE income_id=%s AND user_id=%s", (income_id, user_id))

    def get_income(self, user_id, start_date=None, end_date=None, category_id=None):
        query = """SELECT i.*, c.name AS category_name, c.icon AS category_icon
                   FROM income i LEFT JOIN categories c ON i.category_id = c.category_id
                   WHERE i.user_id = %s"""
        params = [user_id]
        if start_date and end_date:
            query += " AND i.date BETWEEN %s AND %s"
            params += [start_date, end_date]
        if category_id:
            query += " AND i.category_id = %s"
            params.append(category_id)
        query += " ORDER BY i.date DESC, i.income_id DESC"
        return self._fetchall(query, params)

    def total_income(self, user_id, start_date=None, end_date=None):
        query = "SELECT COALESCE(SUM(amount),0) AS total FROM income WHERE user_id=%s"
        params = [user_id]
        if start_date and end_date:
            query += " AND date BETWEEN %s AND %s"
            params += [start_date, end_date]
        return float(self._fetchone(query, params)["total"])

    # ==============================================================
    # EXPENSE
    # ==============================================================
    def add_expense(self, user_id, category_id, amount, payee, date, payment_mode, note=""):
        return self._execute(
            """INSERT INTO expense (user_id, category_id, amount, payee, date, payment_mode, note)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (user_id, category_id, amount, payee, date, payment_mode, note),
        )

    def update_expense(self, user_id, expense_id, category_id, amount, payee, date, payment_mode, note):
        self._execute(
            """UPDATE expense SET category_id=%s, amount=%s, payee=%s, date=%s,
               payment_mode=%s, note=%s
               WHERE expense_id=%s AND user_id=%s""",
            (category_id, amount, payee, date, payment_mode, note, expense_id, user_id),
        )

    def delete_expense(self, user_id, expense_id):
        self._execute("DELETE FROM expense WHERE expense_id=%s AND user_id=%s", (expense_id, user_id))

    def get_expense(self, user_id, start_date=None, end_date=None, category_id=None):
        query = """SELECT e.*, c.name AS category_name, c.icon AS category_icon
                   FROM expense e LEFT JOIN categories c ON e.category_id = c.category_id
                   WHERE e.user_id = %s"""
        params = [user_id]
        if start_date and end_date:
            query += " AND e.date BETWEEN %s AND %s"
            params += [start_date, end_date]
        if category_id:
            query += " AND e.category_id = %s"
            params.append(category_id)
        query += " ORDER BY e.date DESC, e.expense_id DESC"
        return self._fetchall(query, params)

    def total_expense(self, user_id, start_date=None, end_date=None):
        query = "SELECT COALESCE(SUM(amount),0) AS total FROM expense WHERE user_id=%s"
        params = [user_id]
        if start_date and end_date:
            query += " AND date BETWEEN %s AND %s"
            params += [start_date, end_date]
        return float(self._fetchone(query, params)["total"])

    def expense_by_category(self, user_id, start_date=None, end_date=None):
        query = """SELECT c.name AS category_name, c.icon, COALESCE(SUM(e.amount),0) AS total
                   FROM categories c
                   LEFT JOIN expense e ON e.category_id = c.category_id
                   AND e.user_id = c.user_id"""
        params = []
        if start_date and end_date:
            query += " AND e.date BETWEEN %s AND %s"
            params += [start_date, end_date]
        query += " WHERE c.user_id = %s AND c.type='expense' GROUP BY c.category_id, c.name, c.icon HAVING total > 0"
        params.append(user_id)
        return self._fetchall(query, params)

    def monthly_trend(self, user_id, months_back=6):
        query = """SELECT DATE_FORMAT(date, '%%Y-%%m') AS ym, SUM(amount) AS total
                   FROM expense WHERE user_id=%s
                   GROUP BY ym ORDER BY ym DESC LIMIT %s"""
        return self._fetchall(query, (user_id, int(months_back)))

    def monthly_income_trend(self, user_id, months_back=6):
        query = """SELECT DATE_FORMAT(date, '%%Y-%%m') AS ym, SUM(amount) AS total
                   FROM income WHERE user_id=%s
                   GROUP BY ym ORDER BY ym DESC LIMIT %s"""
        return self._fetchall(query, (user_id, int(months_back)))

    # ==============================================================
    # COMBINED / DASHBOARD
    # ==============================================================
    def recent_transactions(self, user_id, limit=8):
        query = """
            SELECT 'income' AS kind, income_id AS id, amount, source AS label,
                   date, category_id FROM income WHERE user_id=%s
            UNION ALL
            SELECT 'expense' AS kind, expense_id AS id, amount, payee AS label,
                   date, category_id FROM expense WHERE user_id=%s
            ORDER BY date DESC, id DESC LIMIT %s
        """
        return self._fetchall(query, (user_id, user_id, int(limit)))
