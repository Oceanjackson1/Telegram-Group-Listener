import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from services.lark import test_webhook
from utils.formatters import build_summary_text
from utils.validators import (
    parse_group_input,
    parse_keywords_input,
    parse_source_input,
    parse_telegram_chat_identifier,
    validate_lark_webhook_url,
)

logger = logging.getLogger(__name__)

(
    LANG_SELECT,
    MONITOR_TYPE,
    SOURCE_INPUT,
    DEST_TYPE,
    DEST_INPUT,
    KEYWORD_SOURCE_INPUT,
    KEYWORDS_INPUT,
    KEYWORD_DEST_INPUT,
    REUSE_DEST,
    CONFIRM,
) = range(10)


def _is_private_chat(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type == "private")


def _get_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    store = context.application.bot_data["config_store"]
    user_id = update.effective_user.id
    return store.get_language(user_id)


def _build_confirm_keyboard(i18n, language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(i18n.t(language, "btn_confirm_start"), callback_data="confirm:start"),
                InlineKeyboardButton(i18n.t(language, "btn_reconfigure"), callback_data="confirm:reconfigure"),
            ]
        ]
    )


def _destination_display(i18n, language: str, destination: dict) -> str:
    destination_type = destination.get("type")
    if destination_type == "lark":
        return i18n.t(language, "dest_type_lark")
    if destination_type == "telegram":
        value = destination.get("value", {})
        target = f"@{value['value']}" if value.get("type") == "username" else value.get("value", "-")
        return f"{i18n.t(language, 'dest_type_telegram')} ({target})"
    return i18n.t(language, "destination_unknown")


def _has_person_destination(config: dict) -> bool:
    destination = config.get("destination", {})
    destination_type = destination.get("type")
    if destination_type == "lark":
        return bool(destination.get("value"))
    if destination_type == "telegram":
        value = destination.get("value", {})
        return value.get("type") in {"id", "username"} and bool(value.get("value"))
    return False


async def prompt_monitor_type_step(chat_id: int, context: ContextTypes.DEFAULT_TYPE, language: str) -> None:
    i18n = context.application.bot_data["i18n"]
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(i18n.t(language, "btn_monitor_person"), callback_data="monitor:person"),
                InlineKeyboardButton(i18n.t(language, "btn_monitor_keyword"), callback_data="monitor:keyword"),
            ]
        ]
    )
    await context.bot.send_message(chat_id=chat_id, text=i18n.t(language, "choose_monitor_type"), reply_markup=keyboard)


async def prompt_source_step(chat_id: int, context: ContextTypes.DEFAULT_TYPE, language: str) -> None:
    i18n = context.application.bot_data["i18n"]
    await context.bot.send_message(chat_id=chat_id, text=i18n.t(language, "step1_source"))


async def prompt_keyword_source_step(chat_id: int, context: ContextTypes.DEFAULT_TYPE, language: str) -> None:
    i18n = context.application.bot_data["i18n"]
    await context.bot.send_message(chat_id=chat_id, text=i18n.t(language, "keyword_step1_source"))


async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return ConversationHandler.END

    language = _get_language(update, context)
    i18n = context.application.bot_data["i18n"]

    if not _is_private_chat(update):
        await update.message.reply_text(i18n.t(language, "dm_only"))
        return ConversationHandler.END

    context.user_data["draft_config"] = {}
    await update.message.reply_text(i18n.t(language, "config_started"))
    await prompt_monitor_type_step(update.effective_chat.id, context, language)
    return MONITOR_TYPE


async def monitor_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return MONITOR_TYPE

    await query.answer()
    language = _get_language(update, context)
    i18n = context.application.bot_data["i18n"]

    monitor_type = query.data.split(":", 1)[1]
    draft_config = context.user_data.setdefault("draft_config", {})
    draft_config.clear()
    draft_config["monitor_type"] = monitor_type

    if monitor_type == "person":
        await query.edit_message_text(i18n.t(language, "monitor_type_person_selected"))
        await prompt_source_step(query.from_user.id, context, language)
        return SOURCE_INPUT

    await query.edit_message_text(i18n.t(language, "monitor_type_keyword_selected"))
    await prompt_keyword_source_step(query.from_user.id, context, language)
    return KEYWORD_SOURCE_INPUT


