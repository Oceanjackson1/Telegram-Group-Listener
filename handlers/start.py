from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from handlers.config import LANG_SELECT, MONITOR_TYPE, prompt_monitor_type_step


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return ConversationHandler.END

    store = context.application.bot_data["config_store"]
    i18n = context.application.bot_data["i18n"]

    language = store.get_language(update.effective_user.id)
    if update.effective_chat.type != "private":
        await update.message.reply_text(i18n.t(language, "dm_only"))
        return ConversationHandler.END

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(i18n.t("en", "btn_english"), callback_data="set_lang:en"),
                InlineKeyboardButton(i18n.t("en", "btn_chinese"), callback_data="set_lang:zh"),
            ]
        ]
    )

    context.user_data["draft_config"] = {}

    await update.message.reply_text(i18n.t("en", "start_welcome"), reply_markup=keyboard)
    return LANG_SELECT


async def language_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return LANG_SELECT

    await query.answer()

    store = context.application.bot_data["config_store"]
    i18n = context.application.bot_data["i18n"]

    selected_language = query.data.split(":", 1)[1]
    store.set_language(query.from_user.id, selected_language)

    await query.edit_message_text(i18n.t(selected_language, "language_selected"))
    context.user_data["draft_config"] = {}
    await prompt_monitor_type_step(query.from_user.id, context, selected_language)

    return MONITOR_TYPE
