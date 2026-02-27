"""Community handler — welcome messages, new member detection."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from services.community import format_welcome, get_welcome_config

logger = logging.getLogger(__name__)


async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message when new members join."""
    message = update.effective_message
    if not message or not message.new_chat_members:
        return

    if message.chat.type not in {"group", "supergroup"}:
        return

    db = context.application.bot_data.get("db")
    if not db:
        return

    chat_id = str(message.chat.id)
    cfg = get_welcome_config(db, chat_id)
    if not cfg or not cfg.get("welcome_message"):
        return

    template = cfg["welcome_message"]
    group_title = message.chat.title or ""

    for member in message.new_chat_members:
        if member.is_bot:
            # When OUR bot is added, register the group
            if member.id == context.bot.id:
                gm = context.application.bot_data.get("group_manager")
                if gm and message.from_user:
                    gm.register_group(
                        chat_id=message.chat.id,
                        chat_title=group_title,
                        added_by=message.from_user.id,
                    )
            continue

        user_name = member.full_name or member.username or str(member.id)
        welcome_text = format_welcome(template, user_name, group_title)

        try:
            await context.bot.send_message(chat_id=int(chat_id), text=welcome_text)
        except Exception as exc:
            logger.exception("Failed to send welcome message: %s", exc)


async def bot_added_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle bot being added to a group — auto-register the group."""
    change = update.my_chat_member
    if not change:
        return

    new_status = change.new_chat_member.status
    chat = change.chat

    if chat.type not in {"group", "supergroup"}:
        return

    gm = context.application.bot_data.get("group_manager")
    if not gm:
        return

    if new_status in {"member", "administrator"}:
        # Bot was added to the group
        gm.register_group(
            chat_id=chat.id,
            chat_title=chat.title or "",
            added_by=change.from_user.id if change.from_user else 0,
        )
        logger.info("Bot added to group %s (%s) by user %s", chat.id, chat.title, change.from_user.id if change.from_user else "unknown")

    elif new_status in {"left", "kicked", "banned"}:
        gm.remove_group(chat.id)
        logger.info("Bot removed from group %s (%s)", chat.id, chat.title)
