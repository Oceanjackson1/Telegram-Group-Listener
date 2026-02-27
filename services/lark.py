import asyncio
import logging
from datetime import datetime, timezone

import httpx
from telegram import Message

logger = logging.getLogger(__name__)


async def test_webhook(url: str, test_message: str) -> tuple[bool, str]:
    payload = {
        "msg_type": "text",
        "content": {"text": test_message},
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        return False, str(exc)

    if response.status_code != 200:
        return False, f"HTTP {response.status_code}"

    try:
        body = response.json()
    except ValueError:
        body = {}

    if body.get("code", 0) != 0:
        return False, body.get("msg", "Unknown webhook error")

    return True, "ok"


def extract_content_for_lark(message: Message, media_note: str) -> str:
    if message.text:
        return message.text
    if message.caption:
        return message.caption
    return media_note


def _build_interactive_card(
    title: str,
    source_user: str,
    source_group: str,
    content: str,
    time_text: str,
    from_label: str,
    group_label: str,
) -> dict:
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title,
                },
                "template": "green",
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": from_label.format(source_user=source_user)},
                        },
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": group_label.format(source_group=source_group)},
                        },
                    ],
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content,
                    },
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": time_text,
                        }
                    ],
                },
            ],
        },
    }


async def send_alert(
    webhook_url: str,
    source_user: str,
    source_group: str,
    content: str,
    title: str,
    from_label: str,
    group_label: str,
    time_template: str,
) -> bool:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    time_text = time_template.format(timestamp=timestamp)
    payload = _build_interactive_card(
        title=title,
        source_user=source_user,
        source_group=source_group,
        content=content,
        time_text=time_text,
        from_label=from_label,
        group_label=group_label,
    )

    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(webhook_url, json=payload)

            if response.status_code == 200:
                body = response.json() if response.text else {}
                if body.get("code", 0) == 0:
                    return True
                logger.error("Lark webhook error on attempt %s: %s", attempt, body)
            else:
                logger.error(
                    "Lark webhook HTTP error on attempt %s: status=%s body=%s",
                    attempt,
                    response.status_code,
                    response.text,
                )
        except Exception as exc:
            logger.exception("Lark webhook send failed on attempt %s: %s", attempt, exc)

        if attempt < 3:
            await asyncio.sleep(2)

    return False