async def source_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return SOURCE_INPUT

    language = _get_language(update, context)
    i18n = context.application.bot_data["i18n"]

    parsed_source = parse_source_input(update.message.text)
    if not parsed_source:
        await update.message.reply_text(i18n.t(language, "source_input_error"))
        return SOURCE_INPUT

    draft_config = context.user_data.setdefault("draft_config", {})
    draft_config["monitor_type"] = "person"
    draft_config["source"] = parsed_source

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(i18n.t(language, "btn_lark"), callback_data="dest:lark"),
                InlineKeyboardButton(i18n.t(language, "btn_telegram"), callback_data="dest:telegram"),
            ]
        ]
    )

    await update.message.reply_text(i18n.t(language, "step2_destination"), reply_markup=keyboard)
    return DEST_TYPE


async def destination_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return DEST_TYPE

    await query.answer()
    language = _get_language(update, context)
    i18n = context.application.bot_data["i18n"]

    destination_type = query.data.split(":", 1)[1]

    draft_config = context.user_data.setdefault("draft_config", {})
    if draft_config.get("monitor_type") != "person":
        await query.edit_message_text(i18n.t(language, "internal_error"))
        await prompt_monitor_type_step(query.from_user.id, context, language)
        return MONITOR_TYPE

    if "source" not in draft_config:
        await query.edit_message_text(i18n.t(language, "source_input_error"))
        await prompt_source_step(query.from_user.id, context, language)
        return SOURCE_INPUT

    draft_config["destination_type"] = destination_type

    destination_label_key = "dest_type_lark" if destination_type == "lark" else "dest_type_telegram"
    await query.edit_message_text(
        i18n.t(language, "destination_type_selected", destination=i18n.t(language, destination_label_key))
    )

    if destination_type == "lark":
        await context.bot.send_message(chat_id=query.from_user.id, text=i18n.t(language, "ask_lark_webhook"))
    else:
        await context.bot.send_message(chat_id=query.from_user.id, text=i18n.t(language, "ask_telegram_group"))

    return DEST_INPUT


async def destination_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return DEST_INPUT

    language = _get_language(update, context)
    i18n = context.application.bot_data["i18n"]
    draft_config = context.user_data.setdefault("draft_config", {})

    if draft_config.get("monitor_type") != "person":
        await update.message.reply_text(i18n.t(language, "internal_error"))
        await prompt_monitor_type_step(update.effective_user.id, context, language)
        return MONITOR_TYPE

    destination_type = draft_config.get("destination_type")
    if destination_type not in {"lark", "telegram"}:
        await update.message.reply_text(i18n.t(language, "step2_destination"))
        return DEST_TYPE

    text_value = update.message.text.strip()

    if destination_type == "lark":
        if not validate_lark_webhook_url(text_value):
            await update.message.reply_text(i18n.t(language, "invalid_lark_url"))
            return DEST_INPUT

        is_ok, reason = await test_webhook(text_value, i18n.t(language, "lark_test_message"))
        if not is_ok:
            await update.message.reply_text(i18n.t(language, "lark_webhook_test_failed", reason=reason))
            return DEST_INPUT

        destination = {"type": "lark", "value": text_value}
    else:
        parsed_group = parse_telegram_chat_identifier(text_value)
        if not parsed_group:
            await update.message.reply_text(i18n.t(language, "invalid_telegram_group"))
            return DEST_INPUT

        destination = {"type": "telegram", "value": parsed_group}

    draft_config["destination"] = destination

    preview_config = {
        "monitor_type": "person",
        "source": draft_config.get("source", {}),
        "destination": destination,
        "active": False,
    }
    summary = build_summary_text(i18n, language, preview_config, title_key="step3_confirm")

    await update.message.reply_text(summary, reply_markup=_build_confirm_keyboard(i18n, language))
    return CONFIRM


