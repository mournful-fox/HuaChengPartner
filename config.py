"""Настройки и статистика. Хранятся в обычном JSON-файле в папке пользователя."""
import datetime
import json
import os

from PySide6.QtCore import QStandardPaths

DEFAULTS = {
    "address": "гэгэ",          # как Хуа Чен к тебе обращается
    "size": 150,                # рост чиби в пикселях
    "butterflies": 7,           # сколько бабочек кружит рядом
    "speech_min": 10,           # реплики раз в N..M минут
    "speech_max": 30,
    "red_string": False,        # красная нить от его пальца к курсору
    "follow_cursor": False,     # часть бабочек летает за курсором
    "eming_auto": True,         # Хуа Чен иногда сам отпускает Э-Мина погулять
    "eming_walk_minutes": 4,    # сколько Э-Мин гуляет, прежде чем вернуться
    "autostart": True,          # запускаться вместе с Windows
    "calm": False,              # стоит на месте, не бродит
    "hide_fullscreen": True,    # прятаться в полноэкранных играх/видео
    "pos_x": 0.8,               # где стоял Хуа Чен (доля ширины экрана)
    "provider": "ollama",       # ollama / gemini / groq / openai
    "api_keys": {},             # ключи облачных провайдеров (хранятся только здесь)
    "cloud_models": {},
    "model": "qwen3:4b",        # локальная модель Ollama
    "ollama_url": "http://127.0.0.1:11434",
    "reminders": [],
    "todos": [],
    # статистика
    "cfg_version": 2,
    "first_launch": None,
    "pets": 0,
    "teleports": 0,
    "dice": 0,
}


def _dir():
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".huachengpartner")
    os.makedirs(base, exist_ok=True)
    return base


class Config(dict):
    path = None

    @classmethod
    def load(cls, char="hua"):
        cfg = cls(DEFAULTS)
        base = _dir()
        folder = base if char == "hua" else os.path.join(base, char)   # у каждого персонажа своя папка
        os.makedirs(folder, exist_ok=True)
        cls.path = os.path.join(folder, "config.json")
        saved = {}
        try:
            with open(cls.path, encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            pass
        cfg.update(saved)
        if saved and saved.get("cfg_version", 1) < 2:      # с версии 2 автозапуск включён по умолчанию
            cfg["autostart"] = True
            cfg["cfg_version"] = 2
            cfg.save()
        if char != "hua":                       # общие вещи берём у Хуа Чена: ключи, обращение, размер
            try:
                with open(os.path.join(base, "config.json"), encoding="utf-8") as f:
                    main = json.load(f)
            except (OSError, ValueError):
                main = {}
            if not saved:
                cfg["autostart"] = False
                for k in ("address", "size", "city", "provider", "model", "cloud_models", "ollama_url"):
                    if k in main:
                        cfg[k] = main[k]
            keys = dict(main.get("api_keys") or {})
            keys.update({k: v for k, v in (cfg.get("api_keys") or {}).items() if v})
            cfg["api_keys"] = keys
        if not cfg["first_launch"]:
            cfg["first_launch"] = datetime.date.today().isoformat()
            cfg.save()
        return cfg

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def days_together(self):
        try:
            d0 = datetime.date.fromisoformat(self["first_launch"])
        except (TypeError, ValueError):
            return 1
        return (datetime.date.today() - d0).days + 1
