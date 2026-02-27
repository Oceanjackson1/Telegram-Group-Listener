"""Start handler — /start sends feature overview + action buttons."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from handlers.config import LANG_SELECT, MONITOR_TYPE, prompt_monitor_type_step


def _build_start_keyboard(i18n, language: str) -> InlineKeyboardMarkup:
    """Build the 2-column 6-button welcome screen keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(i18n.t(language, "start_btn_monitor"),   callback_data="sa:config"),
            InlineKeyboardButton(i18n.t(language, "start_btn_status"),    callback_data="sa:status"),
        ],
        [
            InlineKeyboardButton(i18n.t(language, "start_btn_community"), callback_data="sa:admin"),
            InlineKeyboardButton(i18n.t(language, "start_btn_ai"),        callback_data="sa:ai"),
        ],
        [
            InlineKeyboardButton(i18n.t(language, "start_btn_events"),    callback_data="sa:events"),
            InlineKeyboardButton(i18n.t(language, "start_btn_lang"),      callback_data="sa:lang"),
        ],
    ])


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return ConversationHandler.END

    store = context.application.bot_data["config_store"]
    i18n = context.application.bot_data["i18n"]

    language = store.get_language(update.effective_user.id)
    if update.effective_chat.type != "private":
        await update.message.reply_text(i18n.t(language, "dm_only"))
        return ConversationHandler.END

    await update.message.reply_text(
        i18n.t(language, "start_welcome"),
        reply_markup=_build_start_keyboard(i18n, language),
    )
    return LANG_SELECT


async def start_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle action buttons from the /start overview."""
    query = update.callback_query
    if not query:
        return LANG_SELECT

    await query.answer()

    store = context.application.bot_data["config_store"]
    i18n = context.application.bot_data["i18n"]
    language = store.get_language(query.from_user.id)
    action = query.data.split(":", 1)[1]

    if action == "config":
        # Enter monitoring configuration flow
        context.user_data["draft_config"] = {}
        await query.edit_message_text(i18n.t(language, "start_welcome"))
        await prompt_monitor_type_step(query.from_user.id, context, language)
        return MONITOR_TYPE

    if action == "status":
        await query.edit_message_text(i18n.t(language, "start_status_hint"))
        return ConversationHandler.END

    if action == "admin":
        # Cannot enter admin_flow from here; guide user to type /admin
        await query.edit_message_text(i18n.t(language, "start_welcome"))
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=i18n.t(language, "start_admin_hint"),
        )
        return ConversationHandler.END

    if action == "ai":
        await query.edit_message_text(i18n.t(language, "start_ai_hint"))
        return ConversationHandler.END

    if action == "events":
        await query.edit_message_text(i18n.t(language, "start_events_hint"))
        return ConversationHandler.END

    if action == "lang":
        # Show language selection
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(i18n.t("en", "btn_english"), callback_data="set_lang:en"),
                InlineKeyboardButton(i18n.t("en", "btn_chinese"), callback_data="set_lang:zh"),
            ]
        ])
        await query.edit_message_text(i18n.t(language, "choose_language"), reply_markup=keyboard)
        return LANG_SELECT

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

    # After language switch, show the full start overview in the new language
    await query.edit_message_text(
        i18n.t(selected_language, "language_selected") + "\n\n" + i18n.t(selected_language, "start_welcome"),
        reply_markup=_build_start_keyboard(i18n, selected_language),
    )
    return LANG_SELECT
