"""Comprehensive test suite for the community management bot.

Covers: Database, GroupManager, AntiSpam, Q&A, Events, FileParser, Knowledge, AI Chat, i18n
Run with: python -m pytest tests/test_all.py -v
Or simply: python tests/test_all.py
"""

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ═══════════════════════════════════════════════════════════════════════════
# T1: Database & Schema
# ═══════════════════════════════════════════════════════════════════════════
class TestDatabase(unittest.TestCase):
    """Verify schema creation, CRUD, and edge cases."""

    def setUp(self):
        from utils.database import Database
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = Database(self.tmp.name)

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def test_schema_tables_exist(self):
        """All expected tables should be created on init."""
        tables = self.db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        names = {t["name"] for t in tables}
        expected = {
            "groups", "group_admins", "spam_config", "qa_rules", "chat_config",
            "scheduled_messages", "events", "event_participants", "moderation_log",
            "monitor_config", "knowledge_files", "knowledge_chunks",
            "ai_config", "ai_usage_log", "schema_meta",
        }
        self.assertTrue(expected.issubset(names), f"Missing tables: {expected - names}")

    def test_schema_version(self):
        row = self.db.fetchone("SELECT value FROM schema_meta WHERE key = 'version'")
        self.assertIsNotNone(row)
        self.assertEqual(row["value"], "1")

    def test_fetchone_returns_none_for_empty(self):
        row = self.db.fetchone("SELECT * FROM groups WHERE chat_id = 'nonexistent'")
        self.assertIsNone(row)

    def test_fetchall_returns_empty_list(self):
        rows = self.db.fetchall("SELECT * FROM groups")
        self.assertEqual(rows, [])

    def test_insert_and_read(self):
        self.db.execute(
            "INSERT INTO groups (chat_id, chat_title, added_by, language) VALUES (?, ?, ?, ?)",
            ("-100123", "Test Group", 42, "zh"),
        )
        self.db.commit()
        row = self.db.fetchone("SELECT * FROM groups WHERE chat_id = '-100123'")
        self.assertIsNotNone(row)
        self.assertEqual(row["chat_title"], "Test Group")
        self.assertEqual(row["added_by"], 42)
        self.assertEqual(row["language"], "zh")

    def test_executemany(self):
        params = [("-1001", "G1", 1, "en"), ("-1002", "G2", 2, "zh")]
        self.db.executemany(
            "INSERT INTO groups (chat_id, chat_title, added_by, language) VALUES (?, ?, ?, ?)",
            params,
        )
        self.db.commit()
        rows = self.db.fetchall("SELECT * FROM groups ORDER BY chat_id")
        self.assertEqual(len(rows), 2)


# ═══════════════════════════════════════════════════════════════════════════
# T2: GroupManager
# ═══════════════════════════════════════════════════════════════════════════
class TestGroupManager(unittest.TestCase):
    def setUp(self):
        from utils.database import Database
        from utils.group_manager import GroupManager
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = Database(self.tmp.name)
        self.gm = GroupManager(self.db)

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def test_register_and_get_group(self):
        self.gm.register_group(-100123, "My Group", added_by=42, language="zh")
        g = self.gm.get_group(-100123)
        self.assertIsNotNone(g)
        self.assertEqual(g["chat_title"], "My Group")
        self.assertEqual(g["language"], "zh")

    def test_register_group_upserts(self):
        self.gm.register_group(-100123, "Old Name", added_by=42)
        self.gm.register_group(-100123, "New Name", added_by=42)
        g = self.gm.get_group(-100123)
        self.assertEqual(g["chat_title"], "New Name")

    def test_remove_group(self):
        self.gm.register_group(-100123, "G", added_by=42)
        self.gm.remove_group(-100123)
        self.assertIsNone(self.gm.get_group(-100123))

    def test_admin_management(self):
        self.gm.register_group(-100123, "G", added_by=42)
        self.assertTrue(self.gm.is_admin(-100123, 42))  # owner auto-added
        self.assertFalse(self.gm.is_admin(-100123, 99))

        self.gm.add_admin(-100123, 99)
        self.assertTrue(self.gm.is_admin(-100123, 99))

        self.gm.remove_admin(-100123, 99)
        self.assertFalse(self.gm.is_admin(-100123, 99))

    def test_get_user_groups(self):
        self.gm.register_group(-100, "G1", added_by=42)
        self.gm.register_group(-200, "G2", added_by=42)
        self.gm.register_group(-300, "G3", added_by=99)

        groups = self.gm.get_user_groups(42)
        self.assertEqual(len(groups), 2)

    def test_language_helpers(self):
        self.gm.register_group(-100, "G", added_by=42, language="en")
        self.assertEqual(self.gm.get_group_language(-100), "en")
        self.gm.set_group_language(-100, "zh")
        self.assertEqual(self.gm.get_group_language(-100), "zh")
        # Invalid language defaults to en
        self.gm.set_group_language(-100, "fr")
        self.assertEqual(self.gm.get_group_language(-100), "en")

    def test_get_group_language_missing_group(self):
        self.assertEqual(self.gm.get_group_language(-99999), "en")


