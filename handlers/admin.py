"""Admin backend — /admin command, group selection, and sub-menu routing.

This is the main management panel accessed via DM. It provides a unified
entry point for all configuration modules (anti-spam, Q&A, AI knowledge,
community dialogue, events, monitoring).
"""

import json
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)

# Conversation states
(
    SELECT_GROUP,
    GROUP_MENU,
    # Anti-spam
    SPAM_MENU,
    SPAM_BLACKLIST_INPUT,
    SPAM_LINK_WHITELIST_INPUT,
    SPAM_PUNISHMENT_SELECT,
    SPAM_WHITELIST_USER_INPUT,
    # Q&A
    QA_MENU,
    QA_ADD_TRIGGER,
    QA_ADD_RESPONSE,
    QA_EDIT_SELECT,
    QA_EDIT_RESPONSE,
    # Community
    COMMUNITY_MENU,
    COMMUNITY_WELCOME_INPUT,
    COMMUNITY_ATBOT_INPUT,
    COMMUNITY_SCHEDULED_INPUT,
    COMMUNITY_PROXY_INPUT,
    # Events
    EVENT_MENU,
    EVENT_CREATE_TITLE,
    EVENT_CREATE_DESC,
    EVENT_CREATE_PRIZE,
    EVENT_CREATE_WINNERS,
    EVENT_CREATE_TIME,
    EVENT_CONFIRM,
    # AI Knowledge
    AI_MENU,
    AI_UPLOAD_FILE,
    AI_SYSTEM_PROMPT_INPUT,
    AI_TRIGGER_SELECT,
    # Generic
    WAITING_INPUT,
) = range(29)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _get_i18n(context):
    return context.application.bot_data["i18n"]


def _get_db(context):
    return context.application.bot_data["db"]


def _get_gm(context):
    return context.application.bot_data["group_manager"]


# ─── Entry: /admin ──────────────────────────────────────────────────────────

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return ConversationHandler.END

    # If used in group chat, hint the user to go to DM
    if update.effective_chat.type != "private":
        i18n = _get_i18n(context)
        language = "zh"  # default hint
        await update.message.reply_text(i18n.t(language, "admin_use_dm"))
        return ConversationHandler.END

    i18n = _get_i18n(context)
    gm = _get_gm(context)
    user_id = update.effective_user.id
    language = _get_user_language(context, user_id)

    groups = gm.get_user_groups(user_id)
    if not groups:
        await update.message.reply_text(i18n.t(language, "admin_no_groups"))
        return ConversationHandler.END

    keyboard = []
    for g in groups:
        label = g.get("chat_title") or g["chat_id"]
        keyboard.append([InlineKeyboardButton(label, callback_data=f"ag:{g['chat_id']}")])

    await update.message.reply_text(
        i18n.t(language, "admin_select_group"),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECT_GROUP


def _get_user_language(context, user_id: int) -> str:
    store = context.application.bot_data.get("config_store")
    if store:
        return store.get_language(user_id)
    return "en"


# ─── Group selection ─────────────────────────────────────────────────────────

async def select_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    chat_id = query.data.split(":", 1)[1]
    context.user_data["admin_chat_id"] = chat_id
    return await _show_group_menu(query, context)


async def _show_group_menu(query_or_msg, context: ContextTypes.DEFAULT_TYPE) -> int:
    i18n = _get_i18n(context)
    chat_id = context.user_data.get("admin_chat_id")
    gm = _get_gm(context)
    group = gm.get_group(chat_id)
    title = (group.get("chat_title") if group else chat_id) or chat_id
    language = _get_user_language(context, query_or_msg.from_user.id)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡️ " + i18n.t(language, "admin_antispam"), callback_data="am:spam")],
        [InlineKeyboardButton("💬 " + i18n.t(language, "admin_qa"), callback_data="am:qa")],
        [InlineKeyboardButton("🧠 " + i18n.t(language, "admin_ai"), callback_data="am:ai")],
        [InlineKeyboardButton("🗣️ " + i18n.t(language, "admin_community"), callback_data="am:community")],
        [InlineKeyboardButton("🎉 " + i18n.t(language, "admin_events"), callback_data="am:events")],
        [InlineKeyboardButton("⬅️ " + i18n.t(language, "admin_back"), callback_data="am:back")],
    ])

    text = f"⚙️ {title}\n\n" + i18n.t(language, "admin_choose_module")

    if hasattr(query_or_msg, "edit_message_text"):
        await query_or_msg.edit_message_text(text, reply_markup=keyboard)
    else:
        await context.bot.send_message(chat_id=query_or_msg.from_user.id, text=text, reply_markup=keyboard)
    return GROUP_MENU


