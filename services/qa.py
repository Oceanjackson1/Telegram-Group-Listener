"""Q&A matching engine with cooldown."""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# Cooldown tracker: {(chat_id, rule_id): last_triggered_ts}
_cooldowns: dict[tuple[str, int], float] = {}


def find_matching_rule(db, chat_id: str, text: str) -> dict | None:
    """Find the first matching Q&A rule for the given message text."""
    rules = db.fetchall(
        "SELECT * FROM qa_rules WHERE chat_id = ? AND enabled = 1 ORDER BY id",
        (chat_id,),
    )
    if not rules:
        return None

    text_lower = text.lower()
    now = time.time()

    for rule in rules:
        trigger = rule["trigger_text"]
        match_mode = rule.get("match_mode", "fuzzy")

        matched = False
        if match_mode == "exact":
            matched = text_lower.strip() == trigger.lower().strip()
        else:
            matched = trigger.lower() in text_lower

        if not matched:
            continue

        # Check cooldown
        cooldown_key = (chat_id, rule["id"])
        cooldown_sec = rule.get("cooldown_sec", 30)
        last_time = _cooldowns.get(cooldown_key, 0)
        if now - last_time < cooldown_sec:
            continue

        _cooldowns[cooldown_key] = now
        return rule

    return None
