"""Events handler — join button callback, /events command, draw callback."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.events import draw_winners, get_active_events, get_participant_count, join_event
from utils.progress import ProgressTracker

logger = logging.getLogger(__name__)


def _get_language(context, chat_id: str) -> str:
    gm = context.application.bot_data.get("group_manager")
    return gm.get_group_language(chat_id) if gm else "en"


def _get_i18n(context):
    return context.application.bot_data.get("i18n")


async def event_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle event join button clicks."""
    query = update.callback_query
    if not query or not query.data.startswith("ej:"):
        return

    db = context.application.bot_data.get("db")
    if not db:
        await query.answer()
        return

    event_id = int(query.data.split(":", 1)[1])
    user = query.from_user
    i18n = _get_i18n(context)

    event = db.fetchone("SELECT * FROM events WHERE id = ? AND status = 'active'", (event_id,))
    if not event:
        language = "en"
        msg = i18n.t(language, "event_ended") if i18n else "This event has ended."
        await query.answer(msg, show_alert=True)
        return

    chat_id = str(event["chat_id"])
    language = _get_language(context, chat_id)

    joined = join_event(db, event_id, user.id, user.username, user.full_name)
    count = get_participant_count(db, event_id)

    if joined:
        await query.answer(i18n.t(language, "event_joined", count=count) if i18n else f"Joined! ({count})")
    else:
        await query.answer(i18n.t(language, "event_already_joined", count=count) if i18n else f"Already joined! ({count})")

    # Update the event message with new count
    try:
        event_text = (
            f"🎉 {event['title']}\n\n"
            f"📝 {event['description']}\n"
            f"🎁 {i18n.t(language, 'event_prize')}: {event['prize']}\n"
            f"👑 {i18n.t(language, 'event_winners')}: {event['winner_count']}\n"
            f"⏰ {event['end_time']}\n"
            f"👥 {i18n.t(language, 'event_participants')}: {count}"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎰 " + i18n.t(language, "event_join"), callback_data=f"ej:{event_id}")],
        ])
        await query.edit_message_text(event_text, reply_markup=keyboard)
    except Exception:
        pass  # Message may not be editable


async def event_draw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle manual draw trigger from admin."""
    query = update.callback_query
    if not query or not query.data.startswith("evd:"):
        return

    await query.answer()

    db = context.application.bot_data.get("db")
    if not db:
        return

    event_id = int(query.data.split(":", 1)[1])
    i18n = _get_i18n(context)

    event = db.fetchone("SELECT * FROM events WHERE id = ?", (event_id,))
    if not event:
        return

    chat_id = str(event["chat_id"])
    language = _get_language(context, chat_id)

    async with ProgressTracker(
        bot=context.bot,
        chat_id=query.message.chat.id,
        i18n=i18n,
        language=language,
        task_key="progress_drawing_winners",
        determinate=False,
    ) as pt:
        winners = draw_winners(db, event_id)

    if not winners:
        msg = i18n.t(language, "event_no_participants") if i18n else "No participants."
        await query.edit_message_text(msg)
        return

    winner_lines = []
    for w in winners:
        name = w.get("display_name") or w.get("username") or str(w["user_id"])
        if w.get("username"):
            name = f"@{w['username']}"
        winner_lines.append(f"🏆 {name}")

    text = (
        i18n.t(language, "event_results_title", title=event['title']) + "\n\n"
        f"🎁 {i18n.t(language, 'event_prize')}: {event['prize']}\n\n"
        + i18n.t(language, "event_winners") + ":\n"
        + "\n".join(winner_lines) + "\n\n"
        + i18n.t(language, "event_congrats")
    )

    # Post to group
    async with ProgressTracker(
        bot=context.bot,
        chat_id=query.message.chat.id,
        i18n=i18n,
        language=language,
        task_key="progress_sending_to_group",
        determinate=False,
    ):
        try:
            target = int(chat_id) if chat_id.lstrip("-").isdigit() else f"@{chat_id}"
            await context.bot.send_message(chat_id=target, text=text)
        except Exception as exc:
            logger.exception("Failed to post draw results: %s", exc)

    draw_msg = i18n.t(language, "event_draw_complete", count=len(winners)) if i18n else f"Draw complete! {len(winners)} winner(s)."
    await query.edit_message_text(f"✅ {draw_msg}")


async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List active events in the current group."""
    message = update.effective_message
    if not message or not message.chat:
        return

    db = context.application.bot_data.get("db")
    if not db:
        return

    i18n = _get_i18n(context)
    chat_id = str(message.chat.id)
    language = _get_language(context, chat_id)

    events = get_active_events(db, chat_id)
    if not events:
        await message.reply_text(i18n.t(language, "events_none") if i18n else "No active events.")
        return

    lines = []
    for ev in events:
        count = get_participant_count(db, ev["id"])
        lines.append(
            f"🎉 {ev['title']} (👥 {count} {i18n.t(language, 'event_participants')})\n"
            f"   🎁 {ev['prize']} | ⏰ {ev['end_time']}"
        )

    await message.reply_text("\n\n".join(lines))