async def group_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    module = query.data.split(":", 1)[1]

    if module == "back":
        return await admin_command(update, context)
    if module == "spam":
        return await _show_spam_menu(query, context)
    if module == "qa":
        return await _show_qa_menu(query, context)
    if module == "ai":
        return await _show_ai_menu(query, context)
    if module == "community":
        return await _show_community_menu(query, context)
    if module == "events":
        return await _show_event_menu(query, context)

    return GROUP_MENU


# ═══════════════════════════════════════════════════════════════════════════
# ANTI-SPAM MODULE
# ═══════════════════════════════════════════════════════════════════════════

async def _show_spam_menu(query, context) -> int:
    i18n = _get_i18n(context)
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    language = _get_user_language(context, query.from_user.id)

    cfg = db.fetchone("SELECT * FROM spam_config WHERE chat_id = ?", (chat_id,))
    enabled = cfg["enabled"] if cfg else 0
    status_icon = "✅" if enabled else "❌"
    punishment = cfg["punishment"] if cfg else "delete_warn"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            ("❌ " + i18n.t(language, "admin_disable") if enabled else "✅ " + i18n.t(language, "admin_enable")),
            callback_data="sp:toggle"
        )],
        [InlineKeyboardButton("📝 " + i18n.t(language, "admin_spam_blacklist"), callback_data="sp:blacklist")],
        [InlineKeyboardButton("🔗 " + i18n.t(language, "admin_spam_linkfilter"), callback_data="sp:linkfilter")],
        [InlineKeyboardButton(f"⚖️ {i18n.t(language, 'admin_spam_punishment')}: {punishment}", callback_data="sp:punishment")],
        [InlineKeyboardButton("👤 " + i18n.t(language, "admin_spam_whitelist"), callback_data="sp:whitelist")],
        [InlineKeyboardButton("⬅️ " + i18n.t(language, "admin_back"), callback_data="sp:back")],
    ])

    text = f"🛡️ {i18n.t(language, 'admin_antispam')}\n{i18n.t(language, 'admin_status')}: {status_icon}"
    await query.edit_message_text(text, reply_markup=keyboard)
    return SPAM_MENU


async def spam_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    i18n = _get_i18n(context)
    language = _get_user_language(context, query.from_user.id)

    if action in ("back", "back_to_spam"):
        return await _show_spam_menu(query, context) if action == "back_to_spam" else await _show_group_menu(query, context)

    if action == "toggle":
        cfg = db.fetchone("SELECT * FROM spam_config WHERE chat_id = ?", (chat_id,))
        if cfg:
            new_val = 0 if cfg["enabled"] else 1
            db.execute("UPDATE spam_config SET enabled = ?, updated_at = ? WHERE chat_id = ?", (new_val, _now_utc(), chat_id))
        else:
            db.execute(
                "INSERT INTO spam_config (chat_id, enabled, updated_at) VALUES (?, 1, ?)",
                (chat_id, _now_utc()),
            )
        db.commit()
        return await _show_spam_menu(query, context)

    if action == "blacklist":
        cfg = db.fetchone("SELECT keyword_blacklist FROM spam_config WHERE chat_id = ?", (chat_id,))
        current = json.loads(cfg["keyword_blacklist"]) if cfg else []
        text = i18n.t(language, "admin_spam_blacklist_prompt", count=len(current), keywords=", ".join(current) if current else "-")
        await query.edit_message_text(text)
        context.user_data["admin_input_target"] = "spam_blacklist"
        return SPAM_BLACKLIST_INPUT

    if action == "linkfilter":
        cfg = db.fetchone("SELECT link_filter FROM spam_config WHERE chat_id = ?", (chat_id,))
        current = cfg["link_filter"] if cfg else 0
        if cfg:
            new_val = 0 if current else 1
            db.execute("UPDATE spam_config SET link_filter = ?, updated_at = ? WHERE chat_id = ?", (new_val, _now_utc(), chat_id))
        else:
            db.execute("INSERT INTO spam_config (chat_id, link_filter, updated_at) VALUES (?, 1, ?)", (chat_id, _now_utc()))
        db.commit()
        return await _show_spam_menu(query, context)

    if action == "punishment":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(i18n.t(language, "spam_punishment_delete"), callback_data="spp:delete")],
            [InlineKeyboardButton(i18n.t(language, "spam_punishment_delete_warn"), callback_data="spp:delete_warn")],
            [InlineKeyboardButton(i18n.t(language, "spam_punishment_delete_mute"), callback_data="spp:delete_mute")],
            [InlineKeyboardButton(i18n.t(language, "spam_punishment_delete_kick"), callback_data="spp:delete_kick")],
        ])
        await query.edit_message_text(i18n.t(language, "admin_spam_punishment_select"), reply_markup=keyboard)
        return SPAM_PUNISHMENT_SELECT

    if action == "whitelist":
        cfg = db.fetchone("SELECT whitelist_users FROM spam_config WHERE chat_id = ?", (chat_id,))
        current = json.loads(cfg["whitelist_users"]) if cfg else []
        text = i18n.t(language, "admin_spam_whitelist_prompt", count=len(current))
        await query.edit_message_text(text)
        context.user_data["admin_input_target"] = "spam_whitelist"
        return SPAM_WHITELIST_USER_INPUT

    return SPAM_MENU


