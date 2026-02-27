from __future__ import annotations

from telegram import Bot, Message

from utils.validators import resolve_chat_target


def _has_media(message: Message) -> bool:
    return bool(
        message.photo
        or message.video
        or message.document
        or message.sticker
        or message.audio
        or message.animation
        or message.voice
        or message.video_note
    )


async def send_alert(
    bot: Bot,
    target_group: dict,
    source_message: Message,
    source_user: str,
    source_group: str,
    timestamp: str,
    text_template: str,
    header_template: str,
    extra_context: dict | None = None,
) -> None:
    chat_target = resolve_chat_target(target_group)
    content = source_message.text or source_message.caption or ""
    context = {
        "source_user": source_user,
        "source_group": source_group,
        "timestamp": timestamp,
        "content": content,
    }
    if extra_context:
        context.update(extra_context)

    if not _has_media(source_message):
        text = text_template.format(**context)
        await bot.send_message(chat_id=chat_target, text=text)
        return

    header = header_template.format(**context)
    await bot.send_message(chat_id=chat_target, text=header)
    await bot.copy_message(
        chat_id=chat_target,
        from_chat_id=source_message.chat_id,
        message_id=source_message.message_id,
    )
