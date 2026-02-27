"""Anti-spam group message handler."""

import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from services.antispam import check_spam, log_moderation

logger = logging.getLogger(__name__)


async def antispam_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check incoming group messages for spam. Runs at highest priority (group=0)."""
    message = update.effective_message
    if not message or not message.from_user or not message.chat:
        return

    # Only process group messages
    if message.chat.type not in {"group", "supergroup"}:
        return

    # Skip bot's own messages
    if message.from_user.id == context.bot.id:
        return

    text = message.text or message.caption or ""
    if not text:
        return

    db = context.application.bot_data.get("db")
    if not db:
        return

    chat_id = str(message.chat.id)
    user_id = message.from_user.id
    username = message.from_user.username

    result = check_spam(db, chat_id, user_id, username, text)
    if not result:
        return

    action = result["action"]
    reason = result["reason"]
    i18n = context.application.bot_data.get("i18n")

    # Log the moderation action
    log_moderation(db, chat_id, user_id, action, reason, text)

    try:
        # Delete the message
        await message.delete()

        if "warn" in action and i18n:
            gm = context.application.bot_data.get("group_manager")
            language = gm.get_group_language(chat_id) if gm else "en"
            user_display = f"@{username}" if username else str(user_id)
            warning = i18n.t(language, "spam_warning", user=user_display, reason=reason)
            await context.bot.send_message(chat_id=int(chat_id), text=warning)

        if "mute" in action:
            from datetime import datetime, timedelta, timezone
            until = datetime.now(timezone.utc) + timedelta(hours=1)
            from telegram import ChatPermissions
            await context.bot.restrict_chat_member(
                chat_id=int(chat_id),
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )

        if "kick" in action:
            await context.bot.ban_chat_member(chat_id=int(chat_id), user_id=user_id)

    except Exception as exc:
        logger.exception("Anti-spam action failed for chat %s user %s: %s", chat_id, user_id, exc)