async def spam_blacklist_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    i18n = _get_i18n(context)
    language = _get_user_language(context, update.effective_user.id)

    new_keywords = [k.strip() for k in update.message.text.replace("\n", ",").split(",") if k.strip()]
    cfg = db.fetchone("SELECT keyword_blacklist FROM spam_config WHERE chat_id = ?", (chat_id,))
    current = json.loads(cfg["keyword_blacklist"]) if cfg else []
    merged = list({k.lower(): k for k in current + new_keywords}.values())

    if cfg:
        db.execute("UPDATE spam_config SET keyword_blacklist = ?, updated_at = ? WHERE chat_id = ?",
                    (json.dumps(merged, ensure_ascii=False), _now_utc(), chat_id))
    else:
        db.execute("INSERT INTO spam_config (chat_id, keyword_blacklist, updated_at) VALUES (?, ?, ?)",
                    (chat_id, json.dumps(merged, ensure_ascii=False), _now_utc()))
    db.commit()

    await update.message.reply_text(i18n.t(language, "admin_spam_blacklist_updated", count=len(merged)))
    # Return to spam menu by sending it fresh
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ " + i18n.t(language, "admin_back"), callback_data="sp:back_to_spam")],
    ])
    await update.message.reply_text(i18n.t(language, "admin_continue"), reply_markup=keyboard)
    return SPAM_MENU


async def spam_punishment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    punishment = query.data.split(":", 1)[1]

    cfg = db.fetchone("SELECT chat_id FROM spam_config WHERE chat_id = ?", (chat_id,))
    if cfg:
        db.execute("UPDATE spam_config SET punishment = ?, updated_at = ? WHERE chat_id = ?", (punishment, _now_utc(), chat_id))
    else:
        db.execute("INSERT INTO spam_config (chat_id, punishment, updated_at) VALUES (?, ?, ?)", (chat_id, punishment, _now_utc()))
    db.commit()
    return await _show_spam_menu(query, context)


async def spam_whitelist_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    i18n = _get_i18n(context)
    language = _get_user_language(context, update.effective_user.id)

    raw = update.message.text.strip().replace("\n", ",")
    new_users = [u.strip().lstrip("@") for u in raw.split(",") if u.strip()]
    cfg = db.fetchone("SELECT whitelist_users FROM spam_config WHERE chat_id = ?", (chat_id,))
    current = json.loads(cfg["whitelist_users"]) if cfg else []
    merged = list(set(current + new_users))

    if cfg:
        db.execute("UPDATE spam_config SET whitelist_users = ?, updated_at = ? WHERE chat_id = ?",
                    (json.dumps(merged), _now_utc(), chat_id))
    else:
        db.execute("INSERT INTO spam_config (chat_id, whitelist_users, updated_at) VALUES (?, ?, ?)",
                    (chat_id, json.dumps(merged), _now_utc()))
    db.commit()

    await update.message.reply_text(i18n.t(language, "admin_spam_whitelist_updated", count=len(merged)))
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="sp:back_to_spam")]])
    await update.message.reply_text(i18n.t(language, "admin_continue"), reply_markup=keyboard)
    return SPAM_MENU


# ═══════════════════════════════════════════════════════════════════════════
# Q&A MODULE
# ═══════════════════════════════════════════════════════════════════════════

