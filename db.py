from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DEFAULT_SERVICES, SEGMENTS


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    price_usd INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS barbers (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    bio TEXT NOT NULL DEFAULT '',
                    rating REAL NOT NULL DEFAULT 4.7,
                    segment TEXT NOT NULL DEFAULT 'standard',
                    price_min INTEGER NOT NULL DEFAULT 40,
                    price_max INTEGER NOT NULL DEFAULT 70,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS barber_services (
                    barber_id INTEGER NOT NULL,
                    service_id INTEGER NOT NULL,
                    price_usd INTEGER NOT NULL,
                    PRIMARY KEY (barber_id, service_id),
                    FOREIGN KEY (barber_id) REFERENCES barbers(user_id),
                    FOREIGN KEY (service_id) REFERENCES services(id)
                );

                CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    barber_id INTEGER NOT NULL,
                    service_id INTEGER NOT NULL,
                    client_name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    price_usd INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (barber_id) REFERENCES barbers(user_id),
                    FOREIGN KEY (service_id) REFERENCES services(id)
                );
                """
            )
            for code, title, price in DEFAULT_SERVICES:
                conn.execute(
                    """
                    INSERT INTO services (code, title, price_usd)
                    VALUES (?, ?, ?)
                    ON CONFLICT(code) DO NOTHING
                    """,
                    (code, title, price),
                )

    def get_services(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM services ORDER BY id"))

    def get_service(self, service_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM services WHERE id = ?",
                (service_id,),
            ).fetchone()

    def update_service_price(self, service_id: int, price_usd: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE services SET price_usd = ? WHERE id = ?",
                (price_usd, service_id),
            )

    def upsert_barber(
        self,
        user_id: int,
        name: str,
        bio: str,
        segment: str,
        status: str,
        rating: float = 4.7,
    ) -> None:
        spec = SEGMENTS[segment]
        now = utcnow()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO barbers (
                    user_id, name, bio, rating, segment,
                    price_min, price_max, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    name = excluded.name,
                    bio = excluded.bio,
                    segment = excluded.segment,
                    price_min = excluded.price_min,
                    price_max = excluded.price_max,
                    status = excluded.status
                """,
                (
                    user_id,
                    name,
                    bio,
                    rating,
                    segment,
                    spec["price_min"],
                    spec["price_max"],
                    status,
                    now,
                ),
            )
            self._attach_default_services(conn, user_id)

    def _attach_default_services(self, conn: sqlite3.Connection, barber_id: int) -> None:
        services = conn.execute("SELECT id, price_usd FROM services").fetchall()
        for service in services:
            conn.execute(
                """
                INSERT INTO barber_services (barber_id, service_id, price_usd)
                VALUES (?, ?, ?)
                ON CONFLICT(barber_id, service_id) DO NOTHING
                """,
                (barber_id, service["id"], service["price_usd"]),
            )

    def ensure_admin_barber(self, admin_id: int) -> None:
        if self.get_barber(admin_id):
            return
        self.upsert_barber(
            user_id=admin_id,
            name="Studio Admin",
            bio="Администратор студии. Принимает заявки и управляет барберами.",
            segment="premium",
            status="approved",
            rating=5.0,
        )

    def get_barber(self, user_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM barbers WHERE user_id = ?",
                (user_id,),
            ).fetchone()

    def list_barbers(self, status: str | None = None) -> list[sqlite3.Row]:
        with self.connect() as conn:
            if status:
                return list(
                    conn.execute(
                        "SELECT * FROM barbers WHERE status = ? ORDER BY rating DESC, name",
                        (status,),
                    )
                )
            return list(conn.execute("SELECT * FROM barbers ORDER BY status, rating DESC"))

    def approved_barbers(self) -> list[sqlite3.Row]:
        return self.list_barbers("approved")

    def set_barber_status(self, user_id: int, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE barbers SET status = ? WHERE user_id = ?",
                (status, user_id),
            )

    def update_barber(self, user_id: int, **fields: Any) -> None:
        if not fields:
            return
        if "segment" in fields and fields["segment"] in SEGMENTS:
            spec = SEGMENTS[fields["segment"]]
            fields.setdefault("price_min", spec["price_min"])
            fields.setdefault("price_max", spec["price_max"])
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [user_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE barbers SET {assignments} WHERE user_id = ?", values)

    def barber_services(self, barber_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT s.id, s.code, s.title, bs.price_usd
                    FROM barber_services bs
                    JOIN services s ON s.id = bs.service_id
                    WHERE bs.barber_id = ?
                    ORDER BY s.id
                    """,
                    (barber_id,),
                )
            )

    def set_barber_service_price(self, barber_id: int, service_id: int, price_usd: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE barber_services
                SET price_usd = ?
                WHERE barber_id = ? AND service_id = ?
                """,
                (price_usd, barber_id, service_id),
            )

    def service_price_for_barber(self, barber_id: int, service_id: int) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT price_usd FROM barber_services
                WHERE barber_id = ? AND service_id = ?
                """,
                (barber_id, service_id),
            ).fetchone()
            if row:
                return int(row["price_usd"])
            service = self.get_service(service_id)
            return int(service["price_usd"]) if service else 0

    def create_booking(
        self,
        client_id: int,
        barber_id: int,
        service_id: int,
        client_name: str,
        phone: str,
        price_usd: int,
    ) -> int:
        now = utcnow()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO bookings (
                    client_id, barber_id, service_id, client_name,
                    phone, price_usd, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (client_id, barber_id, service_id, client_name, phone, price_usd, now, now),
            )
            return int(cur.lastrowid)

    def get_booking(self, booking_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT
                    b.*,
                    s.title AS service_title,
                    br.name AS barber_name,
                    br.rating AS barber_rating
                FROM bookings b
                JOIN services s ON s.id = b.service_id
                JOIN barbers br ON br.user_id = b.barber_id
                WHERE b.id = ?
                """,
                (booking_id,),
            ).fetchone()

    def update_booking(self, booking_id: int, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = utcnow()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [booking_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE bookings SET {assignments} WHERE id = ?", values)

    def client_bookings(self, client_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT
                        b.*,
                        s.title AS service_title,
                        br.name AS barber_name
                    FROM bookings b
                    JOIN services s ON s.id = b.service_id
                    JOIN barbers br ON br.user_id = b.barber_id
                    WHERE b.client_id = ?
                    ORDER BY b.id DESC
                    LIMIT 15
                    """,
                    (client_id,),
                )
            )

    def barber_bookings(self, barber_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT
                        b.*,
                        s.title AS service_title
                    FROM bookings b
                    JOIN services s ON s.id = b.service_id
                    WHERE b.barber_id = ?
                    ORDER BY b.id DESC
                    LIMIT 20
                    """,
                    (barber_id,),
                )
            )

    def all_bookings(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT
                        b.*,
                        s.title AS service_title,
                        br.name AS barber_name
                    FROM bookings b
                    JOIN services s ON s.id = b.service_id
                    JOIN barbers br ON br.user_id = b.barber_id
                    ORDER BY b.id DESC
                    LIMIT 30
                    """
                )
            )
