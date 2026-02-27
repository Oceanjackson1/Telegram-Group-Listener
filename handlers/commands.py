from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from utils.formatters import build_summary_text


def _get_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    store = context.application.bot_data["config_store"]
    return store.get_language(update.effective_user.id)


def _has_person_monitor(config: dict) -> bool:
    return bool(config.get("source")) and bool(config.get("destination"))


def _has_keyword_monitor(config: dict) -> bool:
    return bool(config.get("keyword_source")) and bool(config.get("keyword_destination")) and bool(config.get("keywords"))


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    language = _get_language(update, context)
    i18n = context.application.bot_data["i18n"]
    store = context.application.bot_data["config_store"]

    config = store.get_user_config(update.effective_user.id)
    status_blocks: list[str] = []

    if _has_person_monitor(config):
        person_config = {
            "monitor_type": "person",
            "source": config.get("source", {}),
            "destination": config.get("destination", {}),
            "active": config.get("active", False),
        }
        status_blocks.append(
            build_summary_text(
                i18n,
                language,
                person_config,
                title_key="status_title_person",
                include_status=True,
            )
        )

    if _has_keyword_monitor(config):
        keyword_config = {
            "monitor_type": "keyword",
            "keyword_source": config.get("keyword_source", {}),
            "keyword_destination": config.get("keyword_destination", {}),
            "keywords": config.get("keywords", []),
            "keyword_active": config.get("keyword_active", False),
        }
        status_blocks.append(
            build_summary_text(
                i18n,
                language,
                keyword_config,
                title_key="status_title_keyword",
                include_status=True,
            )
        )

    if not status_blocks:
        await update.message.reply_text(i18n.t(language, "status_no_config"))
        return

    status_text = "\n\n".join(status_blocks)
    await update.message.reply_text(status_text)


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    language = _get_language(update, context)
    i18n = context.application.bot_data["i18n"]
    store = context.application.bot_data["config_store"]

    current = store.get_user_config(update.effective_user.id)
    has_person = _has_person_monitor(current)
    has_keyword = _has_keyword_monitor(current)
    if not has_person and not has_keyword:
        await update.message.reply_text(i18n.t(language, "status_no_config"))
        return

    updates = {}
    if has_person:
        updates["active"] = False
    if has_keyword:
        updates["keyword_active"] = False
    store.update_user_config(update.effective_user.id, updates)
    await update.message.reply_text(i18n.t(language, "stopped"))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    language = _get_language(update, context)
    i18n = context.application.bot_data["i18n"]
    await update.message.reply_text(i18n.t(language, "help_text"))


async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    language = _get_language(update, context)
    i18n = context.application.bot_data["i18n"]

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(i18n.t("en", "btn_english"), callback_data="switch_lang:en"),
                InlineKeyboardButton(i18n.t("en", "btn_chinese"), callback_data="switch_lang:zh"),
            ]
        ]
    )

    await update.message.reply_text(i18n.t(language, "choose_language"), reply_markup=keyboard)


async def language_switch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    await query.answer()

    store = context.application.bot_data["config_store"]
    i18n = context.application.bot_data["i18n"]

    selected_language = query.data.split(":", 1)[1]
    store.set_language(query.from_user.id, selected_language)
    await query.edit_message_text(i18n.t(selected_language, "language_switched"))
