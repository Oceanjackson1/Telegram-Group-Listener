"""Progress feedback utility for Telegram bot long-running operations."""

from __future__ import annotations

import logging
import time
from typing import Optional, Union

from telegram import Bot, Message

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

_BAR_FILLED = "\u2588"      # █
_BAR_EMPTY = "\u2591"       # ░
_BAR_LENGTH = 10
_MIN_EDIT_INTERVAL = 2.0    # seconds between edits (Telegram rate-limit safety)


def _render_bar(fraction: float) -> str:
    """Render a text-based progress bar from 0.0 to 1.0."""
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * _BAR_LENGTH)
    empty = _BAR_LENGTH - filled
    pct = round(fraction * 100)
    return f"[{_BAR_FILLED * filled}{_BAR_EMPTY * empty}] {pct}%"


class ProgressTracker:
    """Async context manager that shows and updates a progress message in Telegram.

    Determinate mode (with percentage):
        async with ProgressTracker(bot, chat_id, i18n, lang, "progress_parsing_file") as pt:
            await pt.update(0.3, step_key="progress_downloading_file")
            ...
            await pt.update(0.8, step_key="progress_storing_chunks")

    Indeterminate mode (no percentage):
        async with ProgressTracker(bot, chat_id, i18n, lang, "progress_drawing_winners", determinate=False):
            ...

    On exit the progress message is deleted (default) or replaced via finish_with_text().
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: Union[int, str],
        i18n,
        language: str,
        task_key: str,
        determinate: bool = True,
        reply_to_message_id: Optional[int] = None,
        delete_on_finish: bool = True,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._i18n = i18n
        self._language = language
        self._task_key = task_key
        self._determinate = determinate
        self._reply_to = reply_to_message_id
        self._delete_on_finish = delete_on_finish

        self._message: Optional[Message] = None
        self._last_edit_time: float = 0.0
        self._last_text: str = ""
        self._current_fraction: float = 0.0

    # ── helpers ──────────────────────────────────────────────────────────

    def _t(self, key: str, **kwargs) -> str:
        if self._i18n:
            return self._i18n.t(self._language, key, **kwargs)
        return key

    def _build_text(self, fraction: float = 0.0, step_key: Optional[str] = None) -> str:
        task_desc = self._t(self._task_key)
        if self._determinate:
            bar = _render_bar(fraction)
            lines = [f"\u23f3 {task_desc}", bar]
        else:
            lines = [f"\u23f3 {task_desc}..."]

        if step_key:
            step_desc = self._t(step_key)
            lines.append(f"\u25b8 {step_desc}")  # ▸

        return "\n".join(lines)

    # ── context manager ──────────────────────────────────────────────────

    async def __aenter__(self) -> "ProgressTracker":
        text = self._build_text(0.0)
        self._last_text = text
        try:
            self._message = await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                reply_to_message_id=self._reply_to,
            )
            self._last_edit_time = time.monotonic()
        except Exception:
            logger.warning("ProgressTracker: failed to send initial message", exc_info=True)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._message is None:
            return False
        try:
            if self._delete_on_finish:
                await self._message.delete()
            else:
                final_text = self._build_text(1.0)
                if final_text != self._last_text:
                    await self._message.edit_text(final_text)
        except Exception:
            logger.debug("ProgressTracker: cleanup failed", exc_info=True)
        return False  # do not suppress exceptions

    # ── public API ───────────────────────────────────────────────────────

    async def update(
        self,
        fraction: Optional[float] = None,
        step_key: Optional[str] = None,
    ) -> None:
        """Update the progress message (rate-limited to avoid Telegram 429)."""
        if self._message is None:
            return

        now = time.monotonic()
        if now - self._last_edit_time < _MIN_EDIT_INTERVAL:
            return

        if fraction is not None:
            self._current_fraction = fraction

        text = self._build_text(self._current_fraction, step_key)
        if text == self._last_text:
            return

        try:
            await self._message.edit_text(text)
            self._last_text = text
            self._last_edit_time = now
        except Exception:
            logger.debug("ProgressTracker: edit_text failed", exc_info=True)

    async def finish_with_text(self, text: str) -> None:
        """Replace the progress message with final result text instead of deleting."""
        if self._message is None:
            return
        try:
            await self._message.edit_text(text)
            self._delete_on_finish = False
            self._message = None  # prevent further edits in __aexit__
        except Exception:
            logger.debug("ProgressTracker: finish_with_text failed", exc_info=True)
