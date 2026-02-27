import json
from pathlib import Path
from typing import Any


class I18n:
    def __init__(self, i18n_dir: str) -> None:
        self._translations: dict[str, dict[str, str]] = {}
        base = Path(i18n_dir)
        for language in ("en", "zh"):
            file_path = base / f"{language}.json"
            if not file_path.exists():
                self._translations[language] = {}
                continue
            try:
                self._translations[language] = json.loads(file_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._translations[language] = {}

    def t(self, language: str, key: str, **kwargs: Any) -> str:
        language = language if language in self._translations else "en"
        message = self._translations.get(language, {}).get(key)
        if message is None:
            message = self._translations.get("en", {}).get(key, key)
        try:
            return message.format(**kwargs)
        except Exception:
            return message
