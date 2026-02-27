"""Community services — welcome messages, proxy send."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_welcome_config(db, chat_id: str) -> dict | None:
    """Get welcome config for a group. Returns None if disabled."""
    cfg = db.fetchone("SELECT * FROM chat_config WHERE chat_id = ? AND welcome_enabled = 1", (chat_id,))
    return cfg


def format_welcome(template: str, user_name: str, group_title: str) -> str:
    """Format a welcome message template with user variables."""
    try:
        return template.format(name=user_name, group=group_title)
    except (KeyError, IndexError):
        return template.replace("{name}", user_name).replace("{group}", group_title)
