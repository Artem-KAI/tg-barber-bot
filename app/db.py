"""Async database layer — wraps aiosqlite for all DB operations."""
from __future__ import annotations

import datetime
import logging
import os
from typing import Any

import aiosqlite

from app.config import local_now, local_today, settings
from app.texts import TIME_SLOTS

__all__ = ["Database", "db"]

logger = logging.getLogger(__name__)

DEFAULT_WORKDAYS: list[int] = [0, 1, 2, 3, 4, 5]  # Mon–Sat


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")


class Database:
    """Async SQLite database helper with backwards-compatible schema management."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Open the database connection and initialise schema."""
        # data/ is git-ignored, so it does not exist on a fresh checkout
        db_dir = os.path.dirname(self._path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._init_schema()

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database not connected"
        return self._conn

    # ── Schema initialisation & migrations ────────────────────────────────────

    async def _safe_add_column(self, table: str, column_def: str) -> None:
        """Add a column to a table if it doesn't already exist."""
        try:
            await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
            await self.conn.commit()
        except Exception:
            pass  # Column already exists

    async def _init_schema(self) -> None:
        """Create new tables and safely migrate existing ones."""
        # 1. Users table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id   INTEGER PRIMARY KEY,
                username  TEXT,
                full_name TEXT,
                joined_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # 2. Barbers table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS barbers (
                user_id    INTEGER PRIMARY KEY,
                name       TEXT NOT NULL,
                bio        TEXT NOT NULL DEFAULT '',
                rating     REAL NOT NULL DEFAULT 4.7,
                segment    TEXT NOT NULL DEFAULT 'standard',
                price_min  INTEGER NOT NULL DEFAULT 40,
                price_max  INTEGER NOT NULL DEFAULT 70,
                status     TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # 3. Services table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                code      TEXT UNIQUE,
                title     TEXT,
                name      TEXT,
                price     REAL,
                price_usd INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Ensure name and price columns exist on services
        await self._safe_add_column("services", "code TEXT")
        await self._safe_add_column("services", "name TEXT")
        await self._safe_add_column("services", "price REAL")

        # 4. Barber services mapping table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS barber_services (
                barber_id  INTEGER NOT NULL,
                service_id INTEGER NOT NULL,
                price      REAL,
                price_usd  INTEGER,
                PRIMARY KEY (barber_id, service_id),
                FOREIGN KEY (barber_id)  REFERENCES barbers(user_id),
                FOREIGN KEY (service_id) REFERENCES services(id)
            )
        """)
        await self._safe_add_column("barber_services", "price REAL")

        # 5. Bookings table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id     INTEGER NOT NULL,
                barber_id     INTEGER NOT NULL,
                service_id    INTEGER NOT NULL DEFAULT 1,
                client_name   TEXT NOT NULL DEFAULT '',
                phone         TEXT NOT NULL DEFAULT '',
                client_phone  TEXT,
                service_name  TEXT,
                price         REAL,
                price_usd     INTEGER NOT NULL DEFAULT 0,
                slot_datetime TEXT,
                status        TEXT NOT NULL DEFAULT 'pending',
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await self._safe_add_column("bookings", "client_phone TEXT")
        await self._safe_add_column("bookings", "service_name TEXT")
        await self._safe_add_column("bookings", "price REAL")
        await self._safe_add_column("bookings", "slot_datetime TEXT")

        # 6. Barber schedule tables
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS barber_schedule (
                barber_id INTEGER NOT NULL,
                weekday   INTEGER NOT NULL,
                PRIMARY KEY (barber_id, weekday),
                FOREIGN KEY (barber_id) REFERENCES barbers(user_id)
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS barber_time_slots (
                barber_id INTEGER NOT NULL,
                slot_time TEXT NOT NULL,
                PRIMARY KEY (barber_id, slot_time),
                FOREIGN KEY (barber_id) REFERENCES barbers(user_id)
            )
        """)

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS barber_days_off (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                barber_id INTEGER NOT NULL,
                off_date  TEXT NOT NULL,
                UNIQUE(barber_id, off_date),
                FOREIGN KEY (barber_id) REFERENCES barbers(user_id)
            )
        """)

        # 7. Persistent FSM storage (conversation state survives restarts)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS fsm_storage (
                key   TEXT PRIMARY KEY,
                state TEXT,
                data  TEXT NOT NULL DEFAULT '{}'
            )
        """)

        await self.conn.commit()

        # Populate users from existing barbers
        await self.conn.execute("""
            INSERT OR IGNORE INTO users (user_id, username, full_name)
            SELECT user_id, NULL, name FROM barbers
        """)

        # Seed English services. Existing rows keep their price, otherwise every
        # restart would overwrite the prices the admin set in the panel.
        default_services = [
            ("consultation", "Consultation", 25.0),
            ("full_service", "Full Service", 55.0),
            ("express", "Express Cut", 35.0),
            ("beard", "Beard Grooming", 20.0),
            ("hot_shave", "Hot Towel Shave", 30.0),
        ]
        for code, name, price in default_services:
            await self.conn.execute("""
                INSERT INTO services (code, title, name, price, price_usd)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    title = excluded.name
            """, (code, name, name, price, int(price)))

        # Update any NULL names/prices in services
        await self.conn.execute("""
            UPDATE services SET name = title WHERE name IS NULL
        """)
        await self.conn.execute("""
            UPDATE services SET price = price_usd WHERE price IS NULL
        """)

        # Synchronize existing bookings columns
        await self.conn.execute("""
            UPDATE bookings SET client_phone = phone WHERE client_phone IS NULL
        """)
        await self.conn.execute("""
            UPDATE bookings SET price = price_usd WHERE price IS NULL
        """)
        await self.conn.execute("""
            UPDATE bookings SET service_name = (
                SELECT COALESCE(name, title) FROM services WHERE services.id = bookings.service_id
            ) WHERE service_name IS NULL
        """)

        # One active booking per barber per slot. Older databases may already
        # contain duplicates: keep the earliest booking, cancel the rest.
        await self.conn.execute("""
            UPDATE bookings SET status = 'cancelled'
            WHERE status IN ('pending', 'confirmed') AND slot_datetime IS NOT NULL
              AND id NOT IN (
                SELECT MIN(id) FROM bookings
                WHERE status IN ('pending', 'confirmed') AND slot_datetime IS NOT NULL
                GROUP BY barber_id, slot_datetime
              )
        """)
        await self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_bookings_active_slot
            ON bookings (barber_id, slot_datetime)
            WHERE status IN ('pending', 'confirmed') AND slot_datetime IS NOT NULL
        """)

        await self.conn.commit()

        # Ensure approved barbers have default schedules
        cur = await self.conn.execute("SELECT user_id FROM barbers WHERE status = 'approved'")
        rows = await cur.fetchall()
        for r in rows:
            await self.ensure_barber_defaults(r["user_id"])

    async def ensure_barber_defaults(self, barber_id: int) -> None:
        """Seed default working weekdays and time slots if not already configured."""
        cur = await self.conn.execute(
            "SELECT COUNT(*) FROM barber_schedule WHERE barber_id = ?", (barber_id,)
        )
        row = await cur.fetchone()
        if row and row[0] == 0:
            await self.conn.executemany(
                "INSERT OR IGNORE INTO barber_schedule (barber_id, weekday) VALUES (?, ?)",
                [(barber_id, w) for w in DEFAULT_WORKDAYS],
            )

        cur = await self.conn.execute(
            "SELECT COUNT(*) FROM barber_time_slots WHERE barber_id = ?", (barber_id,)
        )
        row = await cur.fetchone()
        if row and row[0] == 0:
            await self.conn.executemany(
                "INSERT OR IGNORE INTO barber_time_slots (barber_id, slot_time) VALUES (?, ?)",
                [(barber_id, s) for s in TIME_SLOTS],
            )
        await self.conn.commit()

    # ── FSM storage ───────────────────────────────────────────────────────────

    async def fsm_get(self, key: str) -> aiosqlite.Row | None:
        cur = await self.conn.execute("SELECT state, data FROM fsm_storage WHERE key = ?", (key,))
        return await cur.fetchone()

    async def fsm_set_state(self, key: str, state: str | None) -> None:
        await self.conn.execute(
            """
            INSERT INTO fsm_storage (key, state) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET state = excluded.state
            """,
            (key, state),
        )
        await self.conn.commit()

    async def fsm_set_data(self, key: str, data_json: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO fsm_storage (key, data) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET data = excluded.data
            """,
            (key, data_json),
        )
        await self.conn.commit()

    # ── Users ─────────────────────────────────────────────────────────────────

    async def ensure_user(
        self, user_id: int, username: str | None, full_name: str
    ) -> None:
        """Insert or update a user record."""
        await self.conn.execute(
            """
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username  = excluded.username,
                full_name = excluded.full_name
            """,
            (user_id, username, full_name),
        )
        await self.conn.commit()

    # ── Barbers ───────────────────────────────────────────────────────────────

    async def get_barber(self, user_id: int) -> aiosqlite.Row | None:
        """Return barber row or None."""
        cur = await self.conn.execute(
            "SELECT * FROM barbers WHERE user_id = ?", (user_id,)
        )
        return await cur.fetchone()

    async def create_barber_application(
        self, user_id: int, name: str, bio: str, segment: str
    ) -> None:
        """Insert a new barber application with status='pending'."""
        now = utcnow()
        await self.conn.execute(
            """
            INSERT INTO barbers (user_id, name, bio, segment, status, rating, created_at)
            VALUES (?, ?, ?, ?, 'pending', 4.8, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name       = excluded.name,
                bio        = excluded.bio,
                segment    = excluded.segment,
                status     = 'pending'
            """,
            (user_id, name, bio, segment, now),
        )
        await self.conn.commit()

    async def approve_barber(self, user_id: int) -> None:
        """Approve a barber application and ensure default schedule."""
        await self.conn.execute(
            "UPDATE barbers SET status = 'approved' WHERE user_id = ?", (user_id,)
        )
        await self.conn.commit()
        await self.ensure_barber_defaults(user_id)

    async def reject_barber(self, user_id: int) -> None:
        """Reject a barber application."""
        await self.conn.execute(
            "UPDATE barbers SET status = 'rejected' WHERE user_id = ?", (user_id,)
        )
        await self.conn.commit()

    async def set_barber_left(self, user_id: int) -> None:
        """Mark a barber as left."""
        await self.conn.execute(
            "UPDATE barbers SET status = 'left' WHERE user_id = ?", (user_id,)
        )
        await self.conn.commit()

    async def cancel_active_barber_bookings(self, barber_id: int) -> list[aiosqlite.Row]:
        """Cancel all pending/confirmed bookings of a barber; return the affected rows."""
        cur = await self.conn.execute(
            """
            SELECT id, client_id FROM bookings
            WHERE barber_id = ? AND status IN ('pending', 'confirmed')
            """,
            (barber_id,),
        )
        rows = await cur.fetchall()
        await self.conn.execute(
            """
            UPDATE bookings SET status = 'cancelled', updated_at = ?
            WHERE barber_id = ? AND status IN ('pending', 'confirmed')
            """,
            (utcnow(), barber_id),
        )
        await self.conn.commit()
        return list(rows)

    async def delete_barber(self, user_id: int) -> None:
        """Completely delete a barber profile and all associated schedules."""
        await self.conn.execute("DELETE FROM barber_services WHERE barber_id = ?", (user_id,))
        await self.conn.execute("DELETE FROM barber_schedule WHERE barber_id = ?", (user_id,))
        await self.conn.execute("DELETE FROM barber_time_slots WHERE barber_id = ?", (user_id,))
        await self.conn.execute("DELETE FROM barber_days_off WHERE barber_id = ?", (user_id,))
        await self.conn.execute("DELETE FROM barbers WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    async def get_pending_barbers(self) -> list[aiosqlite.Row]:
        """Return all barbers with status='pending'."""
        cur = await self.conn.execute(
            """
            SELECT b.*, u.username
            FROM barbers b
            LEFT JOIN users u ON u.user_id = b.user_id
            WHERE b.status = 'pending'
            ORDER BY b.created_at DESC
            """
        )
        return await cur.fetchall()

    async def get_all_barbers(self) -> list[aiosqlite.Row]:
        """Return all barber rows regardless of status."""
        cur = await self.conn.execute(
            """
            SELECT b.*, u.username
            FROM barbers b
            LEFT JOIN users u ON u.user_id = b.user_id
            ORDER BY b.status, b.name
            """
        )
        return await cur.fetchall()

    async def get_approved_barbers(self) -> list[aiosqlite.Row]:
        """Return only approved barbers."""
        cur = await self.conn.execute(
            "SELECT * FROM barbers WHERE status = 'approved' ORDER BY rating DESC, name"
        )
        return await cur.fetchall()

    async def update_barber_field(
        self, user_id: int, field: str, value: Any
    ) -> None:
        """Update a single column in the barbers table."""
        allowed = {"name", "bio", "rating", "segment", "status"}
        if field not in allowed:
            raise ValueError(f"Disallowed field: {field}")
        await self.conn.execute(
            f"UPDATE barbers SET {field} = ? WHERE user_id = ?", (value, user_id)
        )
        await self.conn.commit()

    async def ensure_admin_barber(self, admin_id: int) -> None:
        """Make sure the admin user has an approved barber record and default schedule."""
        cur = await self.conn.execute(
            "SELECT user_id FROM barbers WHERE user_id = ?", (admin_id,)
        )
        row = await cur.fetchone()
        if not row:
            now = utcnow()
            await self.conn.execute(
                """
                INSERT OR IGNORE INTO barbers (user_id, name, bio, segment, rating, status, created_at)
                VALUES (?, 'Studio Admin', 'Barbershop owner and master barber.', 'premium', 5.0, 'approved', ?)
                """,
                (admin_id, now),
            )
            await self.conn.commit()
        await self.ensure_barber_defaults(admin_id)

    # ── Services ──────────────────────────────────────────────────────────────

    async def get_services(self) -> list[aiosqlite.Row]:
        """Return all global services with normalised .name and .price."""
        cur = await self.conn.execute(
            "SELECT id, code, COALESCE(name, title) AS name, COALESCE(price, price_usd) AS price FROM services ORDER BY id"
        )
        return await cur.fetchall()

    async def get_service_by_id(self, service_id: int) -> aiosqlite.Row | None:
        cur = await self.conn.execute(
            "SELECT id, code, COALESCE(name, title) AS name, COALESCE(price, price_usd) AS price FROM services WHERE id = ?",
            (service_id,),
        )
        return await cur.fetchone()

    async def get_service_by_name(self, name: str) -> aiosqlite.Row | None:
        cur = await self.conn.execute(
            "SELECT id, code, COALESCE(name, title) AS name, COALESCE(price, price_usd) AS price FROM services WHERE name = ? OR title = ?",
            (name, name),
        )
        return await cur.fetchone()

    async def update_service_price(self, service_id: int, price: float) -> None:
        await self.conn.execute(
            "UPDATE services SET price = ?, price_usd = ? WHERE id = ?",
            (price, int(price), service_id),
        )
        await self.conn.commit()

    async def get_barber_service_price(
        self, barber_id: int, service_name: str
    ) -> float | None:
        """Return barber-specific price for a service, or None if not set."""
        cur = await self.conn.execute(
            """
            SELECT COALESCE(bs.price, bs.price_usd) AS price
            FROM barber_services bs
            JOIN services s ON s.id = bs.service_id
            WHERE bs.barber_id = ? AND (s.name = ? OR s.title = ?)
            """,
            (barber_id, service_name, service_name),
        )
        row = await cur.fetchone()
        if row and row["price"] is not None:
            return float(row["price"])
        return None

    async def get_effective_price(self, barber_id: int, service_id: int) -> float | None:
        """Barber-specific price for a service, falling back to the studio price."""
        cur = await self.conn.execute(
            """
            SELECT COALESCE(bs.price, bs.price_usd, s.price, s.price_usd) AS price
            FROM services s
            LEFT JOIN barber_services bs ON bs.service_id = s.id AND bs.barber_id = ?
            WHERE s.id = ?
            """,
            (barber_id, service_id),
        )
        row = await cur.fetchone()
        if row and row["price"] is not None:
            return float(row["price"])
        return None

    async def set_barber_service_price(
        self, barber_id: int, service_id: int, price: float
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO barber_services (barber_id, service_id, price, price_usd)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(barber_id, service_id) DO UPDATE SET
                price = excluded.price,
                price_usd = excluded.price_usd
            """,
            (barber_id, service_id, price, int(price)),
        )
        await self.conn.commit()

    # ── Bookings ──────────────────────────────────────────────────────────────

    async def create_booking(
        self,
        client_id: int,
        barber_id: int,
        client_name: str,
        client_phone: str,
        service_name: str,
        price: float,
        slot_datetime: str | None = None,
        service_id: int | None = None,
    ) -> int | None:
        """
        Insert a new booking with full column compatibility.
        Returns None if the slot is already taken (unique index violation).
        """
        if service_id is None:
            svc = await self.get_service_by_name(service_name)
            service_id = svc["id"] if svc else 1

        now = utcnow()
        try:
            cur = await self.conn.execute(
                """
                INSERT INTO bookings
                    (client_id, barber_id, service_id, client_name,
                     phone, client_phone, service_name, price, price_usd,
                     slot_datetime, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    client_id,
                    barber_id,
                    service_id,
                    client_name,
                    client_phone,
                    client_phone,
                    service_name,
                    price,
                    int(price),
                    slot_datetime,
                    now,
                    now,
                ),
            )
        except aiosqlite.IntegrityError:
            await self.conn.rollback()
            return None
        await self.conn.commit()
        return cur.lastrowid

    async def get_booking(self, booking_id: int) -> aiosqlite.Row | None:
        cur = await self.conn.execute(
            """
            SELECT
                id, client_id, barber_id, service_id, client_name,
                COALESCE(client_phone, phone) AS client_phone,
                COALESCE(client_phone, phone) AS phone,
                COALESCE(service_name, (SELECT COALESCE(name, title) FROM services WHERE services.id = bookings.service_id)) AS service_name,
                COALESCE(price, price_usd) AS price,
                COALESCE(price, price_usd) AS price_usd,
                slot_datetime, status, created_at, updated_at
            FROM bookings
            WHERE id = ?
            """,
            (booking_id,),
        )
        return await cur.fetchone()

    async def get_client_bookings(self, client_id: int) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            """
            SELECT
                id, client_id, barber_id, service_id, client_name,
                COALESCE(client_phone, phone) AS client_phone,
                COALESCE(service_name, (SELECT COALESCE(name, title) FROM services WHERE services.id = bookings.service_id)) AS service_name,
                COALESCE(price, price_usd) AS price,
                slot_datetime, status, created_at
            FROM bookings
            WHERE client_id = ?
            ORDER BY id DESC
            LIMIT 20
            """,
            (client_id,),
        )
        return await cur.fetchall()

    async def get_barber_bookings(
        self, barber_id: int, status: str | None = None, active_only: bool = False
    ) -> list[aiosqlite.Row]:
        if active_only:
            cur = await self.conn.execute(
                """
                SELECT
                    id, client_id, barber_id, service_id, client_name,
                    COALESCE(client_phone, phone) AS client_phone,
                    COALESCE(service_name, (SELECT COALESCE(name, title) FROM services WHERE services.id = bookings.service_id)) AS service_name,
                    COALESCE(price, price_usd) AS price,
                    slot_datetime, status, created_at
                FROM bookings
                WHERE barber_id = ? AND status IN ('pending', 'confirmed')
                ORDER BY slot_datetime, id
                LIMIT 50
                """,
                (barber_id,),
            )
            return await cur.fetchall()
        if status:
            cur = await self.conn.execute(
                """
                SELECT
                    id, client_id, barber_id, service_id, client_name,
                    COALESCE(client_phone, phone) AS client_phone,
                    COALESCE(service_name, (SELECT COALESCE(name, title) FROM services WHERE services.id = bookings.service_id)) AS service_name,
                    COALESCE(price, price_usd) AS price,
                    slot_datetime, status, created_at
                FROM bookings
                WHERE barber_id = ? AND status = ?
                ORDER BY id DESC
                LIMIT 30
                """,
                (barber_id, status),
            )
        else:
            cur = await self.conn.execute(
                """
                SELECT
                    id, client_id, barber_id, service_id, client_name,
                    COALESCE(client_phone, phone) AS client_phone,
                    COALESCE(service_name, (SELECT COALESCE(name, title) FROM services WHERE services.id = bookings.service_id)) AS service_name,
                    COALESCE(price, price_usd) AS price,
                    slot_datetime, status, created_at
                FROM bookings
                WHERE barber_id = ?
                ORDER BY id DESC
                LIMIT 30
                """,
                (barber_id,),
            )
        return await cur.fetchall()

    async def get_all_bookings(self) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            """
            SELECT
                b.id, b.client_id, b.barber_id, b.service_id, b.client_name,
                COALESCE(b.client_phone, b.phone) AS client_phone,
                COALESCE(b.service_name, (SELECT COALESCE(s.name, s.title) FROM services s WHERE s.id = b.service_id)) AS service_name,
                COALESCE(b.price, b.price_usd) AS price,
                b.slot_datetime, b.status, b.created_at,
                br.name AS barber_name
            FROM bookings b
            LEFT JOIN barbers br ON br.user_id = b.barber_id
            ORDER BY b.id DESC
            LIMIT 50
            """
        )
        return await cur.fetchall()

    async def update_booking_status(self, booking_id: int, status: str) -> None:
        now = utcnow()
        await self.conn.execute(
            "UPDATE bookings SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, booking_id),
        )
        await self.conn.commit()

    async def update_booking_field(
        self, booking_id: int, field: str, value: Any
    ) -> None:
        allowed = {
            "client_name", "client_phone", "service_name", "service_id",
            "price", "status", "slot_datetime", "barber_id",
        }
        if field not in allowed:
            raise ValueError(f"Disallowed field: {field}")

        now = utcnow()
        if field == "client_phone":
            await self.conn.execute(
                "UPDATE bookings SET client_phone = ?, phone = ?, updated_at = ? WHERE id = ?",
                (value, value, now, booking_id),
            )
        elif field == "price":
            await self.conn.execute(
                "UPDATE bookings SET price = ?, price_usd = ?, updated_at = ? WHERE id = ?",
                (float(value), int(value), now, booking_id),
            )
        else:
            await self.conn.execute(
                f"UPDATE bookings SET {field} = ?, updated_at = ? WHERE id = ?",
                (value, now, booking_id),
            )
        await self.conn.commit()

    async def get_booked_slots(
        self, barber_id: int, date_str: str
    ) -> list[str]:
        """Return list of slot times (HH:MM) already booked for a barber on a date."""
        cur = await self.conn.execute(
            """
            SELECT slot_datetime FROM bookings
            WHERE barber_id = ?
              AND slot_datetime LIKE ?
              AND status IN ('pending', 'confirmed')
            """,
            (barber_id, f"{date_str}%"),
        )
        rows = await cur.fetchall()
        result: list[str] = []
        for row in rows:
            if row["slot_datetime"]:
                parts = row["slot_datetime"].split(" ")
                if len(parts) == 2:
                    result.append(parts[1])
        return result

    async def reassign_booking(self, booking_id: int, barber_id: int, price: float | None) -> bool:
        """Move a booking to another barber. False if that barber's slot is taken."""
        try:
            if price is None:
                await self.conn.execute(
                    "UPDATE bookings SET barber_id = ?, updated_at = ? WHERE id = ?",
                    (barber_id, utcnow(), booking_id),
                )
            else:
                await self.conn.execute(
                    "UPDATE bookings SET barber_id = ?, price = ?, price_usd = ?, updated_at = ? WHERE id = ?",
                    (barber_id, float(price), int(price), utcnow(), booking_id),
                )
        except aiosqlite.IntegrityError:
            await self.conn.rollback()
            return False
        await self.conn.commit()
        return True

    async def get_active_bookings_on(self, barber_id: int, date_str: str) -> list[aiosqlite.Row]:
        """Active bookings of the barber on a given date (YYYY-MM-DD)."""
        cur = await self.conn.execute(
            """
            SELECT id, client_id, slot_datetime FROM bookings
            WHERE barber_id = ? AND slot_datetime LIKE ?
              AND status IN ('pending', 'confirmed')
            ORDER BY slot_datetime
            """,
            (barber_id, f"{date_str} %"),
        )
        return await cur.fetchall()

    async def get_upcoming_active_bookings(self, barber_id: int) -> list[aiosqlite.Row]:
        """Active bookings of the barber that are not in the past."""
        cur = await self.conn.execute(
            """
            SELECT id, client_id, slot_datetime FROM bookings
            WHERE barber_id = ? AND status IN ('pending', 'confirmed')
              AND slot_datetime >= ?
            ORDER BY slot_datetime
            """,
            (barber_id, local_now().strftime("%Y-%m-%d %H:%M")),
        )
        return await cur.fetchall()

    async def expire_past_bookings(self) -> list[aiosqlite.Row]:
        """
        Mark pending bookings whose time has passed (never confirmed) as 'expired'.
        Returns the affected rows so clients can be notified.
        """
        now = local_now().strftime("%Y-%m-%d %H:%M")
        cur = await self.conn.execute(
            """
            SELECT id, client_id, barber_id FROM bookings
            WHERE status = 'pending' AND slot_datetime IS NOT NULL AND slot_datetime < ?
            """,
            (now,),
        )
        rows = await cur.fetchall()
        if rows:
            await self.conn.execute(
                """
                UPDATE bookings SET status = 'expired', updated_at = ?
                WHERE status = 'pending' AND slot_datetime IS NOT NULL AND slot_datetime < ?
                """,
                (utcnow(), now),
            )
            await self.conn.commit()
        return list(rows)

    async def is_slot_taken(
        self, barber_id: int, slot_datetime: str, exclude_booking_id: int | None = None
    ) -> bool:
        """True if the barber already has an active booking at this exact slot."""
        cur = await self.conn.execute(
            """
            SELECT 1 FROM bookings
            WHERE barber_id = ? AND slot_datetime = ?
              AND status IN ('pending', 'confirmed')
              AND id != ?
            LIMIT 1
            """,
            (barber_id, slot_datetime, exclude_booking_id or -1),
        )
        return await cur.fetchone() is not None

    async def get_free_slots(self, barber_id: int, date: datetime.date) -> list[str]:
        """Slots the barber works on `date` that are neither booked nor already past."""
        if date.weekday() not in await self.get_barber_weekdays(barber_id):
            return []
        if date.isoformat() in await self.get_barber_days_off(barber_id):
            return []
        booked = set(await self.get_booked_slots(barber_id, date.isoformat()))
        slots = [s for s in await self.get_barber_time_slots(barber_id) if s not in booked]
        now = local_now()
        if date < now.date():
            return []
        if date == now.date():
            now_time = now.strftime("%H:%M")
            slots = [s for s in slots if s > now_time]
        return slots

    # ── Schedule ──────────────────────────────────────────────────────────────

    async def get_barber_weekdays(self, barber_id: int) -> list[int]:
        """Return list of weekday integers (0-6) the barber works."""
        cur = await self.conn.execute(
            "SELECT weekday FROM barber_schedule WHERE barber_id = ? ORDER BY weekday",
            (barber_id,),
        )
        rows = await cur.fetchall()
        if not rows:
            return list(DEFAULT_WORKDAYS)
        return [row["weekday"] for row in rows]

    async def set_barber_weekdays(
        self, barber_id: int, weekdays: list[int]
    ) -> None:
        """Replace the barber's weekly schedule."""
        await self.conn.execute(
            "DELETE FROM barber_schedule WHERE barber_id = ?", (barber_id,)
        )
        await self.conn.executemany(
            "INSERT INTO barber_schedule (barber_id, weekday) VALUES (?, ?)",
            [(barber_id, w) for w in weekdays],
        )
        await self.conn.commit()

    async def get_barber_time_slots(self, barber_id: int) -> list[str]:
        """Return list of slot times (HH:MM) for the barber."""
        cur = await self.conn.execute(
            "SELECT slot_time FROM barber_time_slots WHERE barber_id = ? ORDER BY slot_time",
            (barber_id,),
        )
        rows = await cur.fetchall()
        if not rows:
            return list(TIME_SLOTS)
        return [row["slot_time"] for row in rows]

    async def set_barber_time_slots(
        self, barber_id: int, slots: list[str]
    ) -> None:
        """Replace the barber's time slots."""
        await self.conn.execute(
            "DELETE FROM barber_time_slots WHERE barber_id = ?", (barber_id,)
        )
        await self.conn.executemany(
            "INSERT INTO barber_time_slots (barber_id, slot_time) VALUES (?, ?)",
            [(barber_id, s) for s in slots],
        )
        await self.conn.commit()

    # ── Days off ──────────────────────────────────────────────────────────────

    async def get_barber_days_off(self, barber_id: int) -> list[str]:
        """Return list of date strings (YYYY-MM-DD) that are marked as days off."""
        cur = await self.conn.execute(
            "SELECT off_date FROM barber_days_off WHERE barber_id = ? ORDER BY off_date",
            (barber_id,),
        )
        rows = await cur.fetchall()
        return [row["off_date"] for row in rows]

    async def toggle_day_off(self, barber_id: int, date_str: str) -> bool:
        """Toggle a day off. Returns True if day was added, False if removed."""
        cur = await self.conn.execute(
            "SELECT id FROM barber_days_off WHERE barber_id = ? AND off_date = ?",
            (barber_id, date_str),
        )
        existing = await cur.fetchone()
        if existing:
            await self.conn.execute(
                "DELETE FROM barber_days_off WHERE barber_id = ? AND off_date = ?",
                (barber_id, date_str),
            )
            await self.conn.commit()
            return False
        else:
            await self.conn.execute(
                "INSERT OR IGNORE INTO barber_days_off (barber_id, off_date) VALUES (?, ?)",
                (barber_id, date_str),
            )
            await self.conn.commit()
            return True

    async def get_available_dates(
        self, barber_id: int, days_ahead: int = 14
    ) -> list[datetime.date]:
        """
        Return a list of dates (today + next `days_ahead` days) when the barber
        works, is not on a day off and still has at least one free slot.
        """
        today = local_today()
        result: list[datetime.date] = []
        for offset in range(0, days_ahead + 1):
            candidate = today + datetime.timedelta(days=offset)
            if await self.get_free_slots(barber_id, candidate):
                result.append(candidate)
        return result


# Singleton instance
db: Database = Database(settings.db_path)