async def keyword_source_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return KEYWORD_SOURCE_INPUT

    language = _get_language(update, context)
    i18n = context.application.bot_data["i18n"]
    draft_config = context.user_data.setdefault("draft_config", {})

    source_group = parse_group_input(update.message.text)
    if not source_group:
        await update.message.reply_text(i18n.t(language, "keyword_source_input_error"))
        return KEYWORD_SOURCE_INPUT

    draft_config["monitor_type"] = "keyword"
    draft_config["keyword_source"] = source_group

    await update.message.reply_text(i18n.t(language, "keyword_step2_keywords"))
    return KEYWORDS_INPUT


async def keywords_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return KEYWORDS_INPUT

    language = _get_language(update, context)
    i18n = context.application.bot_data["i18n"]
    store = context.application.bot_data["config_store"]
    draft_config = context.user_data.setdefault("draft_config", {})

    keywords = parse_keywords_input(update.message.text)
    if not keywords:
        await update.message.reply_text(i18n.t(language, "keyword_input_error"))
        return KEYWORDS_INPUT

    draft_config["keywords"] = keywords

    user_config = store.get_user_config(update.effective_user.id)
    if _has_person_destination(user_config):
        existing_destination = user_config.get("destination", {})
        draft_config["existing_destination"] = existing_destination
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(i18n.t(language, "btn_yes_use_existing"), callback_data="reuse_dest:yes"),
                    InlineKeyboardButton(i18n.t(language, "btn_no_set_new"), callback_data="reuse_dest:no"),
                ]
            ]
        )
        await update.message.reply_text(
            i18n.t(
                language,
                "keyword_reuse_existing_destination",
                destination=_destination_display(i18n, language, existing_destination),
            ),
            reply_markup=keyboard,
        )
        return REUSE_DEST

    await update.message.reply_text(i18n.t(language, "keyword_step3_destination"))
    return KEYWORD_DEST_INPUT


async def reuse_destination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return REUSE_DEST

    await query.answer()
    language = _get_language(update, context)
    i18n = context.application.bot_data["i18n"]
    draft_config = context.user_data.setdefault("draft_config", {})

    reuse_choice = query.data.split(":", 1)[1]
    if reuse_choice == "yes":
        destination = draft_config.get("existing_destination")
        if not destination:
            await query.edit_message_text(i18n.t(language, "internal_error"))
            await context.bot.send_message(chat_id=query.from_user.id, text=i18n.t(language, "keyword_step3_destination"))
            return KEYWORD_DEST_INPUT

        draft_config["keyword_destination"] = destination
        preview_config = {
            "monitor_type": "keyword",
            "keyword_source": draft_config.get("keyword_source", {}),
            "keywords": draft_config.get("keywords", []),
            "keyword_destination": destination,
            "keyword_active": False,
        }
        summary = build_summary_text(i18n, language, preview_config, title_key="step3_confirm_keyword")
        await query.edit_message_text(summary, reply_markup=_build_confirm_keyboard(i18n, language))
        return CONFIRM

    await query.edit_message_text(i18n.t(language, "keyword_new_destination_selected"))
    await context.bot.send_message(chat_id=query.from_user.id, text=i18n.t(language, "keyword_step3_destination"))
    return KEYWORD_DEST_INPUT


async def keyword_destination_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return KEYWORD_DEST_INPUT

    language = _get_language(update, context)
    i18n = context.application.bot_data["i18n"]
    draft_config = context.user_data.setdefault("draft_config", {})
    raw_value = update.message.text.strip()

    destination = None
    if validate_lark_webhook_url(raw_value):
        is_ok, reason = await test_webhook(raw_value, i18n.t(language, "lark_test_message"))
        if not is_ok:
            await update.message.reply_text(i18n.t(language, "lark_webhook_test_failed", reason=reason))
            return KEYWORD_DEST_INPUT
        destination = {"type": "lark", "value": raw_value}
    else:
        parsed_group = parse_telegram_chat_identifier(raw_value)
        if parsed_group:
            destination = {"type": "telegram", "value": parsed_group}

    if not destination:
        await update.message.reply_text(i18n.t(language, "invalid_keyword_destination"))
        return KEYWORD_DEST_INPUT

    draft_config["keyword_destination"] = destination

    preview_config = {
        "monitor_type": "keyword",
        "keyword_source": draft_config.get("keyword_source", {}),
        "keywords": draft_config.get("keywords", []),
        "keyword_destination": destination,
        "keyword_active": False,
    }
    summary = build_summary_text(i18n, language, preview_config, title_key="step3_confirm_keyword")
    await update.message.reply_text(summary, reply_markup=_build_confirm_keyboard(i18n, language))
    return CONFIRM