# ═══════════════════════════════════════════════════════════════════════════
# T3: Anti-Spam
# ═══════════════════════════════════════════════════════════════════════════
class TestAntiSpam(unittest.TestCase):
    def setUp(self):
        from utils.database import Database
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = Database(self.tmp.name)
        # Reset module-level state
        import services.antispam as mod
        mod._recent_messages.clear()

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def _enable_spam(self, chat_id, **overrides):
        defaults = dict(
            chat_id=chat_id, enabled=1, keyword_blacklist='[]',
            link_filter=0, link_whitelist='[]', newbie_restrict=0,
            repeat_detect=0, punishment='delete_warn', whitelist_users='[]',
        )
        defaults.update(overrides)
        cols = ", ".join(defaults.keys())
        placeholders = ", ".join("?" for _ in defaults)
        self.db.execute(
            f"INSERT OR REPLACE INTO spam_config ({cols}) VALUES ({placeholders})",
            tuple(defaults.values()),
        )
        self.db.commit()

    def test_no_config_returns_none(self):
        from services.antispam import check_spam
        result = check_spam(self.db, "-100", 42, "alice", "hello")
        self.assertIsNone(result)

    def test_disabled_config_returns_none(self):
        from services.antispam import check_spam
        self._enable_spam("-100", enabled=0)
        result = check_spam(self.db, "-100", 42, "alice", "hello")
        self.assertIsNone(result)

    def test_keyword_blacklist_match(self):
        from services.antispam import check_spam
        self._enable_spam("-100", keyword_blacklist='["spam", "scam"]')
        result = check_spam(self.db, "-100", 42, "alice", "This is a SCAM!")
        self.assertIsNotNone(result)
        self.assertIn("scam", result["reason"].lower())

    def test_keyword_blacklist_no_match(self):
        from services.antispam import check_spam
        self._enable_spam("-100", keyword_blacklist='["spam"]')
        result = check_spam(self.db, "-100", 42, "alice", "Hello everyone!")
        self.assertIsNone(result)

    def test_link_filter_blocks_url(self):
        from services.antispam import check_spam
        self._enable_spam("-100", link_filter=1)
        result = check_spam(self.db, "-100", 42, "alice", "Check https://evil.com")
        self.assertIsNotNone(result)
        self.assertIn("link", result["reason"].lower())

    def test_link_filter_allows_whitelisted(self):
        from services.antispam import check_spam
        self._enable_spam("-100", link_filter=1, link_whitelist='["telegram.org"]')
        result = check_spam(self.db, "-100", 42, "alice", "Visit https://telegram.org/docs")
        self.assertIsNone(result)

    def test_repeat_detection(self):
        from services.antispam import check_spam
        self._enable_spam("-100", repeat_detect=1, repeat_threshold=3, repeat_window_sec=60)
        check_spam(self.db, "-100", 42, "alice", "buy now")
        check_spam(self.db, "-100", 42, "alice", "buy now")
        result = check_spam(self.db, "-100", 42, "alice", "buy now")  # 3rd
        self.assertIsNotNone(result)
        self.assertIn("repeat", result["reason"].lower())

    def test_whitelist_bypasses_checks(self):
        from services.antispam import check_spam
        self._enable_spam("-100", keyword_blacklist='["spam"]', whitelist_users='["alice"]')
        result = check_spam(self.db, "-100", 42, "alice", "This is spam!")
        self.assertIsNone(result)

    def test_whitelist_by_user_id(self):
        from services.antispam import check_spam
        self._enable_spam("-100", keyword_blacklist='["spam"]', whitelist_users='["42"]')
        result = check_spam(self.db, "-100", 42, "alice", "This is spam!")
        self.assertIsNone(result)

    def test_log_moderation(self):
        from services.antispam import log_moderation
        log_moderation(self.db, "-100", 42, "delete_warn", "test", "bad message")
        row = self.db.fetchone("SELECT * FROM moderation_log WHERE chat_id = '-100'")
        self.assertIsNotNone(row)
        self.assertEqual(row["action"], "delete_warn")