async def _show_qa_menu(query, context) -> int:
    i18n = _get_i18n(context)
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    language = _get_user_language(context, query.from_user.id)

    rules = db.fetchall("SELECT * FROM qa_rules WHERE chat_id = ? AND enabled = 1", (chat_id,))
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ " + i18n.t(language, "admin_qa_add"), callback_data="qa:add")],
        [InlineKeyboardButton(f"📋 {i18n.t(language, 'admin_qa_list')} ({len(rules)})", callback_data="qa:list")],
        [InlineKeyboardButton("🗑️ " + i18n.t(language, "admin_qa_clear"), callback_data="qa:clear")],
        [InlineKeyboardButton("⬅️ " + i18n.t(language, "admin_back"), callback_data="qa:back")],
    ])

    await query.edit_message_text(
        f"💬 {i18n.t(language, 'admin_qa')}\n{i18n.t(language, 'admin_qa_count', count=len(rules))}",
        reply_markup=keyboard,
    )
    return QA_MENU


async def qa_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    i18n = _get_i18n(context)
    language = _get_user_language(context, query.from_user.id)

    if action == "back_to_qa":
        return await _show_qa_menu(query, context)
    if action == "back":
        return await _show_group_menu(query, context)

    if action == "add":
        await query.edit_message_text(i18n.t(language, "admin_qa_trigger_prompt"))
        return QA_ADD_TRIGGER

    if action == "list":
        rules = db.fetchall("SELECT * FROM qa_rules WHERE chat_id = ? AND enabled = 1 ORDER BY id", (chat_id,))
        if not rules:
            await query.edit_message_text(i18n.t(language, "admin_qa_empty"))
        else:
            lines = []
            for i, r in enumerate(rules, 1):
                lines.append(f"{i}. Q: {r['trigger_text']}\n   A: {r['response_text'][:80]}")
            await query.edit_message_text("\n\n".join(lines))
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="qa:back_to_qa")]])
        await context.bot.send_message(chat_id=query.from_user.id, text=i18n.t(language, "admin_continue"), reply_markup=keyboard)
        return QA_MENU

    if action == "clear":
        db.execute("UPDATE qa_rules SET enabled = 0, updated_at = ? WHERE chat_id = ?", (_now_utc(), chat_id))
        db.commit()
        await query.edit_message_text(i18n.t(language, "admin_qa_cleared"))
        return await _show_qa_menu(query, context)

    return QA_MENU


async def qa_add_trigger_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["qa_trigger"] = update.message.text.strip()
    i18n = _get_i18n(context)
    language = _get_user_language(context, update.effective_user.id)
    await update.message.reply_text(i18n.t(language, "admin_qa_response_prompt"))
    return QA_ADD_RESPONSE


async def qa_add_response_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    trigger = context.user_data.pop("qa_trigger", "")
    response = update.message.text.strip()
    i18n = _get_i18n(context)
    language = _get_user_language(context, update.effective_user.id)

    db.execute(
        "INSERT INTO qa_rules (chat_id, trigger_text, response_text, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (chat_id, trigger, response, _now_utc(), _now_utc()),
    )
    db.commit()

    await update.message.reply_text(i18n.t(language, "admin_qa_added", trigger=trigger))
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ " + i18n.t(language, "admin_qa_add_more"), callback_data="qa:add")],
        [InlineKeyboardButton("⬅️ Back", callback_data="qa:back_to_qa")],
    ])
    await update.message.reply_text(i18n.t(language, "admin_continue"), reply_markup=keyboard)
    return QA_MENU


# ═══════════════════════════════════════════════════════════════════════════
# COMMUNITY MODULE
# ═══════════════════════════════════════════════════════════════════════════

async def _show_community_menu(query, context) -> int:
    i18n = _get_i18n(context)
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    language = _get_user_language(context, query.from_user.id)

    cfg = db.fetchone("SELECT * FROM chat_config WHERE chat_id = ?", (chat_id,))
    welcome_on = cfg["welcome_enabled"] if cfg else 0

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            ("❌ " if welcome_on else "✅ ") + i18n.t(language, "admin_community_welcome"),
            callback_data="cm:toggle_welcome"
        )],
        [InlineKeyboardButton("📝 " + i18n.t(language, "admin_community_welcome_msg"), callback_data="cm:welcome_msg")],
        [InlineKeyboardButton("📢 " + i18n.t(language, "admin_community_proxy"), callback_data="cm:proxy")],
        [InlineKeyboardButton("⬅️ " + i18n.t(language, "admin_back"), callback_data="cm:back")],
    ])

    status_icon = "✅" if welcome_on else "❌"
    await query.edit_message_text(
        f"🗣️ {i18n.t(language, 'admin_community')}\n{i18n.t(language, 'admin_community_welcome')}: {status_icon}",
        reply_markup=keyboard,
    )
    return COMMUNITY_MENU


