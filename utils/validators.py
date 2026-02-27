from __future__ import annotations

import re
from typing import Any


ID_PATTERN = re.compile(r"^-?\d+$")
USERNAME_PATTERN = re.compile(r"^@?[A-Za-z0-9_]{5,32}$")
GROUP_LINE_PATTERN = re.compile(r"^(group|群组|群組)\s*[:：]\s*(.+)$", re.IGNORECASE)
USER_LINE_PATTERN = re.compile(r"^(user|用户)\s*[:：]\s*(.+)$", re.IGNORECASE)


def parse_source_input(text: str) -> dict[str, dict[str, str]] | None:
    group_value = None
    user_value = None

    for line in text.splitlines():
        clean_line = line.strip()
        if not clean_line:
            continue

        group_match = GROUP_LINE_PATTERN.match(clean_line)
        if group_match:
            group_value = group_match.group(2).strip()
            continue

        user_match = USER_LINE_PATTERN.match(clean_line)
        if user_match:
            user_value = user_match.group(2).strip()
            continue

    if not group_value or not user_value:
        return None

    group_identifier = parse_telegram_chat_identifier(group_value)
    user_identifier = parse_user_identifier(user_value)

    if not group_identifier or not user_identifier:
        return None

    return {"group": group_identifier, "user": user_identifier}


def parse_group_input(text: str) -> dict[str, str] | None:
    for line in text.splitlines():
        clean_line = line.strip()
        if not clean_line:
            continue

        group_match = GROUP_LINE_PATTERN.match(clean_line)
        if group_match:
            clean_line = group_match.group(2).strip()

        return parse_telegram_chat_identifier(clean_line)

    return None


def parse_telegram_chat_identifier(value: str) -> dict[str, str] | None:
    clean_value = value.strip()
    if ID_PATTERN.fullmatch(clean_value):
        return {"type": "id", "value": clean_value}

    if USERNAME_PATTERN.fullmatch(clean_value):
        username = clean_value[1:] if clean_value.startswith("@") else clean_value
        return {"type": "username", "value": username.lower()}

    return None


def parse_user_identifier(value: str) -> dict[str, str] | None:
    return parse_telegram_chat_identifier(value)


def parse_keywords_input(text: str) -> list[str]:
    normalized = text.replace("\n", ",")
    candidates = [part.strip() for part in normalized.split(",")]

    deduped: list[str] = []
    seen: set[str] = set()
    for keyword in candidates:
        if not keyword:
            continue
        key = keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(keyword)

    return deduped


def find_matched_keywords(content: str, keywords: list[str]) -> list[str]:
    if not content:
        return []

    content_lower = content.lower()
    matched: list[str] = []
    seen: set[str] = set()

    for keyword in keywords:
        clean_keyword = keyword.strip()
        if not clean_keyword:
            continue
        lookup = clean_keyword.lower()
        if lookup in seen:
            continue
        if lookup in content_lower:
            matched.append(clean_keyword)
            seen.add(lookup)

    return matched


def validate_lark_webhook_url(url: str) -> bool:
    clean_url = url.strip()
    return clean_url.startswith("https://open.larksuite.com/") or clean_url.startswith(
        "https://open.feishu.cn/"
    )


def format_identifier(identifier: dict[str, str] | None) -> str:
    if not identifier:
        return "-"
    if identifier.get("type") == "username":
        return f"@{identifier.get('value', '')}"
    return identifier.get("value", "-")


def matches_chat_identifier(identifier: dict[str, str] | None, chat_id: int, chat_username: str | None) -> bool:
    if not identifier:
        return False

    identifier_type = identifier.get("type")
    identifier_value = identifier.get("value", "")

    if identifier_type == "id":
        return identifier_value == str(chat_id)

    if identifier_type == "username":
        if not chat_username:
            return False
        return identifier_value.lower() == chat_username.lower()

    return False


def matches_user_identifier(identifier: dict[str, str] | None, user_id: int, username: str | None) -> bool:
    return matches_chat_identifier(identifier, user_id, username)


def resolve_chat_target(identifier: dict[str, str]) -> Any:
    if identifier.get("type") == "id":
        try:
            return int(identifier.get("value", "0"))
        except ValueError:
            return identifier.get("value", "")
    return f"@{identifier.get('value', '')}"
