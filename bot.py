import logging
import os
import signal

from dotenv import load_dotenv
from telegram import BotCommand, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from handlers.admin import (
    AI_MENU,
    AI_SYSTEM_PROMPT_INPUT,
    AI_UPLOAD_FILE,
    COMMUNITY_MENU,
    COMMUNITY_PROXY_INPUT,
    COMMUNITY_WELCOME_INPUT,
    EVENT_CONFIRM,
    EVENT_CREATE_DESC,
    EVENT_CREATE_PRIZE,
    EVENT_CREATE_TIME,
    EVENT_CREATE_TITLE,
    EVENT_CREATE_WINNERS,
    EVENT_MENU,
    GROUP_MENU,
    QA_ADD_RESPONSE,
    QA_ADD_TRIGGER,
    QA_MENU,
    SELECT_GROUP,
    SPAM_BLACKLIST_INPUT,
    SPAM_MENU,
    SPAM_PUNISHMENT_SELECT,
    SPAM_WHITELIST_USER_INPUT,
    admin_command,
    ai_file_upload_handler,
    ai_menu_callback,
    ai_system_prompt_input,
    community_menu_callback,
    community_proxy_input,
    community_welcome_input,
    event_confirm_callback,
    event_desc_input,
    event_menu_callback,
    event_prize_input,
    event_time_input,
    event_title_input,
    event_winners_input,
    group_menu_callback,
    qa_add_response_input,
    qa_add_trigger_input,
    qa_menu_callback,
    select_group_callback,
    spam_blacklist_input,
    spam_menu_callback,
    spam_punishment_callback,
    spam_whitelist_input,
    cancel_command,
)
from handlers.ai_chat import ai_chat_handler, ask_command
from handlers.antispam import antispam_handler
from handlers.commands import (
    help_command,
    lang_command,
    language_switch_callback,
    status_command,
    stop_command,
)
from handlers.community import bot_added_handler, new_member_handler
from handlers.config import (
    CONFIRM,
    DEST_INPUT,
    DEST_TYPE,
    KEYWORDS_INPUT,
    KEYWORD_DEST_INPUT,
    KEYWORD_SOURCE_INPUT,
    LANG_SELECT,
    MONITOR_TYPE,
    REUSE_DEST,
    SOURCE_INPUT,
    config_command,
    confirm_callback,
    destination_input_handler,
    destination_type_callback,
    keyword_destination_input_handler,
    keyword_source_input_handler,
    keywords_input_handler,
    monitor_type_callback,
    reuse_destination_callback,
    source_input_handler,
)
from handlers.events import event_draw_callback, event_join_callback, events_command
from handlers.monitor import chat_member_update_handler, monitored_message_handler
from handlers.qa import faq_command, qa_handler
from handlers.start import language_select_callback, start_command
from utils.config_store import ConfigStore
from utils.database import Database
from utils.group_manager import GroupManager
from utils.i18n import I18n
from utils.logger import setup_logger

logger = logging.getLogger(__name__)


async def post_init(application) -> None:
    i18n = application.bot_data["i18n"]
    default_commands = [
        BotCommand("start", i18n.t("en", "command_start_desc")),
        BotCommand("status", i18n.t("en", "command_status_desc")),
        BotCommand("stop", i18n.t("en", "command_stop_desc")),
        BotCommand("config", i18n.t("en", "command_config_desc")),
        BotCommand("admin", "Open admin panel"),
        BotCommand("faq", "List group FAQ"),
        BotCommand("ask", "Ask AI a question"),
        BotCommand("events", "List active events"),
        BotCommand("lang", i18n.t("en", "command_lang_desc")),
        BotCommand("help", i18n.t("en", "command_help_desc")),
    ]
    zh_commands = [
        BotCommand("start", i18n.t("zh", "command_start_desc")),
        BotCommand("status", i18n.t("zh", "command_status_desc")),
        BotCommand("stop", i18n.t("zh", "command_stop_desc")),
        BotCommand("config", i18n.t("zh", "command_config_desc")),
        BotCommand("admin", "打开管理面板"),
        BotCommand("faq", "查看群FAQ"),
        BotCommand("ask", "向AI提问"),
        BotCommand("events", "查看进行中的活动"),
        BotCommand("lang", i18n.t("zh", "command_lang_desc")),
        BotCommand("help", i18n.t("zh", "command_help_desc")),
    ]

    await application.bot.set_my_commands(default_commands)
    await application.bot.set_my_commands(zh_commands, language_code="zh")


async def post_shutdown(application) -> None:
    store = application.bot_data.get("config_store")
    if store:
        store.save()
    db = application.bot_data.get("db")
    if db:
        db.close()


async def error_handler(update, context) -> None:
    logger.exception("Unhandled error while processing update %s", update, exc_info=context.error)