# ═══════════════════════════════════════════════════════════════════════════
# T4: Q&A Service
# ═══════════════════════════════════════════════════════════════════════════
class TestQA(unittest.TestCase):
    def setUp(self):
        from utils.database import Database
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = Database(self.tmp.name)
        # Reset cooldowns
        import services.qa as mod
        mod._cooldowns.clear()

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def _add_rule(self, chat_id, trigger, response, match_mode="fuzzy", cooldown=0):
        self.db.execute(
            "INSERT INTO qa_rules (chat_id, trigger_text, response_text, match_mode, cooldown_sec, enabled) VALUES (?, ?, ?, ?, ?, 1)",
            (chat_id, trigger, response, match_mode, cooldown),
        )
        self.db.commit()

    def test_fuzzy_match(self):
        from services.qa import find_matching_rule
        self._add_rule("-100", "price", "The price is $99.", "fuzzy")
        result = find_matching_rule(self.db, "-100", "What is the price?")
        self.assertIsNotNone(result)
        self.assertEqual(result["response_text"], "The price is $99.")

    def test_exact_match_hits(self):
        from services.qa import find_matching_rule
        self._add_rule("-100", "hello", "Hi there!", "exact")
        result = find_matching_rule(self.db, "-100", "hello")
        self.assertIsNotNone(result)

    def test_exact_match_misses(self):
        from services.qa import find_matching_rule
        self._add_rule("-100", "hello", "Hi!", "exact")
        result = find_matching_rule(self.db, "-100", "hello world")
        self.assertIsNone(result)

    def test_no_rules_returns_none(self):
        from services.qa import find_matching_rule
        result = find_matching_rule(self.db, "-100", "anything")
        self.assertIsNone(result)

    def test_cooldown_blocks_rapid_triggers(self):
        from services.qa import find_matching_rule
        self._add_rule("-100", "help", "How can I help?", cooldown=60)
        r1 = find_matching_rule(self.db, "-100", "help me")
        self.assertIsNotNone(r1)
        r2 = find_matching_rule(self.db, "-100", "help again")
        self.assertIsNone(r2)  # blocked by cooldown

    def test_case_insensitive(self):
        from services.qa import find_matching_rule
        self._add_rule("-100", "BITCOIN", "BTC info here")
        result = find_matching_rule(self.db, "-100", "tell me about bitcoin")
        self.assertIsNotNone(result)


