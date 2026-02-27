"""Q&A handler for group messages + /faq command."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from services.qa import find_matching_rule

logger = logging.getLogger(__name__)


async def qa_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check group messages against Q&A rules."""
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
    rule = find_matching_rule(db, chat_id, text)
    if not rule:
        return

    reply_mode = rule.get("reply_mode", "reply")
    response = rule["response_text"]

    try:
        if reply_mode == "quote":
            await message.reply_text(response, quote=True)
        elif reply_mode == "dm":
            await context.bot.send_message(chat_id=message.from_user.id, text=response)
        else:
            await message.reply_text(response)
    except Exception as exc:
        logger.exception("Q&A reply failed: %s", exc)


async def faq_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all Q&A rules for the current group."""
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

    rules = db.fetchall(
        "SELECT trigger_text, response_text FROM qa_rules WHERE chat_id = ? AND enabled = 1 ORDER BY id",
        (chat_id,),
    )

    if not rules:
        await message.reply_text(i18n.t(language, "faq_empty") if i18n else "No FAQ entries yet.")
        return

    lines = []
    for i, r in enumerate(rules, 1):
        lines.append(f"**Q{i}:** {r['trigger_text']}\n**A:** {r['response_text']}")

    await message.reply_text("\n\n".join(lines))