async def community_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    i18n = _get_i18n(context)
    language = _get_user_language(context, query.from_user.id)

    if action == "back_to_cm":
        return await _show_community_menu(query, context)
    if action == "back":
        return await _show_group_menu(query, context)

    if action == "toggle_welcome":
        cfg = db.fetchone("SELECT * FROM chat_config WHERE chat_id = ?", (chat_id,))
        if cfg:
            new_val = 0 if cfg["welcome_enabled"] else 1
            db.execute("UPDATE chat_config SET welcome_enabled = ?, updated_at = ? WHERE chat_id = ?", (new_val, _now_utc(), chat_id))
        else:
            db.execute("INSERT INTO chat_config (chat_id, welcome_enabled, updated_at) VALUES (?, 1, ?)", (chat_id, _now_utc()))
        db.commit()
        return await _show_community_menu(query, context)

    if action == "welcome_msg":
        await query.edit_message_text(i18n.t(language, "admin_community_welcome_input"))
        return COMMUNITY_WELCOME_INPUT

    if action == "proxy":
        await query.edit_message_text(i18n.t(language, "admin_community_proxy_input"))
        return COMMUNITY_PROXY_INPUT

    return COMMUNITY_MENU


async def community_welcome_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    i18n = _get_i18n(context)
    language = _get_user_language(context, update.effective_user.id)
    msg = update.message.text.strip()

    cfg = db.fetchone("SELECT chat_id FROM chat_config WHERE chat_id = ?", (chat_id,))
    if cfg:
        db.execute("UPDATE chat_config SET welcome_message = ?, updated_at = ? WHERE chat_id = ?", (msg, _now_utc(), chat_id))
    else:
        db.execute("INSERT INTO chat_config (chat_id, welcome_message, welcome_enabled, updated_at) VALUES (?, ?, 1, ?)", (chat_id, msg, _now_utc()))
    db.commit()

    await update.message.reply_text(i18n.t(language, "admin_community_welcome_saved"))
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="cm:back_to_cm")]])
    await update.message.reply_text(i18n.t(language, "admin_continue"), reply_markup=keyboard)
    return COMMUNITY_MENU


async def community_proxy_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = context.user_data["admin_chat_id"]
    i18n = _get_i18n(context)
    language = _get_user_language(context, update.effective_user.id)
    msg = update.message.text.strip()

    try:
        target = int(chat_id) if chat_id.lstrip("-").isdigit() else f"@{chat_id}"
        await context.bot.send_message(chat_id=target, text=msg)
        await update.message.reply_text(i18n.t(language, "admin_community_proxy_sent"))
    except Exception as exc:
        logger.exception("Proxy send failed: %s", exc)
        await update.message.reply_text(i18n.t(language, "admin_community_proxy_failed"))

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="cm:back_to_cm")]])
    await update.message.reply_text(i18n.t(language, "admin_continue"), reply_markup=keyboard)
    return COMMUNITY_MENU


# ═══════════════════════════════════════════════════════════════════════════
# EVENTS MODULE
# ═══════════════════════════════════════════════════════════════════════════

async def _show_event_menu(query, context) -> int:
    i18n = _get_i18n(context)
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    language = _get_user_language(context, query.from_user.id)

    active_events = db.fetchall("SELECT * FROM events WHERE chat_id = ? AND status = 'active'", (chat_id,))
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 " + i18n.t(language, "admin_event_create"), callback_data="ev:create")],
        [InlineKeyboardButton(f"📋 {i18n.t(language, 'admin_event_list')} ({len(active_events)})", callback_data="ev:list")],
        [InlineKeyboardButton("🎰 " + i18n.t(language, "admin_event_draw"), callback_data="ev:draw")],
        [InlineKeyboardButton("⬅️ " + i18n.t(language, "admin_back"), callback_data="ev:back")],
    ])

    await query.edit_message_text(
        f"🎉 {i18n.t(language, 'admin_events')}\n{i18n.t(language, 'admin_event_active', count=len(active_events))}",
        reply_markup=keyboard,
    )
    return EVENT_MENU