# ═══════════════════════════════════════════════════════════════════════════
# T5: Events Service
# ═══════════════════════════════════════════════════════════════════════════
class TestEvents(unittest.TestCase):
    def setUp(self):
        from utils.database import Database
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = Database(self.tmp.name)
        self._create_event()

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def _create_event(self, chat_id="-100", winner_count=1, status="active"):
        self.db.execute(
            "INSERT INTO events (chat_id, title, description, prize, winner_count, status, created_by, created_at) "
            "VALUES (?, 'Test Event', 'Desc', 'Prize', ?, ?, 1, '2025-01-01')",
            (chat_id, winner_count, status),
        )
        self.db.commit()

    def test_join_event_new(self):
        from services.events import join_event
        result = join_event(self.db, 1, 42, "alice", "Alice")
        self.assertTrue(result)

    def test_join_event_duplicate(self):
        from services.events import join_event
        join_event(self.db, 1, 42, "alice", "Alice")
        result = join_event(self.db, 1, 42, "alice", "Alice")
        self.assertFalse(result)

    def test_participant_count(self):
        from services.events import get_participant_count, join_event
        join_event(self.db, 1, 42, "alice", "Alice")
        join_event(self.db, 1, 43, "bob", "Bob")
        self.assertEqual(get_participant_count(self.db, 1), 2)

    def test_draw_winners(self):
        from services.events import draw_winners, join_event
        join_event(self.db, 1, 42, "alice", "Alice")
        join_event(self.db, 1, 43, "bob", "Bob")
        join_event(self.db, 1, 44, "charlie", "Charlie")
        winners = draw_winners(self.db, 1)
        self.assertEqual(len(winners), 1)
        # Event should be marked drawn
        event = self.db.fetchone("SELECT status FROM events WHERE id = 1")
        self.assertEqual(event["status"], "drawn")

    def test_draw_no_participants(self):
        from services.events import draw_winners
        winners = draw_winners(self.db, 1)
        self.assertEqual(winners, [])

    def test_draw_after_drawn_returns_empty(self):
        from services.events import draw_winners, join_event
        join_event(self.db, 1, 42, "alice", "Alice")
        draw_winners(self.db, 1)
        # Second draw should fail
        winners = draw_winners(self.db, 1)
        self.assertEqual(winners, [])

    def test_get_active_events(self):
        from services.events import get_active_events
        events = get_active_events(self.db, "-100")
        self.assertEqual(len(events), 1)

    def test_multiple_winners(self):
        from services.events import draw_winners, join_event
        # Create event with 3 winners
        self.db.execute(
            "INSERT INTO events (chat_id, title, prize, winner_count, status, created_by, created_at) "
            "VALUES ('-200', 'Big Event', 'Prize', 3, 'active', 1, '2025-01-01')"
        )
        self.db.commit()
        ev = self.db.fetchone("SELECT id FROM events WHERE chat_id = '-200'")
        for i in range(10):
            join_event(self.db, ev["id"], 100 + i, f"user{i}", f"User {i}")
        winners = draw_winners(self.db, ev["id"])
        self.assertEqual(len(winners), 3)


# ═══════════════════════════════════════════════════════════════════════════
# T6: File Parser
# ═══════════════════════════════════════════════════════════════════════════
class TestFileParser(unittest.TestCase):

    def test_parse_txt_file(self):
        from services.file_parser import parse_file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("Hello world.\n\nThis is a test document.\n\nIt has three paragraphs.")
            f.flush()
            chunks = parse_file(f.name, "txt")
        os.unlink(f.name)
        self.assertGreater(len(chunks), 0)
        self.assertIn("Hello world", chunks[0])

    def test_parse_md_file(self):
        from services.file_parser import parse_file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# Title\n\nSome markdown content.\n\n## Section\n\nMore content here.")
            f.flush()
            chunks = parse_file(f.name, "md")
        os.unlink(f.name)
        self.assertGreater(len(chunks), 0)

    def test_parse_empty_file(self):
        from services.file_parser import parse_file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("")
            f.flush()
            chunks = parse_file(f.name, "txt")
        os.unlink(f.name)
        self.assertEqual(chunks, [])

    def test_chunking_long_text(self):
        from services.file_parser import _split_into_chunks
        long_text = ("Paragraph content. " * 100 + "\n\n") * 10
        chunks = _split_into_chunks(long_text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 900)  # some tolerance

    def test_extract_keywords(self):
        from services.file_parser import extract_keywords
        text = "Bitcoin is blockchain technology. Bitcoin uses cryptographic hashing. Ethereum is also blockchain."
        keywords = extract_keywords(text)
        self.assertIn("bitcoin", keywords)
        self.assertIn("blockchain", keywords)

    def test_extract_keywords_chinese(self):
        from services.file_parser import extract_keywords
        text = "区块链技术是去中心化的。区块链可以用于加密货币交易。"
        keywords = extract_keywords(text)
        self.assertGreater(len(keywords), 0)

    def test_unsupported_format(self):
        from services.file_parser import _extract_text
        with self.assertRaises(ValueError):
            _extract_text("/tmp/test.xyz", "xyz")

    def test_clean_text(self):
        from services.file_parser import _clean_text
        dirty = "hello     world\n\n\n\n\ngoodbye"
        clean = _clean_text(dirty)
        self.assertNotIn("\n\n\n", clean)
        self.assertNotIn("     ", clean)


