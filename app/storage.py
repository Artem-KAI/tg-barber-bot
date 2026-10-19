"""SQLite-backed FSM storage, so conversations survive bot restarts."""
from __future__ import annotations

import json
from typing import Any, Mapping

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

from app.db import Database

__all__ = ["SQLiteStorage"]


class SQLiteStorage(BaseStorage):
    """Stores FSM state and data in the bot's own SQLite database."""

    def __init__(self, database: Database) -> None:
        self._db = database

    @staticmethod
    def _key(key: StorageKey) -> str:
        return ":".join(
            str(part)
            for part in (
                key.bot_id,
                key.chat_id,
                key.user_id,
                key.thread_id or "",
                key.business_connection_id or "",
                key.destiny,
            )
        )

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        await self._db.fsm_set_state(self._key(key), value)

    async def get_state(self, key: StorageKey) -> str | None:
        row = await self._db.fsm_get(self._key(key))
        return row["state"] if row else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        await self._db.fsm_set_data(self._key(key), json.dumps(dict(data)))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        row = await self._db.fsm_get(self._key(key))
        if not row or not row["data"]:
            return {}
        return json.loads(row["data"])

    async def close(self) -> None:
        # The database connection is owned and closed by main()
        pass