async def event_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    i18n = _get_i18n(context)
    language = _get_user_language(context, query.from_user.id)
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]

    if action == "back_to_ev":
        return await _show_event_menu(query, context)
    if action == "back":
        return await _show_group_menu(query, context)

    if action == "create":
        context.user_data["event_draft"] = {}
        await query.edit_message_text(i18n.t(language, "admin_event_title_prompt"))
        return EVENT_CREATE_TITLE

    if action == "list":
        events = db.fetchall("SELECT * FROM events WHERE chat_id = ? AND status = 'active' ORDER BY id", (chat_id,))
        if not events:
            text = i18n.t(language, "admin_event_none")
        else:
            lines = []
            for ev in events:
                participants = db.fetchall("SELECT COUNT(*) as cnt FROM event_participants WHERE event_id = ?", (ev["id"],))
                cnt = participants[0]["cnt"] if participants else 0
                lines.append(f"🎉 {ev['title']} (👥 {cnt})")
            text = "\n".join(lines)
        await query.edit_message_text(text)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="ev:back_to_ev")]])
        await context.bot.send_message(chat_id=query.from_user.id, text=i18n.t(language, "admin_continue"), reply_markup=keyboard)
        return EVENT_MENU

    if action == "draw":
        events = db.fetchall("SELECT * FROM events WHERE chat_id = ? AND status = 'active' ORDER BY id", (chat_id,))
        if not events:
            await query.edit_message_text(i18n.t(language, "admin_event_none"))
            return EVENT_MENU
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(ev["title"], callback_data=f"evd:{ev['id']}")] for ev in events
        ])
        await query.edit_message_text(i18n.t(language, "admin_event_draw_select"), reply_markup=keyboard)
        return EVENT_MENU

    return EVENT_MENU


async def event_title_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["event_draft"]["title"] = update.message.text.strip()
    i18n = _get_i18n(context)
    language = _get_user_language(context, update.effective_user.id)
    await update.message.reply_text(i18n.t(language, "admin_event_desc_prompt"))
    return EVENT_CREATE_DESC


async def event_desc_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["event_draft"]["description"] = update.message.text.strip()
    i18n = _get_i18n(context)
    language = _get_user_language(context, update.effective_user.id)
    await update.message.reply_text(i18n.t(language, "admin_event_prize_prompt"))
    return EVENT_CREATE_PRIZE


async def event_prize_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["event_draft"]["prize"] = update.message.text.strip()
    i18n = _get_i18n(context)
    language = _get_user_language(context, update.effective_user.id)
    await update.message.reply_text(i18n.t(language, "admin_event_winners_prompt"))
    return EVENT_CREATE_WINNERS


async def event_winners_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    i18n = _get_i18n(context)
    language = _get_user_language(context, update.effective_user.id)
    try:
        count = int(update.message.text.strip())
        if count < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text(i18n.t(language, "admin_event_winners_invalid"))
        return EVENT_CREATE_WINNERS

    context.user_data["event_draft"]["winner_count"] = count
    await update.message.reply_text(i18n.t(language, "admin_event_time_prompt"))
    return EVENT_CREATE_TIME


async def event_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    i18n = _get_i18n(context)
    language = _get_user_language(context, update.effective_user.id)
    draft = context.user_data.get("event_draft", {})
    draft["end_time"] = update.message.text.strip()

    preview = (
        f"🎉 {draft.get('title', '')}\n"
        f"📝 {draft.get('description', '')}\n"
        f"🎁 {draft.get('prize', '')}\n"
        f"👑 {draft.get('winner_count', 1)}\n"
        f"⏰ {draft.get('end_time', '')}"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ " + i18n.t(language, "admin_event_confirm"), callback_data="evc:yes")],
        [InlineKeyboardButton("❌ " + i18n.t(language, "admin_event_cancel"), callback_data="evc:no")],
    ])
    await update.message.reply_text(preview, reply_markup=keyboard)
    return EVENT_CONFIRM


