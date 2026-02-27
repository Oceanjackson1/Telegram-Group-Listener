"""Migrate user_configs.json → SQLite database."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root so imports work when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.database import Database  # noqa: E402


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def migrate(json_path: str = "user_configs.json", db_path: str = "data/bot.db") -> None:
    src = Path(json_path)
    if not src.exists():
        print(f"Source file {json_path} not found, nothing to migrate.")
        return

    raw = src.read_text(encoding="utf-8").strip()
    if not raw:
        print("Empty config file, nothing to migrate.")
        return

    configs: dict = json.loads(raw)
    if not configs:
        print("No configs in JSON, nothing to migrate.")
        return

    db = Database(db_path)
    now = _now_utc()
    migrated = 0

    for owner_id_str, config in configs.items():
        owner_id = int(owner_id_str)
        language = config.get("language", "en")

        # Person monitoring
        source = config.get("source")
        destination = config.get("destination")
        if source and destination:
            db.execute(
                "INSERT INTO monitor_config (owner_id, monitor_type, source_config, destination, keywords, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    owner_id,
                    "person",
                    json.dumps(source, ensure_ascii=False),
                    json.dumps(destination, ensure_ascii=False),
                    "[]",
                    1 if config.get("active") else 0,
                    config.get("updated_at", now),
                    now,
                ),
            )
            migrated += 1

        # Keyword monitoring
        keyword_source = config.get("keyword_source")
        keyword_destination = config.get("keyword_destination")
        keywords = config.get("keywords", [])
        if keyword_source and keyword_destination and keywords:
            db.execute(
                "INSERT INTO monitor_config (owner_id, monitor_type, source_config, destination, keywords, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    owner_id,
                    "keyword",
                    json.dumps(keyword_source, ensure_ascii=False),
                    json.dumps(keyword_destination, ensure_ascii=False),
                    json.dumps(keywords, ensure_ascii=False),
                    1 if config.get("keyword_active") else 0,
                    config.get("updated_at", now),
                    now,
                ),
            )
            migrated += 1

    db.commit()
    db.close()
    print(f"Migration complete: {migrated} monitor config(s) imported from {json_path} → {db_path}")


if __name__ == "__main__":
    migrate()
