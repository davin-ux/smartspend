# SmartSpend Pro — Web Edition 💰

A personal finance / expense tracker **web app** built with **Python (Flask)**,
**MySQL**, and vanilla HTML/CSS/JS. This is the web version of the SmartSpend
Pro desktop app — same features, same database schema, but runs in any
browser: phone, tablet, or desktop. No installation needed on the device
you use it from — only the computer running the server needs Python + MySQL.

## Features

- 🔐 Secure login/registration (salted PBKDF2-SHA256 password hashing)
- 📧 Email verification (OTP) — Instagram-style: a 6-digit code is emailed after signup (or on login to an unverified account), required before access is granted
- 🏠 Dashboard — income/expense/balance summary, budget progress bar, recent activity
- 💵 Income & 💳 Expense tracking — add/edit/delete, categorized
- 📄 Reports — filter by type/date range, CSV export
- 📊 Analytics — expense-by-category pie chart, monthly trend chart (Chart.js)
- 👤 Profile — edit info, change password
- ⚙️ Settings — currency, monthly budget, logout
- 📱 **Fully responsive** — adapts across phone, tablet, laptop, and large desktop screens

## Tech Stack

| Layer      | Technology                    |
|------------|--------------------------------|
| Backend    | Python 3.10+, Flask             |
| Database   | MySQL 8.0+ (mysql-connector-python) |
| Frontend   | Server-rendered Jinja2 templates + vanilla CSS/JS |
| Charts     | Chart.js (via CDN)               |

## Project Structure

```
SmartSpend-Web/
├── app.py                # Flask app — all routes
├── config.py               # MySQL connection settings, app constants
├── database.py              # All MySQL CRUD operations (same as desktop version)
├── utils.py                 # Hashing, validation, formatting helpers
├── templates/
│   ├── base.html            # Shared shell: sidebar/topbar nav, responsive layout
│   ├── login.html / register.html
│   ├── dashboard.html
│   ├── income.html / expense.html
│   ├── reports.html
│   ├── analytics.html
│   ├── profile.html
│   └── settings.html
├── static/
│   ├── css/style.css        # All styling, incl. responsive breakpoints
│   └── assets/              # Logo, icons, background image
├── sql/
│   └── smartspend.sql       # Database schema (auto-run on first launch)
├── exports/                  # CSV reports saved here
└── requirements.txt
```

## Setup & Run

1. Install Python 3.10+ and have **MySQL Server** running (same as the
   desktop version — see its README for install steps per OS).
2. Open `config.py` and set your MySQL credentials in `MYSQL_CONFIG`.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the server:
   ```bash
   python app.py
   ```
5. Open **http://localhost:5000** in a browser on the same computer.

The server runs with `debug=False` by default so Flask's interactive debugger is
not exposed to devices on your network.

### Using it from your phone or tablet

The server binds to `0.0.0.0`, so any device on the **same Wi-Fi network**
as the computer running it can reach it too:

1. Find your computer's local IP address:
   - Windows: `ipconfig` (look for "IPv4 Address")
   - Mac/Linux: `ifconfig` or `ip addr` (look for something like `192.168.x.x`)
2. On your phone/tablet's browser, go to `http://<that-ip>:5000` — e.g.
   `http://192.168.1.42:5000`.
3. Make sure your phone and computer are on the same Wi-Fi, and that your
   computer's firewall allows incoming connections on port 5000.

The layout automatically adapts: full sidebar on desktop, icon-only sidebar
on tablets, and a top bar with scrollable nav on phones.

## Notes for Your Report

- Reuses the exact same `database.py` and MySQL schema as the desktop
  CustomTkinter version — only the presentation layer changed, which shows
  clean separation between business logic and UI.
- Sessions are handled with Flask's signed cookie sessions (`session["user_id"]`);
  a `login_required` decorator protects every authenticated route.
- Responsive design uses plain CSS media queries at 600px, 1024px, and
  1440px breakpoints — no framework needed.
- For a real deployment (not just local network testing), you'd run this
  behind a production WSGI server (e.g. gunicorn) and set a fixed
  `SMARTSPEND_SECRET_KEY` environment variable instead of the auto-generated one.

## Troubleshooting

If every page shows **"Couldn't connect to the database"**, or login/register
don't work, it's almost always one of these:

| Symptom | Likely cause | Fix |
|---|---|---|
| "Couldn't connect to the database" page | MySQL Server isn't running | Start MySQL (services app on Windows, `brew services start mysql` on Mac, `sudo systemctl start mysql` on Linux) |
| Error mentions "Access denied for user" | Wrong password in `config.py` | Set the real password in `MYSQL_CONFIG["password"]` |
| Error mentions "Can't connect to MySQL server" | Wrong host/port, or server not running | Check `MYSQL_CONFIG["host"]`/`["port"]` match your MySQL setup |
| `ModuleNotFoundError` when running `python app.py` | Dependencies not installed | Run `pip install -r requirements.txt` again |
| Registration works but no email arrives | `EMAIL_CONFIG` not set in `config.py` | Either fill it in, or just use the code shown in the flash message — the app shows it automatically when email isn't configured |
| Can't reach it from your phone | Different Wi-Fi network, or firewall blocking port 5000 | Confirm both devices are on the same Wi-Fi; allow inbound connections on port 5000 in your firewall |