async def event_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    i18n = _get_i18n(context)
    language = _get_user_language(context, query.from_user.id)

    if action == "no":
        context.user_data.pop("event_draft", None)
        return await _show_event_menu(query, context)

    draft = context.user_data.pop("event_draft", {})
    now = _now_utc()
    db.execute(
        "INSERT INTO events (chat_id, title, description, prize, winner_count, status, end_time, created_by, created_at) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)",
        (chat_id, draft.get("title"), draft.get("description"), draft.get("prize"),
         draft.get("winner_count", 1), draft.get("end_time"), query.from_user.id, now),
    )
    db.commit()

    event = db.fetchone("SELECT * FROM events WHERE chat_id = ? ORDER BY id DESC LIMIT 1", (chat_id,))

    # Send to group
    event_text = (
        f"🎉 {draft.get('title', '')}\n\n"
        f"📝 {draft.get('description', '')}\n"
        f"🎁 {i18n.t(language, 'event_prize')}: {draft.get('prize', '')}\n"
        f"👑 {i18n.t(language, 'event_winners')}: {draft.get('winner_count', 1)}\n"
        f"⏰ {draft.get('end_time', '')}\n"
        f"👥 {i18n.t(language, 'event_participants')}: 0"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎰 " + i18n.t(language, "event_join"), callback_data=f"ej:{event['id']}")],
    ])
    try:
        target = int(chat_id) if chat_id.lstrip("-").isdigit() else f"@{chat_id}"
        msg = await context.bot.send_message(chat_id=target, text=event_text, reply_markup=keyboard)
        db.execute("UPDATE events SET message_id = ? WHERE id = ?", (msg.message_id, event["id"]))
        db.commit()
    except Exception as exc:
        logger.exception("Failed to send event to group: %s", exc)

    await query.edit_message_text(i18n.t(language, "admin_event_created"))
    return await _show_event_menu(query, context)


# ═══════════════════════════════════════════════════════════════════════════
# AI KNOWLEDGE BASE MODULE
# ═══════════════════════════════════════════════════════════════════════════

async def _show_ai_menu(query, context) -> int:
    i18n = _get_i18n(context)
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    language = _get_user_language(context, query.from_user.id)

    cfg = db.fetchone("SELECT * FROM ai_config WHERE chat_id = ?", (chat_id,))
    enabled = cfg["enabled"] if cfg else 0
    files = db.fetchall("SELECT * FROM knowledge_files WHERE chat_id = ? AND status = 'active'", (chat_id,))

    status_icon = "✅" if enabled else "❌"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            ("❌ " + i18n.t(language, "admin_disable") if enabled else "✅ " + i18n.t(language, "admin_enable")),
            callback_data="ai:toggle"
        )],
        [InlineKeyboardButton(f"📤 {i18n.t(language, 'admin_ai_upload')} ", callback_data="ai:upload")],
        [InlineKeyboardButton(f"📚 {i18n.t(language, 'admin_ai_files')} ({len(files)})", callback_data="ai:files")],
        [InlineKeyboardButton("📝 " + i18n.t(language, "admin_ai_prompt"), callback_data="ai:prompt")],
        [InlineKeyboardButton("📊 " + i18n.t(language, "admin_ai_usage"), callback_data="ai:usage")],
        [InlineKeyboardButton("⬅️ " + i18n.t(language, "admin_back"), callback_data="ai:back")],
    ])

    await query.edit_message_text(
        f"🧠 {i18n.t(language, 'admin_ai')}\n"
        f"{i18n.t(language, 'admin_status')}: {status_icon}\n"
        f"{i18n.t(language, 'admin_ai_file_count', count=len(files))}",
        reply_markup=keyboard,
    )
    return AI_MENU


async def ai_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    i18n = _get_i18n(context)
    language = _get_user_language(context, query.from_user.id)

    if action == "back_to_ai":
        return await _show_ai_menu(query, context)
    if action == "back":
        return await _show_group_menu(query, context)

    if action == "toggle":
        cfg = db.fetchone("SELECT * FROM ai_config WHERE chat_id = ?", (chat_id,))
        if cfg:
            new_val = 0 if cfg["enabled"] else 1
            db.execute("UPDATE ai_config SET enabled = ?, updated_at = ? WHERE chat_id = ?", (new_val, _now_utc(), chat_id))
        else:
            db.execute(
                "INSERT INTO ai_config (chat_id, enabled, updated_at) VALUES (?, 1, ?)",
                (chat_id, _now_utc()),
            )
        db.commit()
        return await _show_ai_menu(query, context)

    if action == "upload":
        await query.edit_message_text(i18n.t(language, "admin_ai_upload_prompt"))
        context.user_data["admin_awaiting_file"] = True
        return AI_UPLOAD_FILE

    if action == "files":
        files = db.fetchall("SELECT * FROM knowledge_files WHERE chat_id = ? AND status = 'active' ORDER BY id", (chat_id,))
        if not files:
            text = i18n.t(language, "admin_ai_no_files")
        else:
            lines = []
            for f in files:
                lines.append(f"📄 {f['file_name']} ({f['chunk_count']} chunks, {f['total_chars']} chars)")
            text = "\n".join(lines)
        await query.edit_message_text(text)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="ai:back_to_ai")]])
        await context.bot.send_message(chat_id=query.from_user.id, text=i18n.t(language, "admin_continue"), reply_markup=keyboard)
        return AI_MENU

    if action == "prompt":
        cfg = db.fetchone("SELECT system_prompt FROM ai_config WHERE chat_id = ?", (chat_id,))
        current = cfg["system_prompt"] if cfg else "You are a friendly community assistant."
        await query.edit_message_text(i18n.t(language, "admin_ai_prompt_input", current=current))
        return AI_SYSTEM_PROMPT_INPUT

    if action == "usage":
        stats = db.fetchone(
            "SELECT COUNT(*) as calls, COALESCE(SUM(total_tokens), 0) as tokens FROM ai_usage_log WHERE chat_id = ?",
            (chat_id,),
        )
        calls = stats["calls"] if stats else 0
        tokens = stats["tokens"] if stats else 0
        text = f"📊 {i18n.t(language, 'admin_ai_usage')}\n\n📞 {calls} calls\n🪙 {tokens} tokens"
        await query.edit_message_text(text)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="ai:back_to_ai")]])
        await context.bot.send_message(chat_id=query.from_user.id, text=i18n.t(language, "admin_continue"), reply_markup=keyboard)
        return AI_MENU

    return AI_MENU


