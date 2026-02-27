import copy
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ConfigStore:
    def __init__(self, file_path: str) -> None:
        self.file_path = Path(file_path)
        self._lock = threading.RLock()
        self._configs: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self.file_path.exists():
                self.file_path.write_text("{}", encoding="utf-8")
                self._configs = {}
                return

            raw = self.file_path.read_text(encoding="utf-8").strip()
            if not raw:
                self._configs = {}
                return

            try:
                data = json.loads(raw)
                self._configs = data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                self._configs = {}

    def save(self) -> None:
        with self._lock:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text(
                json.dumps(self._configs, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def get_user_config(self, user_id: int) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._configs.get(str(user_id), {}))

    def get_all_configs(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._configs)

    def get_language(self, user_id: int) -> str:
        config = self.get_user_config(user_id)
        language = config.get("language", "en")
        return language if language in {"en", "zh"} else "en"

    def set_language(self, user_id: int, language: str) -> None:
        with self._lock:
            key = str(user_id)
            config = self._configs.setdefault(key, {})
            config["language"] = language if language in {"en", "zh"} else "en"
            config["updated_at"] = self._now_utc()
            self.save()

    def update_user_config(self, user_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            key = str(user_id)
            current = self._configs.setdefault(key, {})
            merged = copy.deepcopy(current)
            merged.update(copy.deepcopy(updates))
            merged.setdefault("language", "en")
            merged["updated_at"] = self._now_utc()
            self._configs[key] = merged
            self.save()
            return copy.deepcopy(merged)

    def set_active(self, user_id: int, active: bool) -> None:
        with self._lock:
            key = str(user_id)
            config = self._configs.setdefault(key, {"language": "en"})
            config["active"] = active
            config["updated_at"] = self._now_utc()
            self.save()

    @staticmethod
    def _now_utc() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
