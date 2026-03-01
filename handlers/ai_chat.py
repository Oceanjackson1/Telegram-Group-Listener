"""AI chat handler — @Bot replies, /ask command, proactive answering."""

import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

from services.ai_chat import get_ai_response, should_ai_respond
from utils.progress import ProgressTracker

logger = logging.getLogger(__name__)


async def ai_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle AI responses in group chats."""
    message = update.effective_message
    if not message or not message.from_user or not message.chat:
        return

    if message.chat.type not in {"group", "supergroup"}:
        return

    if message.from_user.id == context.bot.id:
        return

    text = message.text or message.caption or ""
    if not text:
        return

    db = context.application.bot_data.get("db")
    if not db:
        return

    chat_id = str(message.chat.id)
    bot_username = context.bot.username or ""

    # Detect if bot is mentioned
    is_mention = False
    if bot_username:
        is_mention = f"@{bot_username}" in text
        text_cleaned = text.replace(f"@{bot_username}", "").strip()
    else:
        text_cleaned = text

    is_ask_command = False  # /ask is handled separately

    if not should_ai_respond(db, chat_id, text, is_mention, is_ask_command):
        return

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return

    i18n = context.application.bot_data.get("i18n")
    gm = context.application.bot_data.get("group_manager")
    language = gm.get_group_language(chat_id) if gm else "en"

    try:
        async with ProgressTracker(
            bot=context.bot,
            chat_id=message.chat.id,
            i18n=i18n,
            language=language,
            task_key="progress_ai_thinking",
            reply_to_message_id=message.message_id,
        ) as pt:
            await pt.update(0.2, step_key="progress_ai_retrieving")
            result = await get_ai_response(
                db=db,
                chat_id=chat_id,
                user_id=message.from_user.id,
                question=text_cleaned if is_mention else text,
                api_key=api_key,
            )
            await pt.update(0.9, step_key="progress_ai_generating")

        if result and result.get("content"):
            await message.reply_text(result["content"], quote=True)

    except Exception as exc:
        logger.exception("AI chat response failed: %s", exc)


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ask <question> command."""
    message = update.effective_message
    if not message or not message.chat:
        return

    db = context.application.bot_data.get("db")
    if not db:
        return

    i18n = context.application.bot_data.get("i18n")
    chat_id = str(message.chat.id)
    gm = context.application.bot_data.get("group_manager")
    language = gm.get_group_language(chat_id) if gm else "en"

    # Extract question from /ask <question>
    text = message.text or ""
    question = text.replace("/ask", "", 1).strip()
    if not question:
        await message.reply_text(i18n.t(language, "ask_usage") if i18n else "Usage: /ask <your question>")
        return

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        await message.reply_text(i18n.t(language, "ai_not_configured") if i18n else "AI is not configured.")
        return

    try:
        async with ProgressTracker(
            bot=context.bot,
            chat_id=message.chat.id,
            i18n=i18n,
            language=language,
            task_key="progress_ai_thinking",
            reply_to_message_id=message.message_id,
        ) as pt:
            await pt.update(0.2, step_key="progress_ai_retrieving")
            result = await get_ai_response(
                db=db,
                chat_id=chat_id,
                user_id=message.from_user.id,
                question=question,
                api_key=api_key,
            )
            await pt.update(0.9, step_key="progress_ai_generating")

        if result and result.get("content"):
            await message.reply_text(result["content"], quote=True)
        else:
            await message.reply_text(
                i18n.t(language, "ai_no_knowledge") if i18n else "No knowledge base is configured for this group."
            )

    except Exception as exc:
        logger.exception("AI /ask command failed: %s", exc)
        await message.reply_text(
            i18n.t(language, "ai_error") if i18n else "Sorry, something went wrong. Please try again."
        )
