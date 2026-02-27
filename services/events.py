"""Events & giveaway service — CRUD, lottery draw."""
from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def join_event(db, event_id: int, user_id: int, username: str | None, display_name: str | None) -> bool:
    """Add a user to an event. Returns True if newly joined, False if already joined."""
    existing = db.fetchone(
        "SELECT 1 FROM event_participants WHERE event_id = ? AND user_id = ?",
        (event_id, user_id),
    )
    if existing:
        return False

    db.execute(
        "INSERT INTO event_participants (event_id, user_id, username, display_name, joined_at) VALUES (?, ?, ?, ?, ?)",
        (event_id, user_id, username, display_name, _now_utc()),
    )
    db.commit()
    return True


def get_participant_count(db, event_id: int) -> int:
    row = db.fetchone("SELECT COUNT(*) as cnt FROM event_participants WHERE event_id = ?", (event_id,))
    return row["cnt"] if row else 0


def draw_winners(db, event_id: int) -> list[dict]:
    """Draw random winners for an event. Returns list of winner dicts."""
    event = db.fetchone("SELECT * FROM events WHERE id = ?", (event_id,))
    if not event or event["status"] != "active":
        return []

    participants = db.fetchall(
        "SELECT * FROM event_participants WHERE event_id = ?", (event_id,)
    )
    if not participants:
        return []

    winner_count = min(event.get("winner_count", 1), len(participants))
    winners = random.sample(participants, winner_count)

    db.execute(
        "UPDATE events SET status = 'drawn', drawn_at = ? WHERE id = ?",
        (_now_utc(), event_id),
    )
    db.commit()
    return winners


def get_active_events(db, chat_id: str) -> list[dict]:
    return db.fetchall(
        "SELECT * FROM events WHERE chat_id = ? AND status = 'active' ORDER BY id",
        (chat_id,),
    )