def build_application(token: str):
    # Init core services
    store = ConfigStore("user_configs.json")
    i18n = I18n("i18n")
    db = Database("data/bot.db")
    gm = GroupManager(db)

    application = (
        ApplicationBuilder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.bot_data["config_store"] = store
    application.bot_data["i18n"] = i18n
    application.bot_data["db"] = db
    application.bot_data["group_manager"] = gm

    # ─── Existing setup flow (monitor config) ────────────────────────────
    setup_flow = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_command),
            CommandHandler("config", config_command),
        ],
        states={
            LANG_SELECT: [
                CallbackQueryHandler(language_select_callback, pattern=r"^set_lang:(en|zh)$"),
            ],
            MONITOR_TYPE: [
                CallbackQueryHandler(monitor_type_callback, pattern=r"^monitor:(person|keyword)$"),
            ],
            SOURCE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, source_input_handler),
            ],
            DEST_TYPE: [
                CallbackQueryHandler(destination_type_callback, pattern=r"^dest:(lark|telegram)$"),
            ],
            DEST_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, destination_input_handler),
            ],
            KEYWORD_SOURCE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, keyword_source_input_handler),
            ],
            KEYWORDS_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, keywords_input_handler),
            ],
            KEYWORD_DEST_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, keyword_destination_input_handler),
            ],
            REUSE_DEST: [
                CallbackQueryHandler(reuse_destination_callback, pattern=r"^reuse_dest:(yes|no)$"),
            ],
            CONFIRM: [
                CallbackQueryHandler(confirm_callback, pattern=r"^confirm:(start|reconfigure)$"),
            ],
        },
        fallbacks=[
            CommandHandler("help", help_command),
            CommandHandler("status", status_command),
            CommandHandler("stop", stop_command),
            CommandHandler("lang", lang_command),
            CommandHandler("config", config_command),
            CommandHandler("start", start_command),
        ],
        allow_reentry=True,
    )

    # ─── Admin flow ──────────────────────────────────────────────────────
    admin_flow = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_command)],
        states={
            SELECT_GROUP: [
                CallbackQueryHandler(select_group_callback, pattern=r"^ag:"),
            ],
            GROUP_MENU: [
                CallbackQueryHandler(group_menu_callback, pattern=r"^am:"),
            ],
            # Anti-spam
            SPAM_MENU: [
                CallbackQueryHandler(spam_menu_callback, pattern=r"^sp:"),
            ],
            SPAM_BLACKLIST_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, spam_blacklist_input),
            ],
            SPAM_PUNISHMENT_SELECT: [
                CallbackQueryHandler(spam_punishment_callback, pattern=r"^spp:"),
            ],
            SPAM_WHITELIST_USER_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, spam_whitelist_input),
            ],
            # Q&A
            QA_MENU: [
                CallbackQueryHandler(qa_menu_callback, pattern=r"^qa:"),
            ],
            QA_ADD_TRIGGER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, qa_add_trigger_input),
            ],
            QA_ADD_RESPONSE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, qa_add_response_input),
            ],
            # Community
            COMMUNITY_MENU: [
                CallbackQueryHandler(community_menu_callback, pattern=r"^cm:"),
            ],
            COMMUNITY_WELCOME_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, community_welcome_input),
            ],
            COMMUNITY_PROXY_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, community_proxy_input),
            ],
            # Events
            EVENT_MENU: [
                CallbackQueryHandler(event_menu_callback, pattern=r"^ev:"),
            ],
            EVENT_CREATE_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, event_title_input),
            ],
            EVENT_CREATE_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, event_desc_input),
            ],
            EVENT_CREATE_PRIZE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, event_prize_input),
            ],
            EVENT_CREATE_WINNERS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, event_winners_input),
            ],
            EVENT_CREATE_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, event_time_input),
            ],
            EVENT_CONFIRM: [
                CallbackQueryHandler(event_confirm_callback, pattern=r"^evc:"),
            ],
            # AI
            AI_MENU: [
                CallbackQueryHandler(ai_menu_callback, pattern=r"^ai:"),
            ],
            AI_UPLOAD_FILE: [
                MessageHandler(filters.Document.ALL, ai_file_upload_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ai_file_upload_handler),
            ],
            AI_SYSTEM_PROMPT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ai_system_prompt_input),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CommandHandler("admin", admin_command),
            CommandHandler("help", help_command),
        ],
        allow_reentry=True,
        conversation_timeout=300,
    )

    application.add_handler(setup_flow)
    application.add_handler(admin_flow)

    # ─── Standalone commands ─────────────────────────────────────────────
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("lang", lang_command))
    application.add_handler(CommandHandler("config", config_command))
    application.add_handler(CommandHandler("faq", faq_command))
    application.add_handler(CommandHandler("ask", ask_command))
    application.add_handler(CommandHandler("events", events_command))
    application.add_handler(CallbackQueryHandler(language_switch_callback, pattern=r"^switch_lang:(en|zh)$"))

    # ─── Event join/draw callbacks ───────────────────────────────────────
    application.add_handler(CallbackQueryHandler(event_join_callback, pattern=r"^ej:"))
    application.add_handler(CallbackQueryHandler(event_draw_callback, pattern=r"^evd:"))

    # ─── Group message handlers (ordered by priority) ────────────────────
    # group=0: Anti-spam (highest priority)
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, antispam_handler), group=0)

    # group=1: Q&A rules
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, qa_handler), group=1)

    # group=2: AI chat (knowledge base responses)
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, ai_chat_handler), group=2)

    # group=3: Original message monitoring/forwarding
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, monitored_message_handler), group=3)

    # ─── New member / bot added handlers ─────────────────────────────────
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.StatusUpdate.NEW_CHAT_MEMBERS,
        new_member_handler
    ), group=4)

    application.add_handler(ChatMemberHandler(bot_added_handler, ChatMemberHandler.MY_CHAT_MEMBER), group=5)
    application.add_handler(ChatMemberHandler(chat_member_update_handler, ChatMemberHandler.MY_CHAT_MEMBER), group=6)

    application.add_error_handler(error_handler)
    return application


def main() -> None:
    load_dotenv()
    setup_logger("bot.log")

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set. Please provide it in your environment or .env file.")

    app = build_application(token)
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        stop_signals=(signal.SIGINT, signal.SIGTERM),
    )


if __name__ == "__main__":
    main()
