"""Group manager — register groups, check bot permissions, manage admins."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from utils.database import Database

logger = logging.getLogger(__name__)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


class GroupManager:
    def __init__(self, db: Database) -> None:
        self._db = db

    # -- group registration --------------------------------------------------

    def register_group(self, chat_id: int | str, chat_title: str, added_by: int, language: str = "en") -> None:
        existing = self._db.fetchone("SELECT chat_id FROM groups WHERE chat_id = ?", (str(chat_id),))
        now = _now_utc()
        if existing:
            self._db.execute(
                "UPDATE groups SET chat_title = ?, updated_at = ? WHERE chat_id = ?",
                (chat_title, now, str(chat_id)),
            )
        else:
            self._db.execute(
                "INSERT INTO groups (chat_id, chat_title, added_by, language, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(chat_id), chat_title, added_by, language, now, now),
            )
        # Make the adder an owner
        self._db.execute(
            "INSERT OR REPLACE INTO group_admins (chat_id, user_id, role) VALUES (?, ?, ?)",
            (str(chat_id), added_by, "owner"),
        )
        self._db.commit()

    def remove_group(self, chat_id: int | str) -> None:
        cid = str(chat_id)
        self._db.execute("DELETE FROM groups WHERE chat_id = ?", (cid,))
        self._db.execute("DELETE FROM group_admins WHERE chat_id = ?", (cid,))
        self._db.commit()

    def get_group(self, chat_id: int | str) -> dict | None:
        return self._db.fetchone("SELECT * FROM groups WHERE chat_id = ?", (str(chat_id),))

    def get_user_groups(self, user_id: int) -> list[dict]:
        rows = self._db.fetchall(
            "SELECT g.* FROM groups g JOIN group_admins ga ON g.chat_id = ga.chat_id WHERE ga.user_id = ?",
            (user_id,),
        )
        return rows

    # -- admin management ----------------------------------------------------

    def add_admin(self, chat_id: int | str, user_id: int, role: str = "admin") -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO group_admins (chat_id, user_id, role) VALUES (?, ?, ?)",
            (str(chat_id), user_id, role),
        )
        self._db.commit()

    def remove_admin(self, chat_id: int | str, user_id: int) -> None:
        self._db.execute(
            "DELETE FROM group_admins WHERE chat_id = ? AND user_id = ?",
            (str(chat_id), user_id),
        )
        self._db.commit()

    def is_admin(self, chat_id: int | str, user_id: int) -> bool:
        row = self._db.fetchone(
            "SELECT 1 FROM group_admins WHERE chat_id = ? AND user_id = ?",
            (str(chat_id), user_id),
        )
        return row is not None

    def get_admins(self, chat_id: int | str) -> list[dict]:
        return self._db.fetchall(
            "SELECT * FROM group_admins WHERE chat_id = ?", (str(chat_id),)
        )

    # -- language helpers ----------------------------------------------------

    def get_group_language(self, chat_id: int | str) -> str:
        row = self._db.fetchone("SELECT language FROM groups WHERE chat_id = ?", (str(chat_id),))
        lang = row.get("language", "en") if row else "en"
        return lang if lang in {"en", "zh"} else "en"

    def set_group_language(self, chat_id: int | str, language: str) -> None:
        lang = language if language in {"en", "zh"} else "en"
        self._db.execute(
            "UPDATE groups SET language = ?, updated_at = ? WHERE chat_id = ?",
            (lang, _now_utc(), str(chat_id)),
        )
        self._db.commit()