async def ai_file_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle file uploads in the AI knowledge admin flow."""
    i18n = _get_i18n(context)
    language = _get_user_language(context, update.effective_user.id)

    if not update.message or not update.message.document:
        await update.message.reply_text(i18n.t(language, "admin_ai_upload_prompt"))
        return AI_UPLOAD_FILE

    doc = update.message.document
    file_name = doc.file_name or "unknown"
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

    if ext not in {"txt", "md", "pdf", "docx"}:
        await update.message.reply_text(i18n.t(language, "admin_ai_unsupported_format"))
        return AI_UPLOAD_FILE

    await update.message.reply_text(i18n.t(language, "admin_ai_parsing"))

    # Import file parser service
    from services.file_parser import parse_file
    from services.knowledge import store_file_chunks

    chat_id = context.user_data["admin_chat_id"]
    db = _get_db(context)

    # Download file
    import os
    upload_dir = os.path.join("data", "uploads", chat_id)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file_name)

    tg_file = await doc.get_file()
    await tg_file.download_to_drive(file_path)

    # Parse
    try:
        chunks = parse_file(file_path, ext)
    except Exception as exc:
        logger.exception("File parse error: %s", exc)
        await update.message.reply_text(i18n.t(language, "admin_ai_parse_error"))
        return AI_UPLOAD_FILE

    # Store
    total_chars = sum(len(c) for c in chunks)
    store_file_chunks(db, chat_id, file_name, ext, os.path.getsize(file_path), file_path,
                      chunks, update.effective_user.id)

    await update.message.reply_text(
        i18n.t(language, "admin_ai_upload_success", file_name=file_name, chunks=len(chunks), chars=total_chars)
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 " + i18n.t(language, "admin_ai_upload_more"), callback_data="ai:upload")],
        [InlineKeyboardButton("⬅️ Back", callback_data="ai:back_to_ai")],
    ])
    await update.message.reply_text(i18n.t(language, "admin_continue"), reply_markup=keyboard)
    return AI_MENU


async def ai_system_prompt_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = _get_db(context)
    chat_id = context.user_data["admin_chat_id"]
    i18n = _get_i18n(context)
    language = _get_user_language(context, update.effective_user.id)
    prompt = update.message.text.strip()

    cfg = db.fetchone("SELECT chat_id FROM ai_config WHERE chat_id = ?", (chat_id,))
    if cfg:
        db.execute("UPDATE ai_config SET system_prompt = ?, updated_at = ? WHERE chat_id = ?", (prompt, _now_utc(), chat_id))
    else:
        db.execute("INSERT INTO ai_config (chat_id, system_prompt, updated_at) VALUES (?, ?, ?)", (chat_id, prompt, _now_utc()))
    db.commit()

    await update.message.reply_text(i18n.t(language, "admin_ai_prompt_saved"))
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="ai:back_to_ai")]])
    await update.message.reply_text(i18n.t(language, "admin_continue"), reply_markup=keyboard)
    return AI_MENU


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel — exit admin conversation."""
    i18n = _get_i18n(context)
    language = _get_user_language(context, update.effective_user.id)
    await update.message.reply_text(i18n.t(language, "admin_cancelled"))
    context.user_data.pop("admin_chat_id", None)
    context.user_data.pop("event_draft", None)
    context.user_data.pop("qa_trigger", None)
    return ConversationHandler.END
