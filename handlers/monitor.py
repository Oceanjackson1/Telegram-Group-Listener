import logging
from datetime import datetime, timezone

from telegram import Chat, Update
from telegram.ext import ContextTypes

from services import lark as lark_service
from services import telegram as telegram_service
from utils.validators import find_matched_keywords, matches_chat_identifier, matches_user_identifier

logger = logging.getLogger(__name__)


def _chat_display(chat: Chat) -> str:
    if chat.username:
        return f"@{chat.username}"
    return str(chat.id)


def _user_display(user) -> str:
    if user.username:
        return f"@{user.username}"
    return str(user.id)


async def _forward_person_message(
    owner_id: str,
    config: dict,
    message,
    context: ContextTypes.DEFAULT_TYPE,
    i18n,
    language: str,
    source_user_display: str,
    source_group_display: str,
    timestamp: str,
) -> None:
    source = config.get("source", {})
    source_group = source.get("group")
    source_user = source.get("user")
    if not source_group or not source_user:
        return

    if not matches_chat_identifier(source_group, message.chat.id, message.chat.username):
        return

    if not matches_user_identifier(source_user, message.from_user.id, message.from_user.username):
        return

    destination = config.get("destination", {})
    destination_type = destination.get("type")

    if destination_type == "lark":
        content = lark_service.extract_content_for_lark(
            message,
            i18n.t(language, "lark_media_note"),
        )
        delivered = await lark_service.send_alert(
            webhook_url=destination.get("value", ""),
            source_user=source_user_display,
            source_group=source_group_display,
            content=content,
            title=i18n.t(language, "lark_alert_title"),
            from_label=i18n.t(language, "lark_field_from"),
            group_label=i18n.t(language, "lark_field_group"),
            time_template=i18n.t(language, "lark_time_label"),
        )
        if not delivered:
            await context.bot.send_message(
                chat_id=int(owner_id),
                text=i18n.t(language, "lark_delivery_failed_dm"),
            )
        return

    if destination_type == "telegram":
        await telegram_service.send_alert(
            bot=context.bot,
            target_group=destination.get("value", {}),
            source_message=message,
            source_user=source_user_display,
            source_group=source_group_display,
            timestamp=timestamp,
            text_template=i18n.t(language, "tg_alert_template"),
            header_template=i18n.t(language, "tg_alert_header"),
        )


async def _forward_keyword_message(
    owner_id: str,
    config: dict,
    message,
    context: ContextTypes.DEFAULT_TYPE,
    i18n,
    language: str,
    source_user_display: str,
    source_group_display: str,
    timestamp: str,
) -> None:
    keyword_source = config.get("keyword_source")
    keywords = config.get("keywords", [])
    destination = config.get("keyword_destination", {})
    destination_type = destination.get("type")

    if not keyword_source or not keywords or destination_type not in {"lark", "telegram"}:
        return

    if not matches_chat_identifier(keyword_source, message.chat.id, message.chat.username):
        return

    text_content = message.text or message.caption or ""
    matched_keywords = find_matched_keywords(text_content, keywords)
    if not matched_keywords:
        return

    matched_keywords_display = ", ".join(matched_keywords)

    if destination_type == "lark":
        content = lark_service.extract_content_for_lark(
            message,
            i18n.t(language, "lark_media_note"),
        )
        content = (
            f"{i18n.t(language, 'keyword_match_prefix', keywords=matched_keywords_display)}\n\n"
            f"{content}"
        )
        delivered = await lark_service.send_alert(
            webhook_url=destination.get("value", ""),
            source_user=source_user_display,
            source_group=source_group_display,
            content=content,
            title=i18n.t(language, "lark_keyword_alert_title"),
            from_label=i18n.t(language, "lark_field_from"),
            group_label=i18n.t(language, "lark_field_group"),
            time_template=i18n.t(language, "lark_time_label"),
        )
        if not delivered:
            await context.bot.send_message(
                chat_id=int(owner_id),
                text=i18n.t(language, "lark_delivery_failed_dm"),
            )
        return

    await telegram_service.send_alert(
        bot=context.bot,
        target_group=destination.get("value", {}),
        source_message=message,
        source_user=source_user_display,
        source_group=source_group_display,
        timestamp=timestamp,
        text_template=i18n.t(language, "tg_keyword_alert_template"),
        header_template=i18n.t(language, "tg_keyword_alert_header"),
        extra_context={"matched_keywords": matched_keywords_display},
    )


async def monitored_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.from_user or not message.chat:
        return

    store = context.application.bot_data["config_store"]
    i18n = context.application.bot_data["i18n"]

    all_configs = store.get_all_configs()
    if not all_configs:
        return

    source_group_display = _chat_display(message.chat)
    source_user_display = _user_display(message.from_user)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    for owner_id, config in all_configs.items():
        language = config.get("language", "en")

        try:
            if config.get("active"):
                await _forward_person_message(
                    owner_id=owner_id,
                    config=config,
                    message=message,
                    context=context,
                    i18n=i18n,
                    language=language,
                    source_user_display=source_user_display,
                    source_group_display=source_group_display,
                    timestamp=timestamp,
                )
        except Exception as exc:
            logger.exception("Failed to forward person monitoring message for owner %s: %s", owner_id, exc)

        try:
            if config.get("keyword_active"):
                await _forward_keyword_message(
                    owner_id=owner_id,
                    config=config,
                    message=message,
                    context=context,
                    i18n=i18n,
                    language=language,
                    source_user_display=source_user_display,
                    source_group_display=source_group_display,
                    timestamp=timestamp,
                )
        except Exception as exc:
            logger.exception("Failed to forward keyword monitoring message for owner %s: %s", owner_id, exc)


async def chat_member_update_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    change = update.my_chat_member
    if not change:
        return

    new_status = change.new_chat_member.status
    if new_status not in {"left", "kicked", "banned"}:
        return

    store = context.application.bot_data["config_store"]
    i18n = context.application.bot_data["i18n"]
    chat = change.chat

    for owner_id, config in store.get_all_configs().items():
        person_source_group = config.get("source", {}).get("group")
        keyword_source_group = config.get("keyword_source")
        person_matches = config.get("active") and matches_chat_identifier(person_source_group, chat.id, chat.username)
        keyword_matches = config.get("keyword_active") and matches_chat_identifier(
            keyword_source_group, chat.id, chat.username
        )

        if not person_matches and not keyword_matches:
            continue

        updates = {}
        if person_matches:
            updates["active"] = False
        if keyword_matches:
            updates["keyword_active"] = False

        try:
            store.update_user_config(int(owner_id), updates)
        except ValueError:
            logger.error("Invalid owner id in config store: %s", owner_id)
            continue

        language = config.get("language", "en")
        if person_matches and keyword_matches:
            monitor_type = i18n.t(language, "monitor_type_both")
        elif person_matches:
            monitor_type = i18n.t(language, "monitor_type_person")
        else:
            monitor_type = i18n.t(language, "monitor_type_keyword")

        try:
            await context.bot.send_message(
                chat_id=int(owner_id),
                text=i18n.t(
                    language,
                    "bot_removed_source_dm",
                    source_group=_chat_display(chat),
                    monitor_type=monitor_type,
                ),
            )
        except Exception as exc:
            logger.exception("Failed to notify owner %s about group removal: %s", owner_id, exc)
