"""Anti-spam detection engine."""
from __future__ import annotations

import json
import logging
import re
import time

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r'https?://\S+|www\.\S+', re.IGNORECASE)

# In-memory message history for repeat detection: {chat_id: {user_id: [(text, ts)]}}
_recent_messages: dict[str, dict[int, list[tuple[str, float]]]] = {}


def check_spam(db, chat_id: str, user_id: int, username: str | None, text: str) -> dict | None:
    """Check if a message is spam. Returns action dict or None if clean."""
    cfg = db.fetchone("SELECT * FROM spam_config WHERE chat_id = ? AND enabled = 1", (chat_id,))
    if not cfg:
        return None

    # Check whitelist
    whitelist = json.loads(cfg.get("whitelist_users") or "[]")
    if str(user_id) in whitelist or (username and username.lower() in [w.lower() for w in whitelist]):
        return None

    punishment = cfg.get("punishment", "delete_warn")

    # Check keyword blacklist
    blacklist = json.loads(cfg.get("keyword_blacklist") or "[]")
    text_lower = text.lower()
    for kw in blacklist:
        if kw.lower() in text_lower:
            return {"action": punishment, "reason": f"blacklist keyword: {kw}"}

    # Check link filter
    if cfg.get("link_filter"):
        urls = URL_PATTERN.findall(text)
        if urls:
            link_whitelist = json.loads(cfg.get("link_whitelist") or "[]")
            for url in urls:
                allowed = False
                for domain in link_whitelist:
                    if domain.lower() in url.lower():
                        allowed = True
                        break
                if not allowed:
                    return {"action": punishment, "reason": f"blocked link: {url}"}

    # Repeat message detection
    if cfg.get("repeat_detect"):
        window = cfg.get("repeat_window_sec", 60)
        threshold = cfg.get("repeat_threshold", 3)
        now = time.time()

        if chat_id not in _recent_messages:
            _recent_messages[chat_id] = {}
        user_history = _recent_messages[chat_id].setdefault(user_id, [])

        # Clean old entries
        user_history[:] = [(t, ts) for t, ts in user_history if now - ts < window]
        user_history.append((text_lower, now))

        count = sum(1 for t, _ in user_history if t == text_lower)
        if count >= threshold:
            user_history.clear()
            return {"action": punishment, "reason": "repeat message"}

    return None


def log_moderation(db, chat_id: str, user_id: int, action: str, reason: str, message_text: str) -> None:
    """Log a moderation action."""
    from datetime import datetime, timezone
    db.execute(
        "INSERT INTO moderation_log (chat_id, user_id, action, reason, message_text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (chat_id, user_id, action, reason, message_text[:500],
         datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")),
    )
    db.commit()