async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return CONFIRM

    await query.answer()
    language = _get_language(update, context)
    i18n = context.application.bot_data["i18n"]
    store = context.application.bot_data["config_store"]

    action = query.data.split(":", 1)[1]
    if action == "reconfigure":
        context.user_data["draft_config"] = {}
        await query.edit_message_text(i18n.t(language, "reconfigure_notice"))
        await prompt_monitor_type_step(query.from_user.id, context, language)
        return MONITOR_TYPE

    draft_config = context.user_data.get("draft_config", {})
    monitor_type = draft_config.get("monitor_type")
    if monitor_type not in {"person", "keyword"}:
        await query.edit_message_text(i18n.t(language, "internal_error"))
        await prompt_monitor_type_step(query.from_user.id, context, language)
        return MONITOR_TYPE

    config_payload = {"language": language}
    running_text = ""

    if monitor_type == "person":
        if "source" not in draft_config or "destination" not in draft_config:
            await query.edit_message_text(i18n.t(language, "internal_error"))
            await prompt_source_step(query.from_user.id, context, language)
            return SOURCE_INPUT

        config_payload.update(
            {
                "source": draft_config["source"],
                "destination": draft_config["destination"],
                "active": True,
            }
        )
        source = config_payload["source"]
        source_group = f"@{source['group']['value']}" if source["group"]["type"] == "username" else source["group"]["value"]
        source_user = f"@{source['user']['value']}" if source["user"]["type"] == "username" else source["user"]["value"]

        if config_payload["destination"]["type"] == "lark":
            running_text = i18n.t(
                language,
                "running_state_lark",
                source_user=source_user,
                source_group=source_group,
            )
        else:
            target_group = config_payload["destination"]["value"]
            target_group_display = (
                f"@{target_group['value']}" if target_group["type"] == "username" else target_group["value"]
            )
            running_text = i18n.t(
                language,
                "running_state_telegram",
                source_user=source_user,
                source_group=source_group,
                target_group=target_group_display,
            )
    else:
        if "keyword_source" not in draft_config or "keyword_destination" not in draft_config or "keywords" not in draft_config:
            await query.edit_message_text(i18n.t(language, "internal_error"))
            await prompt_keyword_source_step(query.from_user.id, context, language)
            return KEYWORD_SOURCE_INPUT

        config_payload.update(
            {
                "keyword_source": draft_config["keyword_source"],
                "keyword_destination": draft_config["keyword_destination"],
                "keywords": draft_config["keywords"],
                "keyword_active": True,
            }
        )
        source_group = (
            f"@{config_payload['keyword_source']['value']}"
            if config_payload["keyword_source"]["type"] == "username"
            else config_payload["keyword_source"]["value"]
        )
        keywords_display = ", ".join(config_payload["keywords"])

        if config_payload["keyword_destination"]["type"] == "lark":
            running_text = i18n.t(
                language,
                "running_state_keyword_lark",
                source_group=source_group,
                keywords=keywords_display,
            )
        else:
            target_group = config_payload["keyword_destination"]["value"]
            target_group_display = (
                f"@{target_group['value']}" if target_group["type"] == "username" else target_group["value"]
            )
            running_text = i18n.t(
                language,
                "running_state_keyword_telegram",
                source_group=source_group,
                keywords=keywords_display,
                target_group=target_group_display,
            )

    store.update_user_config(query.from_user.id, config_payload)
    context.user_data.pop("draft_config", None)

    await query.edit_message_text(i18n.t(language, "confirmation_saved"))
    await context.bot.send_message(chat_id=query.from_user.id, text=running_text)
    return ConversationHandler.END