# ═══════════════════════════════════════════════════════════════════════════
# T7: Knowledge Store & BM25 Retrieval
# ═══════════════════════════════════════════════════════════════════════════
class TestKnowledge(unittest.TestCase):
    def setUp(self):
        from utils.database import Database
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = Database(self.tmp.name)

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def test_store_and_retrieve_chunks(self):
        from services.knowledge import has_knowledge, store_file_chunks
        chunks = ["Bitcoin is a cryptocurrency.", "Ethereum supports smart contracts.", "Blockchain is decentralized."]
        file_id = store_file_chunks(self.db, "-100", "test.txt", "txt", 100, "/tmp/test.txt", chunks, 42)
        self.assertGreater(file_id, 0)
        self.assertTrue(has_knowledge(self.db, "-100"))

    def test_bm25_retrieval_relevance(self):
        from services.knowledge import retrieve_context, store_file_chunks
        chunks = [
            "Bitcoin is a decentralized digital currency.",
            "Ethereum uses smart contracts for automation.",
            "Weather today is sunny and warm.",
            "Python is a popular programming language.",
        ]
        store_file_chunks(self.db, "-100", "test.txt", "txt", 100, "/tmp/test.txt", chunks, 42)
        context = retrieve_context(self.db, "-100", "What is Bitcoin?")
        self.assertIn("Bitcoin", context)

    def test_retrieve_empty_knowledge(self):
        from services.knowledge import retrieve_context
        context = retrieve_context(self.db, "-100", "anything")
        self.assertEqual(context, "")

    def test_has_knowledge_false(self):
        from services.knowledge import has_knowledge
        self.assertFalse(has_knowledge(self.db, "-100"))

    def test_delete_file(self):
        from services.knowledge import delete_file, has_knowledge, store_file_chunks
        store_file_chunks(self.db, "-100", "test.txt", "txt", 100, "/tmp/test.txt", ["chunk1"], 42)
        file_row = self.db.fetchone("SELECT id FROM knowledge_files WHERE chat_id = '-100'")
        delete_file(self.db, file_row["id"])
        self.assertFalse(has_knowledge(self.db, "-100"))
        # Chunks should be deleted
        cnt = self.db.fetchone("SELECT COUNT(*) as c FROM knowledge_chunks WHERE chat_id = '-100'")
        self.assertEqual(cnt["c"], 0)

    def test_tokenize(self):
        from services.knowledge import _tokenize
        tokens = _tokenize("Hello World! 区块链 is great")
        self.assertIn("hello", tokens)
        self.assertIn("world", tokens)
        self.assertIn("great", tokens)


