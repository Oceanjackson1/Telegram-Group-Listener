"""AI chat engine — prompt building, conversation memory, DeepSeek integration."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from services.deepseek import call_deepseek
from services.knowledge import has_knowledge, retrieve_context

logger = logging.getLogger(__name__)

# Conversation memory: {chat_id: {user_id: [{"role": ..., "content": ..., "ts": ...}]}}
_chat_memory: dict[str, dict[int, list[dict]]] = {}

MEMORY_MAX_ROUNDS = 5  # max 5 rounds per user
MEMORY_TTL = 1800  # 30 minutes


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _get_history(chat_id: str, user_id: int) -> list[dict]:
    """Get conversation history for a user in a chat, pruning old entries."""
    if chat_id not in _chat_memory:
        _chat_memory[chat_id] = {}

    history = _chat_memory[chat_id].get(user_id, [])
    now = time.time()
    # Prune old entries
    history = [h for h in history if now - h.get("ts", 0) < MEMORY_TTL]
    # Keep only last N rounds (2 messages per round)
    history = history[-(MEMORY_MAX_ROUNDS * 2):]
    _chat_memory[chat_id][user_id] = history

    return [{"role": h["role"], "content": h["content"]} for h in history]


def _add_to_history(chat_id: str, user_id: int, role: str, content: str) -> None:
    if chat_id not in _chat_memory:
        _chat_memory[chat_id] = {}
    history = _chat_memory[chat_id].setdefault(user_id, [])
    history.append({"role": role, "content": content, "ts": time.time()})
    # Keep bounded
    if len(history) > MEMORY_MAX_ROUNDS * 2:
        _chat_memory[chat_id][user_id] = history[-(MEMORY_MAX_ROUNDS * 2):]


async def get_ai_response(
    db,
    chat_id: str,
    user_id: int,
    question: str,
    api_key: str,
) -> dict | None:
    """Get AI response for a user question. Returns dict with 'content' + usage stats, or None if AI is disabled."""

    # Check AI config
    ai_cfg = db.fetchone("SELECT * FROM ai_config WHERE chat_id = ? AND enabled = 1", (chat_id,))
    if not ai_cfg:
        return None

    # Check if knowledge base exists
    if not has_knowledge(db, chat_id):
        return None

    system_prompt = ai_cfg.get("system_prompt", "You are a friendly community assistant.")
    temperature = ai_cfg.get("temperature", 0.7)
    max_tokens = ai_cfg.get("max_tokens", 1024)

    # Retrieve relevant knowledge
    knowledge_context = retrieve_context(db, chat_id, question, top_k=5)

    # Get conversation history
    chat_history = _get_history(chat_id, user_id)

    # Call DeepSeek
    result = await call_deepseek(
        system_prompt=system_prompt,
        knowledge_context=knowledge_context,
        chat_history=chat_history,
        user_question=question,
        api_key=api_key,
        chat_id=chat_id,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Update memory
    _add_to_history(chat_id, user_id, "user", question)
    _add_to_history(chat_id, user_id, "assistant", result["content"])

    # Log usage
    db.execute(
        "INSERT INTO ai_usage_log (chat_id, user_id, question, answer, prompt_tokens, completion_tokens, total_tokens, latency_ms, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            chat_id, user_id, question[:500], result["content"][:500],
            result["prompt_tokens"], result["completion_tokens"],
            result["total_tokens"], result["latency_ms"], _now_utc(),
        ),
    )
    db.commit()

    return result


def should_ai_respond(db, chat_id: str, text: str, is_mention: bool, is_ask_command: bool) -> bool:
    """Determine if the AI should respond to this message."""
    if is_ask_command or is_mention:
        return True

    ai_cfg = db.fetchone("SELECT * FROM ai_config WHERE chat_id = ? AND enabled = 1", (chat_id,))
    if not ai_cfg:
        return False

    trigger_mode = ai_cfg.get("trigger_mode", "all")

    if trigger_mode == "all":
        # Check if message looks like a question
        question_indicators = ["?", "？", "how", "what", "why", "when", "where", "who",
                               "吗", "怎么", "什么", "为什么", "如何", "哪", "几",
                               "请问", "想问", "能告诉"]
        text_lower = text.lower()
        return any(q in text_lower for q in question_indicators)

    if trigger_mode == "mention":
        return is_mention

    if trigger_mode == "keyword":
        import json
        keywords = json.loads(ai_cfg.get("trigger_keywords", "[]"))
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in keywords)

    return False
