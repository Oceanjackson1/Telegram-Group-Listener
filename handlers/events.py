"""Events handler — join button callback, /events command, draw callback."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.events import draw_winners, get_active_events, get_participant_count, join_event

logger = logging.getLogger(__name__)


async def event_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle event join button clicks."""
    query = update.callback_query
    if not query or not query.data.startswith("ej:"):
        return

    await query.answer()

    db = context.application.bot_data.get("db")
    if not db:
        return

    event_id = int(query.data.split(":", 1)[1])
    user = query.from_user
    i18n = context.application.bot_data.get("i18n")

    event = db.fetchone("SELECT * FROM events WHERE id = ? AND status = 'active'", (event_id,))
    if not event:
        await query.answer("This event has ended.", show_alert=True)
        return

    joined = join_event(db, event_id, user.id, user.username, user.full_name)
    count = get_participant_count(db, event_id)

    if joined:
        await query.answer(f"✅ You've joined! ({count} participants)")
    else:
        await query.answer(f"You already joined! ({count} participants)")

    # Update the event message with new count
    try:
        event_text = (
            f"🎉 {event['title']}\n\n"
            f"📝 {event['description']}\n"
            f"🎁 Prize: {event['prize']}\n"
            f"👑 Winners: {event['winner_count']}\n"
            f"⏰ {event['end_time']}\n"
            f"👥 Participants: {count}"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎰 Join", callback_data=f"ej:{event_id}")],
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
    i18n = context.application.bot_data.get("i18n")

    event = db.fetchone("SELECT * FROM events WHERE id = ?", (event_id,))
    if not event:
        return

    winners = draw_winners(db, event_id)
    if not winners:
        await query.edit_message_text("No participants in this event.")
        return

    winner_lines = []
    for w in winners:
        name = w.get("display_name") or w.get("username") or str(w["user_id"])
        if w.get("username"):
            name = f"@{w['username']}"
        winner_lines.append(f"🏆 {name}")

    text = (
        f"🎊 {event['title']} — Results!\n\n"
        f"🎁 Prize: {event['prize']}\n\n"
        f"Winners:\n" + "\n".join(winner_lines) + "\n\n"
        f"Congratulations! 🥳"
    )

    # Post to group
    chat_id = event["chat_id"]
    try:
        target = int(chat_id) if chat_id.lstrip("-").isdigit() else f"@{chat_id}"
        await context.bot.send_message(chat_id=target, text=text)
    except Exception as exc:
        logger.exception("Failed to post draw results: %s", exc)

    await query.edit_message_text(f"✅ Draw complete! {len(winners)} winner(s) announced in group.")


async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List active events in the current group."""
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

    events = get_active_events(db, chat_id)
    if not events:
        await message.reply_text(i18n.t(language, "events_none") if i18n else "No active events.")
        return

    lines = []
    for ev in events:
        count = get_participant_count(db, ev["id"])
        lines.append(f"🎉 {ev['title']} (👥 {count} participants)\n   🎁 {ev['prize']} | ⏰ {ev['end_time']}")

    await message.reply_text("\n\n".join(lines))