# ═══════════════════════════════════════════════════════════════════════════
# T8: AI Chat — Intent Detection
# ═══════════════════════════════════════════════════════════════════════════
class TestAIChat(unittest.TestCase):
    def setUp(self):
        from utils.database import Database
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = Database(self.tmp.name)
        # Reset memory
        import services.ai_chat as mod
        mod._chat_memory.clear()

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def _enable_ai(self, chat_id, trigger_mode="all"):
        self.db.execute(
            "INSERT INTO ai_config (chat_id, enabled, trigger_mode) VALUES (?, 1, ?)",
            (chat_id, trigger_mode),
        )
        self.db.commit()

    def test_should_respond_to_mention(self):
        from services.ai_chat import should_ai_respond
        self._enable_ai("-100")
        self.assertTrue(should_ai_respond(self.db, "-100", "hello", is_mention=True, is_ask_command=False))

    def test_should_respond_to_ask_command(self):
        from services.ai_chat import should_ai_respond
        self._enable_ai("-100")
        self.assertTrue(should_ai_respond(self.db, "-100", "hello", is_mention=False, is_ask_command=True))

    def test_should_respond_question_all_mode(self):
        from services.ai_chat import should_ai_respond
        self._enable_ai("-100", "all")
        self.assertTrue(should_ai_respond(self.db, "-100", "What is Bitcoin?", is_mention=False, is_ask_command=False))
        self.assertTrue(should_ai_respond(self.db, "-100", "比特币是什么？", is_mention=False, is_ask_command=False))

    def test_should_not_respond_statement_all_mode(self):
        from services.ai_chat import should_ai_respond
        self._enable_ai("-100", "all")
        self.assertFalse(should_ai_respond(self.db, "-100", "Good morning!", is_mention=False, is_ask_command=False))

    def test_should_not_respond_disabled(self):
        from services.ai_chat import should_ai_respond
        # No config at all
        self.assertFalse(should_ai_respond(self.db, "-100", "What is Bitcoin?", is_mention=False, is_ask_command=False))

    def test_mention_mode(self):
        from services.ai_chat import should_ai_respond
        self._enable_ai("-100", "mention")
        self.assertFalse(should_ai_respond(self.db, "-100", "What is Bitcoin?", is_mention=False, is_ask_command=False))
        self.assertTrue(should_ai_respond(self.db, "-100", "What is Bitcoin?", is_mention=True, is_ask_command=False))

    def test_keyword_mode(self):
        from services.ai_chat import should_ai_respond
        self.db.execute(
            "INSERT INTO ai_config (chat_id, enabled, trigger_mode, trigger_keywords) VALUES (?, 1, 'keyword', ?)",
            ("-100", '["bitcoin", "crypto"]'),
        )
        self.db.commit()
        self.assertTrue(should_ai_respond(self.db, "-100", "Tell me about Bitcoin", is_mention=False, is_ask_command=False))
        self.assertFalse(should_ai_respond(self.db, "-100", "Hello world", is_mention=False, is_ask_command=False))

    def test_conversation_memory(self):
        from services.ai_chat import _add_to_history, _get_history
        _add_to_history("-100", 42, "user", "Hello")
        _add_to_history("-100", 42, "assistant", "Hi there!")
        history = _get_history("-100", 42)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "assistant")

    def test_memory_bounds(self):
        from services.ai_chat import MEMORY_MAX_ROUNDS, _add_to_history, _get_history
        for i in range(20):
            _add_to_history("-100", 42, "user", f"msg {i}")
            _add_to_history("-100", 42, "assistant", f"reply {i}")
        history = _get_history("-100", 42)
        self.assertLessEqual(len(history), MEMORY_MAX_ROUNDS * 2)


# ═══════════════════════════════════════════════════════════════════════════
# T9: Community Service
# ═══════════════════════════════════════════════════════════════════════════
class TestCommunity(unittest.TestCase):
    def test_format_welcome_basic(self):
        from services.community import format_welcome
        result = format_welcome("Welcome {name} to {group}!", "Alice", "My Group")
        self.assertEqual(result, "Welcome Alice to My Group!")

    def test_format_welcome_no_placeholders(self):
        from services.community import format_welcome
        result = format_welcome("Welcome to the community!", "Alice", "G")
        self.assertEqual(result, "Welcome to the community!")

    def test_format_welcome_missing_key(self):
        from services.community import format_welcome
        # Should not crash even with extra/missing keys
        result = format_welcome("{name} joined {group} - {extra}", "Alice", "G")
        self.assertIn("Alice", result)


