"""DeepSeek API client with retry and rate limiting."""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

logger = logging.getLogger(__name__)

_semaphore = asyncio.Semaphore(5)

# Rate limiter: {chat_id: [timestamps]}
_rate_tracker: dict[str, list[float]] = {}
_RATE_LIMIT = 10  # per minute per group


def _check_rate_limit(chat_id: str) -> bool:
    """Returns True if within rate limit."""
    now = time.time()
    if chat_id not in _rate_tracker:
        _rate_tracker[chat_id] = []

    _rate_tracker[chat_id] = [t for t in _rate_tracker[chat_id] if now - t < 60]
    if len(_rate_tracker[chat_id]) >= _RATE_LIMIT:
        return False

    _rate_tracker[chat_id].append(now)
    return True


async def call_deepseek(
    system_prompt: str,
    knowledge_context: str,
    chat_history: list[dict],
    user_question: str,
    api_key: str,
    chat_id: str = "",
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> dict:
    """Call DeepSeek API. Returns dict with 'content', 'prompt_tokens', 'completion_tokens', 'total_tokens', 'latency_ms'."""

    if chat_id and not _check_rate_limit(chat_id):
        return {
            "content": "⏳ Rate limit reached. Please try again in a moment.",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "latency_ms": 0,
        }

    system_content = system_prompt
    if knowledge_context:
        system_content += (
            "\n\nBelow is your knowledge base. Answer user questions based on this content. "
            "If the answer is not in the knowledge base, say you're not sure but try to be helpful.\n"
            "---\n" + knowledge_context[:6000] + "\n---"
        )

    messages = [
        {"role": "system", "content": system_content},
        *chat_history[-10:],  # Keep last 5 rounds (10 messages)
        {"role": "user", "content": user_question},
    ]

    start_ms = time.time() * 1000

    for attempt in range(1, 4):
        try:
            async with _semaphore:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        "https://api.deepseek.com/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={
                            "model": "deepseek-chat",
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                        },
                    )

            if response.status_code == 200:
                data = response.json()
                latency = int(time.time() * 1000 - start_ms)
                usage = data.get("usage", {})
                content = data["choices"][0]["message"]["content"]
                return {
                    "content": content,
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "latency_ms": latency,
                }
            else:
                logger.error("DeepSeek API error (attempt %d): %d %s", attempt, response.status_code, response.text[:200])

        except Exception as exc:
            logger.exception("DeepSeek API call failed (attempt %d): %s", attempt, exc)

        if attempt < 3:
            await asyncio.sleep(1)

    return {
        "content": "Sorry, I'm unable to respond right now. Please try again later.",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "latency_ms": int(time.time() * 1000 - start_ms),
    }
