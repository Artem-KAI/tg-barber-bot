# 💈 The Iron Throne Barbershop — Telegram Bot

A modern, full-featured appointment booking Telegram bot built with **Python 3.11+**, **aiogram 3.x**, and **aiosqlite**.

Designed for premium barbershops, salons, and independent master barbers. Features complete schedule customisation, date/time slot bookings, days-off management, client self-service, barber studio, and an administrative control panel.

---

## 🌟 Key Features

### 👤 For Clients
- **Interactive Booking Flow**:
  1. Full name input
  2. Phone number input
  3. Service selection with USD pricing
  4. Barber selection with ratings (⭐) and price segments (*Budget*, *Standard*, *Premium*)
  5. Available dates calendar (next 14 days, dynamically filtered by barber schedule and days off)
  6. Available time slots picker (excludes booked slots and past hours on today's date)
  7. Final booking preview & confirmation card
- **Booking Self-Service**:
  - View all active bookings in **📋 My Bookings**
  - Edit client name, phone number, service, or assigned barber before confirmation
    (a new barber is only accepted if they are free at the booked time)
  - Cancel pending bookings with automatic barber notification
  - Each time slot can only be booked once (enforced by the database)
  - Unconfirmed requests whose time has passed expire automatically and the client is told
- **Shop Location & Map**:
  - Direct 1-tap **📍 Location & Map** integration
  - Interactive Google Maps button opening the NYC shop location

### 🪒 For Barbers
- **Self-Registration**:
  - Submit application with professional name, bio, and desired price segment
  - Real-time notification sent directly to the admin for review
- **Barber Studio**:
  - **🗓️ My Schedule**: Interactive 2-step schedule builder (toggle working days of week Mon–Sun, toggle working hours/slots).
    A day or slot that still has upcoming bookings cannot be removed.
  - **🏖️ Days Off**: 30-day interactive calendar to toggle specific dates off (dates with active bookings are refused)
  - **📅 Incoming Bookings**: Active bookings, nearest first. Confirm, decline, change service or price, mark as completed
  - **👤 Profile Management**: Edit display name, bio, segment, and custom service prices (custom prices are used for new bookings)
  - **⚠️ Delete Profile / Leave**: Delete the profile; active bookings are cancelled and the clients notified
- **Instant Alerts**:
  - Receive formatted cards for new bookings (with Confirm / Decline buttons), client edits, or cancellations

### ⚙️ For Administrators
- Automatically initialized upon first launch via `ADMIN_ID`
- **📋 Pending Applications**: Approve or decline applicant barbers with 1 click (also straight from the notification)
- **👥 All Barbers**: View all barbers; set a barber's rating or remove a barber (their active bookings are cancelled)
- **📂 All Bookings**: Overview of recent shop visits and statuses
- **💲 Studio Base Prices**: Manage base studio pricing for all services

---

## 📍 Barbershop Location

- **Name**: The Iron Throne Barbershop
- **Address**: 347 W 42nd St, New York, NY 10036, USA
- **Hours**: Monday – Saturday: 9:00 AM – 8:00 PM (Eastern Time)
- **Map Link**: [Open in Google Maps](https://www.google.com/maps/search/?api=1&query=347+W+42nd+St+New+York+NY+10036)

---

## 📁 Clean Architecture

```text
├── .env                  # Private credentials (ignored by git)
├── .gitignore            # Git exclusion rules
├── main.py               # Bot entry point and dispatcher startup
├── README.md             # Documentation
├── requirements.txt      # Python dependencies
├── app/                  # Core application package
│   ├── __init__.py
│   ├── config.py         # Environment configuration loader
│   ├── db.py             # Async database layer (aiosqlite) with migrations
│   ├── formatters.py     # HTML booking and profile cards
│   ├── keyboards.py      # Reply and inline keyboard builders
│   ├── states.py         # FSM state groups
│   ├── storage.py        # SQLite FSM storage (conversations survive restarts)
│   ├── texts.py          # English UI strings, button labels, and emojis
│   └── utils.py          # Helper utilities and permissions
├── data/
│   └── bot.db            # SQLite database file (WAL mode)
└── handlers/             # Modular aiogram routers
    ├── __init__.py       # Router aggregator
    ├── admin.py          # Admin panel & application review
    ├── barber.py         # Barber studio, schedule, days off, bookings
    ├── booking.py        # Client booking flow and booking management
    └── common.py         # /start, cancel, shop location, status
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.10 or higher
- A Telegram account
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- Your Telegram User ID from [@userinfobot](https://t.me/userinfobot)

### 2. Configuration (`.env`)
Create a `.env` file in the root project directory:

```env
BOT_TOKEN=YOUR_BOT_TOKEN_HERE
ADMIN_ID=YOUR_TELEGRAM_USER_ID_HERE
# Optional:
# TIMEZONE=America/New_York   # shop timezone used for dates and time slots
# DB_PATH=data/bot.db         # SQLite file location
```

> **Security Note**: Never commit your `.env` file or share your bot token and admin ID publicly. The `.gitignore` file already includes `.env` to prevent accidental commits.

### 3. Installation

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Running the Bot

```bash
python main.py
```

Upon launch:
- The SQLite database will be initialized automatically at `data/bot.db`
- Existing schemas and column migrations will execute smoothly
- Default services and schedule presets will be created if not present
- The admin account will be registered with master barber privileges

---

## 🧪 Testing Checklist

1. **Admin Initialisation**:
   - Send `/start` from your admin Telegram account.
   - The main menu will display the **⚙️ Admin Panel** and **🪒 Barber Studio** buttons.
2. **Barber Registration**:
   - Send `/start` from a second Telegram account.
   - Tap **✂️ Become a Barber**, provide a name, short bio, and select a segment (*Budget*, *Standard*, or *Premium*).
   - In the admin account, tap **⚙️ Admin Panel** → **📋 Pending Barber Applications** → **Approve**.
3. **Barber Schedule & Days Off**:
   - From the approved barber account, open **🪒 Barber Studio**.
   - Tap **🗓️ My Schedule** to toggle working days (Mon–Sun) and preferred time slots.
   - Tap **🏖️ Days Off** to mark any upcoming days as off (marked with 🏖️).
4. **Client Booking**:
   - Tap **✂️ Book an Appointment** from a client account.
   - Provide name, phone number, service, barber, date, and time slot.
   - Confirm the booking.
   - Notice the instant notification sent to the chosen barber!
5. **Location & Map**:
   - Tap **📍 Location & Map** from the main menu.
   - Tap **🗺️ Open in Google Maps** to view the NYC barbershop location.

---

## 📜 License

MIT License. Designed with care for modern barbershop operations.