# ═══════════════════════════════════════════════════════════════════════════
# T10: i18n
# ═══════════════════════════════════════════════════════════════════════════
class TestI18n(unittest.TestCase):
    def setUp(self):
        from utils.i18n import I18n
        self.i18n = I18n("i18n")

    def test_en_key_exists(self):
        result = self.i18n.t("en", "admin_antispam")
        self.assertEqual(result, "Anti-Spam")

    def test_zh_key_exists(self):
        result = self.i18n.t("zh", "admin_antispam")
        self.assertEqual(result, "反垃圾")

    def test_unknown_key_returns_key(self):
        result = self.i18n.t("en", "nonexistent_key_xyz")
        self.assertEqual(result, "nonexistent_key_xyz")

    def test_fallback_to_en(self):
        result = self.i18n.t("fr", "admin_antispam")
        self.assertEqual(result, "Anti-Spam")

    def test_formatting(self):
        result = self.i18n.t("en", "admin_qa_count", count=5)
        self.assertEqual(result, "Rules: 5")

    def test_all_new_keys_exist_in_both_languages(self):
        """Every new admin key in en.json should also exist in zh.json."""
        new_keys = [
            "admin_no_groups", "admin_select_group", "admin_choose_module",
            "admin_antispam", "admin_qa", "admin_ai", "admin_community",
            "admin_events", "admin_back", "admin_enable", "admin_disable",
            "admin_spam_blacklist", "admin_qa_add", "admin_event_create",
            "admin_ai_upload", "ask_usage", "ai_error",
        ]
        for key in new_keys:
            en_val = self.i18n.t("en", key)
            zh_val = self.i18n.t("zh", key)
            self.assertNotEqual(en_val, key, f"Missing en key: {key}")
            self.assertNotEqual(zh_val, key, f"Missing zh key: {key}")


# ═══════════════════════════════════════════════════════════════════════════
# T11: Migration Script
# ═══════════════════════════════════════════════════════════════════════════
class TestMigration(unittest.TestCase):
    def test_migrate_from_json(self):
        from scripts.migrate_json_to_sqlite import migrate
        # Create temp JSON
        config = {
            "12345": {
                "language": "en",
                "source": {"group": "@test", "user_id": 42},
                "destination": {"type": "lark", "url": "https://example.com/hook"},
                "active": True,
                "keywords": ["btc"],
                "keyword_source": {"group": "@crypto"},
                "keyword_destination": {"type": "telegram", "group": "@alerts"},
                "keyword_active": True,
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f)
            json_path = f.name

        db_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_tmp.close()

        migrate(json_path, db_tmp.name)

        from utils.database import Database
        db = Database(db_tmp.name)
        rows = db.fetchall("SELECT * FROM monitor_config ORDER BY id")
        self.assertEqual(len(rows), 2)  # person + keyword
        self.assertEqual(rows[0]["monitor_type"], "person")
        self.assertEqual(rows[1]["monitor_type"], "keyword")
        db.close()

        os.unlink(json_path)
        os.unlink(db_tmp.name)

    def test_migrate_missing_file(self):
        """Should not crash if source file doesn't exist."""
        from scripts.migrate_json_to_sqlite import migrate
        db_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_tmp.close()
        migrate("/tmp/nonexistent_xyz.json", db_tmp.name)
        os.unlink(db_tmp.name)


# ═══════════════════════════════════════════════════════════════════════════
# T12: DeepSeek Client (mocked)
# ═══════════════════════════════════════════════════════════════════════════
class TestDeepSeek(unittest.TestCase):
    def test_rate_limiter(self):
        from services.deepseek import _check_rate_limit, _rate_tracker
        _rate_tracker.clear()
        for i in range(10):
            self.assertTrue(_check_rate_limit("-100"))
        # 11th should be rejected
        self.assertFalse(_check_rate_limit("-100"))

    def test_call_deepseek_success(self):
        """Mock successful API call."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from services.deepseek import _rate_tracker, call_deepseek
            _rate_tracker.clear()

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Test answer"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }

            with patch("httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                MockClient.return_value = mock_client

                result = loop.run_until_complete(call_deepseek(
                    system_prompt="You are a helper",
                    knowledge_context="Test context",
                    chat_history=[],
                    user_question="What is X?",
                    api_key="test-key",
                    chat_id="-100",
                ))

            self.assertEqual(result["content"], "Test answer")
            self.assertEqual(result["total_tokens"], 15)
        finally:
            loop.close()


# ═══════════════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    unittest.main(verbosity=2)
