"""ИИ-мозг Хуа Чена: локальная модель через Ollama + инструменты.

Всё работает на компьютере пользователя: запросы идут на http://127.0.0.1:11434 (Ollama),
в интернет ничего не уходит. Всё, что что-то закрывает или переносит, сначала
показывается пользователю и выполняется только после «Да».
"""
import datetime
import json
import os
import re
import shutil
import threading
import urllib.error
import urllib.request

import tools_pc

from PySide6.QtCore import QObject, QTimer, Signal

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

SYSTEM = """Ты — Хуа Чен, Князь демонов из «Благословения небожителей». Ты живёшь на рабочем столе \
пользователя маленькой чиби-фигуркой в красных одеждах, рядом с тобой серебряные бабочки и живой ятаган Э-Мин.
Характер: спокойный, уверенный, чуть насмешливый с другими, но к пользователю бесконечно тёплый, \
преданный и заботливый. Иногда шутишь, иногда ворчишь, что пользователь мало отдыхает.
Правила:
- Отвечай только по-русски, коротко: 1–3 предложения. Без списков и markdown, если не просят.
- Обращайся к пользователю «{addr}».
- Ты не «ИИ-ассистент» и не говоришь о моделях и программах — ты Хуа Чен.
- Когда тебя просят что-то сделать (напоминание, дела, вкладки, загрузки, фокус, кости и т.п.) — \
вызывай подходящий инструмент. Не выдумывай результат: говори то, что вернул инструмент.
- Если инструмент сообщил, что пользователь отказался, просто прими это.
- Для поиска и открытия сайтов передавай то, что пользователь имел в виду, а не буквальное звучание: \
жанры, названия и имена — в их обычном написании (например, «лофи» → lo-fi).
- Никогда не рассуждай вслух и не пересказывай свои мысли: сразу отвечай репликой Хуа Чена или вызывай инструмент. Чтобы узнать дату и время, вызови get_datetime."""


def tool(name, description, props=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


TOOLS = [
    tool("set_reminder", "Поставить напоминание. Укажи либо time (ЧЧ:ММ, сегодня или завтра, если время прошло), "
         "либо in_minutes (через сколько минут).",
         {"text": {"type": "string", "description": "о чём напомнить"},
          "time": {"type": "string", "description": "время в формате ЧЧ:ММ"},
          "date": {"type": "string", "description": "дата ГГГГ-ММ-ДД, если не сегодня"},
          "in_minutes": {"type": "integer", "description": "через сколько минут"}}, ["text"]),
    tool("list_reminders", "Показать все запланированные напоминания."),
    tool("get_datetime", "Узнать текущие дату, время и день недели."),
    tool("delete_reminder", "Удалить напоминание по номеру из list_reminders.",
         {"number": {"type": "integer"}}, ["number"]),
    tool("add_todo", "Добавить дело в список дел.", {"text": {"type": "string"}}, ["text"]),
    tool("list_todos", "Показать список дел."),
    tool("complete_todo", "Отметить дело выполненным по номеру из list_todos.",
         {"number": {"type": "integer"}}, ["number"]),
    tool("delete_todo", "Удалить дело из списка по номеру.", {"number": {"type": "integer"}}, ["number"]),
    tool("count_tabs", "Узнать, сколько вкладок открыто в Chrome и сколько из них давно не открывались."),
    tool("close_inactive_tabs", "Закрыть вкладки Chrome, которые давно не открывали. Закреплённые, активные "
         "и вкладки со звуком не трогаются. Пользователь сам подтвердит закрытие.",
         {"hours": {"type": "number", "description": "сколько часов вкладку не открывали (по умолчанию 3)"}}),
    tool("tidy_downloads", "Разложить файлы в папке «Загрузки» по подпапкам (Изображения, Документы, Архивы, "
         "Установщики, Видео, Музыка). Ничего не удаляет. Пользователь сам подтвердит."),
    tool("open_website", "Открыть сайт в Chrome. site — адрес (example.com) или название сайта "
         "(youtube, вк, почта, twitch, github, википедия и т.п.).",
         {"site": {"type": "string"}}, ["site"]),
    tool("search_web", "Найти что-то в интернете и открыть результаты в Chrome. "
         "where: google (по умолчанию) или youtube (видео, музыка, клипы).",
         {"query": {"type": "string"}, "where": {"type": "string", "enum": ["google", "youtube"]}}, ["query"]),
    tool("find_files", "Найти папку или файл на компьютере по части имени (в Рабочем столе, Документах, "
         "Загрузках, Изображениях, Музыке, Видео, OneDrive). Возвращает пронумерованный список путей.",
         {"query": {"type": "string", "description": "часть имени"},
          "kind": {"type": "string", "enum": ["folder", "file", "any"]}}, ["query"]),
    tool("open_in_explorer", "Открыть папку в Проводнике или показать файл в Проводнике. "
         "path — полный путь из find_files либо название стандартной папки (Загрузки, Документы, Рабочий стол…).",
         {"path": {"type": "string"}}, ["path"]),
    tool("open_app", "Запустить приложение, установленное на компьютере (Telegram, Spotify, Discord, Word, "
         "Блокнот, Калькулятор и т.д.).", {"name": {"type": "string"}}, ["name"]),
    tool("set_alarm", "Поставить будильник: в указанное время зазвучит мелодия, пока пользователь не выключит. "
         "Укажи time (ЧЧ:ММ) или in_minutes.",
         {"time": {"type": "string"}, "date": {"type": "string"}, "in_minutes": {"type": "integer"},
          "text": {"type": "string", "description": "подпись, например «Вставать»"}}),
    tool("start_focus", "Включить фокус-таймер (работа без отвлечений, потом перерыв).",
         {"minutes": {"type": "integer", "description": "длительность, по умолчанию 25"}}),
    tool("roll_dice", "Бросить кости. question=true — чтобы кости ответили «да» или «нет».",
         {"question": {"type": "boolean"}}),
    tool("show_magic", "Показать эффект: butterflies — выпустить бабочек, rain — кровавый дождь, "
         "eming — отпустить Э-Мина погулять.",
         {"effect": {"type": "string", "enum": ["butterflies", "rain", "eming"]}}, ["effect"]),
]

EXT = {
    "Изображения": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic", ".tif", ".tiff"},
    "Документы": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".odt", ".csv",
                  ".epub", ".fb2", ".djvu", ".md"},
    "Архивы": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Установщики": {".exe", ".msi", ".msix", ".appx"},
    "Видео": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv"},
    "Музыка": {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"},
}
PARTIAL = {".crdownload", ".part", ".tmp", ".download"}


def downloads_dir():
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            guid = ctypes.c_byte * 16
            # FOLDERID_Downloads {374DE290-123F-4565-9164-39C4925E467B}
            g = guid(*bytes.fromhex("90e24d373f126545916439c4925e467b"))
            p = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) == 0:
                path = p.value
                ctypes.windll.ole32.CoTaskMemFree(p)
                return path
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Downloads")


TOOL_NAMES = {t["function"]["name"] for t in TOOLS}
STRONG = ("пользовател", "tool_call", "нужно ответить", "надо ответить", "я должен", "мне нужно ответить",
          "the user", "i need to", "i should")
WEAK = ("функци", "инструмент", "в стиле", "ответить коротко", "вызвать")


def looks_like_reasoning(text):
    """Хуа Чен не говорит о «пользователе» и «функциях» — значит, это черновик мыслей модели."""
    low = (text or "").lower()
    return any(w in low for w in STRONG) or sum(w in low for w in WEAK) >= 2


def text_tool_calls(text):
    """Находит в тексте вызов вида {"name": "tidy_downloads", "arguments": {...}}."""
    calls = []
    for m in re.finditer(r'\{\s*"name"\s*:\s*"(\w+)"\s*,\s*"arguments"\s*:\s*(\{.*?\})\s*\}', text or "", re.S):
        if m.group(1) in TOOL_NAMES:
            try:
                args = json.loads(m.group(2))
            except ValueError:
                args = {}
            calls.append({"function": {"name": m.group(1), "arguments": args}})
            break                                   # одного действия за раз достаточно
    return calls


def salvage(text, addr):
    """Если модель всё же рассуждает — достаём из её черновика готовую реплику в кавычках."""
    quoted = re.findall(r"[«\"]([^»\"]{6,200})[»\"]", text or "")
    for q in reversed(quoted):
        if not looks_like_reasoning(q) and "{" not in q and len(q.split()) >= 3:
            return q
    return f"Мм… Повтори-ка, {addr}? Я задумался."


SITES = [
    (("youtube", "ютуб", "ютьюб"), "https://www.youtube.com"),
    (("vk", "вк", "вконтакт"), "https://vk.com"),
    (("gmail", "почт", "mail"), "https://mail.google.com"),
    (("telegram", "телеграм", "телега"), "https://web.telegram.org"),
    (("twitch", "твич"), "https://www.twitch.tv"),
    (("github", "гитхаб"), "https://github.com"),
    (("wikipedia", "википеди", "вики"), "https://ru.wikipedia.org"),
    (("pinterest", "пинтерест"), "https://www.pinterest.com"),
    (("spotify", "спотифай"), "https://open.spotify.com"),
    (("netflix", "нетфликс"), "https://www.netflix.com"),
    (("chatgpt", "чатгпт"), "https://chatgpt.com"),
    (("claude", "клод"), "https://claude.ai"),
    (("gemini", "гемини"), "https://gemini.google.com"),
    (("яндекс", "yandex"), "https://ya.ru"),
    (("google", "гугл"), "https://www.google.com"),
]


def site_url(site):
    from urllib.parse import quote
    s = (site or "").strip()
    if re.match(r"^https?://", s, re.I):
        return s
    if re.match(r"^[\w.-]+\.[a-zа-я]{2,}(/\S*)?$", s, re.I):
        return "https://" + s
    low = s.lower()
    for names, url in SITES:
        if any(n in low for n in names):
            return url
    return "https://www.google.com/search?q=" + quote(s)


def chrome_path():
    if os.name != "nt":
        return None
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            p = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
            if os.path.exists(p):
                return p
    return None


def open_url(url):
    """Открывает ссылку в Chrome (новой вкладкой), а если Chrome не найден — в браузере по умолчанию."""
    p = chrome_path()
    if p:
        import subprocess
        subprocess.Popen([p, url], close_fds=True)
        return "Chrome"
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    QDesktopServices.openUrl(QUrl(url))
    return "браузере"


# ── быстрые команды: распознаём сами, без модели (надёжно и мгновенно) ──
WORDNUM = {"одну": 1, "один": 1, "две": 2, "два": 2, "три": 3, "пять": 5, "десять": 10, "пятнадцать": 15,
           "двадцать": 20, "тридцать": 30, "сорок": 40, "полчаса": 30}


def _num(s):
    s = (s or "").strip()
    return int(s) if s.isdigit() else WORDNUM.get(s)


def route(text):
    """Возвращает (инструмент, аргументы) для очевидных просьб или None — тогда отвечает модель."""
    t = text.lower().replace("ё", "е")
    has = lambda *ws: any(w in t for w in ws)  # noqa: E731
    # загрузки
    if "загрузк" in t and has("чист", "разбер", "разобр", "убер", "убра", "разлож", "порядок", "сортир", "прибер"):
        return "tidy_downloads", {}
    # вкладки
    if "вклад" in t:
        if has("сколько"):
            return "count_tabs", {}
        if has("закр", "убер", "убра", "чист", "прибер"):
            m = re.search(r"(\d+)\s*(час|ч\b)", t)
            return "close_inactive_tabs", {"hours": float(m.group(1)) if m else 3}
    # напоминания
    if re.search(r"\b(какие|мои|покажи|список)\b.*напоминан", t):
        return "list_reminders", {}
    if "напомни" in t:
        args = {}
        m = re.search(r"через\s+полчаса", t) or re.search(
            r"через\s+(?:(\d+|\w+)\s+)?(минут\w*|мин\b|час\w*)", t)
        if m and "полчаса" in m.group(0):
            args["in_minutes"] = 30
        elif m:
            n = _num(m.group(1)) if m.group(1) else None
            unit = m.group(2)
            if unit.startswith("час"):
                n = (n or 1) * 60
            if n:
                args["in_minutes"] = n
        else:
            m = re.search(r"\bв\s*(\d{1,2})(?:[:.](\d{2}))?(?:\s*час\w*)?(?:\s*(утра|дня|вечера|ночи))?\b", t)
            if m:
                hh = int(m.group(1))
                if m.group(3) in ("дня", "вечера") and hh < 12:
                    hh += 12
                args["time"] = f"{hh:02d}:{m.group(2) or '00'}"
        if args:
            body = text
            if m:
                body = text[:m.start()] + text[m.end():]
            body = re.sub(r"(?i)^.*?напомни(те)?\s*(мне)?\s*(,|:)?\s*", "", body)
            body = re.sub(r"(?i)^(о том,?\s*что|о том|что(бы)?|о)\s+", "", body.strip(" ,.:"))
            args["text"] = body.strip(" ,.:!") or "то, о чём ты просил(а)"
            return "set_reminder", args
    # дела
    m = re.search(r"(вычеркни|выполнено|сделала?|отметь|закрой)\D*(\d+)", t)
    if m and has("дел", "пункт", "задач", "вычеркни"):
        return "complete_todo", {"number": int(m.group(2))}
    if re.search(r"\b(добавь|запиши|внеси)\b", t) and has("дел", "список", "задач"):
        body = text.split(":", 1)[1] if ":" in text else re.sub(
            r"(?i)^.*?\b(добавь|запиши|внеси)\b\s*(в\s+)?(список\s+)?(дел[а]?|задач[и]?)?\s*", "", text)
        body = body.strip(" ,.:!")
        if body:
            return "add_todo", {"text": body}
    if re.search(r"(список дел|мои дела|что у меня по делам|какие у меня дела|что в списке)", t):
        return "list_todos", {}
    # кости, фокус, магия, время
    if "кост" in t and has("брос", "кинь", "кинуть", "бросить"):
        return "roll_dice", {"question": "?" in t or " ли " in t or "да или нет" in t}
    if "фокус" in t and has("включ", "запуст", "начн", "давай", "поставь"):
        m = re.search(r"(\d+)\s*мин", t)
        return "start_focus", {"minutes": int(m.group(1)) if m else 25}
    if "дожд" in t and has("устрой", "покажи", "давай", "сделай", "вызови"):
        return "show_magic", {"effect": "rain"}
    if "бабоч" in t and has("выпуст", "покажи", "отпусти"):
        return "show_magic", {"effect": "butterflies"}
    if re.search(r"э-?мин", t) and has("погуля", "отпуст", "выпуст"):
        return "show_magic", {"effect": "eming"}
    if "будильник" in t and has("постав", "завед", "установ", "разбуди", "на "):
        m = re.search(r"через\s+(?:(\d+)\s+)?(минут\w*|час\w*)", t)
        if m:
            n = int(m.group(1) or 1) * (60 if m.group(2).startswith("час") else 1)
            return "set_alarm", {"in_minutes": n, "text": "Будильник"}
        m = re.search(r"(?:на|в)\s*(\d{1,2})(?:[:.\s](\d{2}))?(?:\s*(утра|дня|вечера|ночи))?", t)
        if m:
            hh = int(m.group(1)) + (12 if m.group(3) in ("дня", "вечера") and int(m.group(1)) < 12 else 0)
            return "set_alarm", {"time": f"{hh:02d}:{m.group(2) or '00'}", "text": "Будильник"}
    if re.search(r"\bразбуди\b", t):
        m = re.search(r"в\s*(\d{1,2})(?:[:.\s](\d{2}))?", t)
        if m:
            return "set_alarm", {"time": f"{int(m.group(1)):02d}:{m.group(2) or '00'}", "text": "Вставать"}
    m = re.search(r"(?:найди|поищи|где)\s+(?:мне\s+)?(папк\w*|файл\w*)\s+(.+)", t)
    if m:
        return "find_files", {"query": m.group(2).strip(" .!?«»\""),
                              "kind": "folder" if m.group(1).startswith("папк") else "file"}
    m = re.search(r"(?:открой|покажи)\s+(?:мне\s+)?папк\w*\s+(.+)", t)
    if m:
        return "open_in_explorer", {"path": m.group(1).strip(" .!?«»\"")}
    m = re.search(r"\b(?:запусти|открой|включи)\s+(?:мне\s+)?(?:приложение|программу)\s+(.+)", t) or \
        re.search(r"\bзапусти\s+(?:мне\s+)?(.+)", t)
    if m and "фокус" not in t:
        return "open_app", {"name": m.group(1).strip(" .!?")}
    m = re.search(r"(?:найди|поищи|включи|поставь)\s+(?:мне\s+)?(?:на|в)\s+(?:ютубе?|youtube)\s+(.+)", t) or \
        re.search(r"(?:найди|поищи|включи|поставь)\s+(?:мне\s+)?(.+?)\s+(?:на|в)\s+(?:ютубе?|youtube)", t)
    if m:
        return "search_web", {"query": m.group(1).strip(" .!?"), "where": "youtube"}
    m = re.search(r"(?:загугли|погугли|найди в (?:гугле|google|интернете)|поищи в (?:гугле|google|интернете))\s+(.+)", t)
    if m:
        return "search_web", {"query": m.group(1).strip(" .!?"), "where": "google"}
    m = re.search(r"\b(?:открой|зайди на|перейди на)\s+(?:мне\s+)?(?:сайт\s+)?(.+?)(?:\s+(?:в|во)\s+(?:хроме|chrome|браузере))?[.!?]*$", t)
    if m and "вклад" not in t and "загрузк" not in t:
        target = m.group(1).strip()
        if not re.search(r"\.[a-zа-я]{2,}", target) and tools_pc.find_app(target):
            return "open_app", {"name": target}
        return "open_website", {"site": target}
    if has("который час", "сколько времени", "какое сегодня число", "какой сегодня день", "какое число"):
        return "get_datetime", {}
    return None


PROVIDERS = {
    "ollama": {"title": "Локально (Ollama)"},
    "gemini": {"title": "Google Gemini (бесплатно)", "model": "gemini-flash-latest",
               "fallback": "gemini-flash-lite-latest",
               "base": "https://generativelanguage.googleapis.com/v1beta/openai",
               "keys": "https://aistudio.google.com/apikey"},
    "groq": {"title": "Groq (бесплатно)", "model": "openai/gpt-oss-120b", "fallback": "openai/gpt-oss-20b",
             "base": "https://api.groq.com/openai/v1", "keys": "https://console.groq.com/keys"},
    "openai": {"title": "OpenAI (платно)", "model": "",
               "base": "https://api.openai.com/v1", "keys": "https://platform.openai.com/api-keys"},
}


class MissingKey(Exception):
    pass


def cloud_models(provider, key):
    """Список моделей облачного провайдера (пусто при ошибке)."""
    p = PROVIDERS.get(provider, {})
    if "base" not in p or not key:
        return []
    try:
        req = urllib.request.Request(p["base"] + "/models", headers={"Authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=8) as r:
            ids = [m.get("id", "") for m in json.loads(r.read().decode()).get("data", [])]
    except Exception:  # noqa: BLE001
        return []
    ids = [i.split("/", 1)[1] if i.startswith("models/") else i for i in ids]
    if provider == "gemini":
        ids = [i for i in ids if ("gemini" in i or "gemma" in i) and "embed" not in i
               and "tts" not in i and "image" not in i]
    return sorted(set(ids))


class _Net(QObject):
    done = Signal(object, object)       # (ответ, ошибка)
    tool_done = Signal(object, object)  # (колбэк инструмента, результат фоновой работы)


class Agent:
    def __init__(self, world):
        self.w = world
        self.history = []          # сообщения без системного
        self.busy = False
        self.on_reply = None
        self.net = _Net()
        self.net.done.connect(self._on_http)
        self.net.tool_done.connect(self._on_tool_bg)
        self.found = []
        tools_pc.preload_apps()
        self.rounds = 0

    # ── публичное ──
    def ask(self, text, on_reply, audio=None):
        if self.busy:
            on_reply("Подожди, я ещё думаю над прошлым.")
            return
        self.busy = True
        self.on_reply = on_reply
        self.rounds = 0
        self.tool_results = []
        self.lead = ""
        self.nudge = False
        self.retries = 0
        self.use_fallback = False
        msg = {"role": "user", "content": text}
        if audio:
            msg["audio"] = audio
        self.history.append(msg)
        self.history = self.history[-12:]
        while self.history and self.history[0]["role"] != "user":   # не начинаем с обрывка
            self.history.pop(0)
        r = route(text) if self.local() and not audio else None
        if r:                                   # очевидная просьба — выполняем сразу, без модели
            calls = [{"id": "call_route", "function": {"name": r[0], "arguments": r[1]}}]
            self.history.append({"role": "assistant", "content": "", "tool_calls": calls})
            self._run_tools(calls, 0)
            return
        self._request()

    VOICE_NOTE = ("Это голосовое сообщение на русском, но в нём могут быть английские слова и названия "
                  "(жанры музыки, сайты, приложения, имена исполнителей). Пиши их латиницей так, как их принято "
                  "писать (lo-fi, YouTube, Spotify, Discord), а не русскими буквами на слух.\n"
                  "Первой строкой ответа запиши, что услышал, в формате:\n>> текст\n"
                  "Со второй строки — твой ответ (или вызови инструмент).")

    def ask_voice(self, wav, on_reply, on_transcript=None):
        import base64
        if self.busy:
            on_reply("Подожди, я ещё думаю над прошлым.")
            return
        self.on_transcript = on_transcript
        self.ask("", on_reply, audio=base64.b64encode(wav).decode())

    def _take_transcript(self, content):
        """Достаёт строку «>> …» (что модель расслышала) и убирает её из ответа."""
        m = re.search(r"^\s*>>\s*(.+)$", content or "", re.M)
        if not m:
            return content
        heard = m.group(1).strip()
        for msg in reversed(self.history):
            if msg["role"] == "user" and msg.get("audio"):
                msg.pop("audio")
                msg["content"] = heard
                break
        cb = getattr(self, "on_transcript", None)
        if cb:
            cb(heard)
            self.on_transcript = None
        return (content[:m.start()] + content[m.end():]).strip()

    def reset(self):
        self.history = []

    # ── провайдер ──
    def provider(self):
        p = self.w.cfg.get("provider", "ollama")
        return p if p in PROVIDERS else "ollama"

    def local(self):
        return self.provider() == "ollama"

    def model(self):
        p = self.provider()
        if p == "ollama":
            return self.w.cfg.get("model", "qwen3:4b")
        if getattr(self, "use_fallback", False) and PROVIDERS[p].get("fallback"):
            return PROVIDERS[p]["fallback"]
        return (self.w.cfg.get("cloud_models") or {}).get(p) or PROVIDERS[p]["model"]

    def effort(self):
        """Уровень размышлений для облака: у Gemini 2.5 Flash можно выключить совсем,
        у новых моделей — только снизить до low. Если сервер отверг параметр, больше не шлём."""
        if getattr(self, "no_effort", False):
            return None
        m = self.model().lower()
        if self.provider() == "gemini" and "2.5" in m and "flash" in m:
            return "none"
        return "low"

    def key(self):
        return (self.w.cfg.get("api_keys") or {}).get(self.provider(), "").strip()

    def url(self, path):
        return self.w.cfg.get("ollama_url", "http://127.0.0.1:11434").rstrip("/") + path

    def system(self):
        s = SYSTEM.format(addr=self.w.cfg["address"])
        if self.local() and "qwen" in self.model().lower():
            s += "\n/no_think"          # «мягкий» выключатель размышлений у Qwen3
        return s

    # ── сообщения в формате Ollama и OpenAI ──
    def ollama_messages(self):
        msgs = [{"role": "system", "content": self.system()}]
        for m in self.history:
            if m["role"] == "assistant" and m.get("tool_calls"):
                msgs.append({"role": "assistant", "content": m.get("content") or "",
                             "tool_calls": [{"function": {"name": c["function"]["name"],
                                                          "arguments": c["function"]["arguments"]}}
                                            for c in m["tool_calls"]]})
            elif m["role"] == "tool":
                msgs.append({"role": "tool", "tool_name": m.get("tool_name", ""), "content": m["content"]})
            else:
                msgs.append({"role": m["role"], "content": m["content"]})
        if self.nudge:
            for m in reversed(msgs):
                if m["role"] == "user":
                    m["content"] += ("\n\n(Ответь сразу от лица Хуа Чена, 1–2 предложения, без рассуждений. "
                                     "Если нужно действие — вызови инструмент.)")
                    break
        return msgs

    def openai_messages(self):
        gemini = self.provider() == "gemini"
        msgs = [{"role": "system", "content": self.system()}]
        for m in self.history:
            if m["role"] == "assistant" and m.get("tool_calls"):
                tcs = []
                for k, c in enumerate(m["tool_calls"]):
                    tc = {"id": c["id"], "type": "function",
                          "function": {"name": c["function"]["name"],
                                       "arguments": json.dumps(c["function"]["arguments"], ensure_ascii=False)}}
                    if c.get("extra_content"):
                        tc["extra_content"] = c["extra_content"]
                    elif gemini and k == 0:
                        # вызов без подписи (например, из быстрой команды) — официальная заглушка Google
                        tc["extra_content"] = {"google": {"thought_signature": "skip_thought_signature_validator"}}
                    tcs.append(tc)
                msgs.append({"role": "assistant", "content": m.get("content") or None, "tool_calls": tcs})
            elif m["role"] == "tool":
                msgs.append({"role": "tool", "tool_call_id": m.get("tool_call_id", ""), "content": m["content"]})
            elif m.get("audio"):
                msgs.append({"role": "user", "content": [
                    {"type": "text", "text": self.VOICE_NOTE},
                    {"type": "input_audio", "input_audio": {"data": m["audio"], "format": "wav"}}]})
            else:
                msgs.append({"role": m["role"], "content": m["content"]})
        return msgs

    def body(self, messages, **opts):
        o = {"temperature": 0.6, "num_ctx": 3072, "num_predict": 160}
        o.update(opts)
        return {"model": self.model(), "messages": messages, "tools": TOOLS,
                "stream": False, "think": False, "keep_alive": "60m", "options": o}

    def warmup(self):
        """Заранее загружает локальную модель в память, чтобы первый ответ не ждал."""
        if not self.local():
            return
        body = self.body([{"role": "system", "content": self.system()},
                          {"role": "user", "content": "привет"}], num_predict=1)

        def work():
            try:
                req = urllib.request.Request(self.url("/api/chat"), data=json.dumps(body).encode(),
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=600).read()
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=work, daemon=True).start()

    def _request(self):
        self.rounds += 1
        if self.local():
            url = self.url("/api/chat")
            body = self.body(self.ollama_messages())
            headers = {"Content-Type": "application/json"}
        else:
            p = PROVIDERS[self.provider()]
            if not self.key():
                QTimer.singleShot(0, lambda: self.net.done.emit(None, MissingKey()))
                return
            url = p["base"] + "/chat/completions"
            body = {"model": self.model(), "messages": self.openai_messages(), "tools": TOOLS,
                    "temperature": 0.8}
            effort = self.effort()
            if effort:
                body["reasoning_effort"] = effort      # меньше «раздумий» — быстрее ответ
            headers = {"Content-Type": "application/json", "Authorization": "Bearer " + self.key()}

        def work():
            try:
                req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
                with urllib.request.urlopen(req, timeout=300) as r:
                    self.net.done.emit(json.loads(r.read().decode("utf-8")), None)
            except urllib.error.HTTPError as e:
                try:
                    e.detail = e.read().decode("utf-8", "replace")
                except Exception:  # noqa: BLE001
                    e.detail = ""
                self.net.done.emit(None, e)
            except Exception as e:  # noqa: BLE001
                self.net.done.emit(None, e)
        threading.Thread(target=work, daemon=True).start()

    def _parse(self, data):
        """→ (текст, вызовы) в общем виде: [{"id", "function": {"name", "arguments": dict}}]."""
        if self.local():
            msg = data.get("message", {})
        else:
            msg = (data.get("choices") or [{}])[0].get("message", {})
        content = msg.get("content") or ""
        if isinstance(content, list):     # некоторые API отдают текст кусочками
            content = "".join(c.get("text", "") for c in content if isinstance(c, dict))
        calls = []
        for i, c in enumerate(msg.get("tool_calls") or []):
            fn = c.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except ValueError:
                    args = {}
            call = {"id": c.get("id") or f"call_{self.rounds}_{i}",
                    "function": {"name": fn.get("name", ""), "arguments": args}}
            if c.get("extra_content"):          # Gemini: «подпись размышлений», её надо вернуть
                call["extra_content"] = c["extra_content"]
            calls.append(call)
        return content, calls

    def _on_http(self, data, err):
        if (err is not None and isinstance(err, urllib.error.HTTPError) and err.code == 400
                and "reasoning" in getattr(err, "detail", "").lower() and not getattr(self, "no_effort", False)):
            self.no_effort = True
            self.rounds -= 1
            self._request()
            return
        if err is not None and self._should_retry(err):
            return
        if err is not None:
            self.busy = False
            self.status("")
            # убираем незаконченный ход, чтобы история осталась целой
            while self.history and self.history[-1]["role"] != "user":
                self.history.pop()
            if self.history:
                self.history.pop()
            self.on_reply(self._explain(err))
            return
        self.status("")
        content, calls = self._parse(data)
        content = self._take_transcript(content)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
        content = re.sub(r"^.*?</think>", "", content, flags=re.S).strip()
        if self.local():                         # страховки только для маленьких локальных моделей
            if not calls:
                calls = text_tool_calls(content)  # модель написала вызов текстом — выполним его сами
                for i, c in enumerate(calls):
                    c["id"] = f"call_{self.rounds}_{i}"
                if calls:
                    content = ""
            if not calls and looks_like_reasoning(content):
                if not self.nudge:               # одна повторная попытка с жёсткой подсказкой
                    self.nudge = True
                    self._request()
                    return
                content = salvage(content, self.w.cfg["address"])
            if calls and looks_like_reasoning(content):
                content = ""
        if calls and self.rounds <= 5:
            self.history.append({"role": "assistant", "content": content, "tool_calls": calls})
            self.tool_results = []
            self.lead = content
            self._run_tools(calls, 0)
            return
        self.busy = False
        if not content:
            content = "Готово."
        self.history.append({"role": "assistant", "content": content})
        self.nudge = False
        self.on_reply(content)

    def status(self, text):
        cb = getattr(self, "on_status", None)
        if cb:
            cb(text)

    def _should_retry(self, err):
        """Временные сбои сервера: ждём и повторяем, потом пробуем запасную модель."""
        code = err.code if isinstance(err, urllib.error.HTTPError) else None
        transient = code in (429, 500, 502, 503, 504) or (
            code is None and isinstance(err, (urllib.error.URLError, TimeoutError, ConnectionError)) and not self.local())
        if not transient:
            return False
        p = PROVIDERS[self.provider()]
        if self.retries < 2:
            self.retries += 1
            delay = 2000 if self.retries == 1 else 5000
            self.status("Сервер занят, пробую ещё раз…")
        elif not self.use_fallback and p.get("fallback") and code != 429:
            self.use_fallback = True
            self.retries = 0
            delay = 500
            self.status("Пробую запасную модель…")
        else:
            return False
        self.rounds -= 1
        QTimer.singleShot(delay, self._request)
        return True

    @staticmethod
    def _server_message(detail):
        """Достаёт человеческий текст ошибки из JSON сервера."""
        try:
            d = json.loads(detail)
            if isinstance(d, list) and d:
                d = d[0]
            e = d.get("error", d)
            return (e.get("message") if isinstance(e, dict) else str(e)) or ""
        except Exception:  # noqa: BLE001
            return (detail or "").strip()[:200]

    def _explain(self, err):
        if isinstance(err, MissingKey):
            return ("Мне нужен ключ, чтобы говорить через " + PROVIDERS[self.provider()]["title"] +
                    ". Открой настройки и вставь его.")
        if isinstance(err, urllib.error.HTTPError):
            if self.local() and err.code == 404:
                return (f"Модель «{self.model()}» не найдена в Ollama. "
                        f"Скачай её командой: ollama pull {self.model()}")
            if err.code in (401, 403):
                return "Ключ не подошёл (или к этой модели нет доступа). Проверь его в настройках."
            if err.code == 429:
                return "Бесплатный лимит на сейчас исчерпан. Подожди минутку и напиши снова."
            if err.code in (500, 502, 503, 504):
                return ("Серверы " + PROVIDERS[self.provider()]["title"].split(" (")[0] +
                        " сейчас перегружены — я пробовал несколько раз. Напиши мне через минутку.")
            if err.code == 404:
                return f"Модель «{self.model()}» не найдена. Выбери другую в настройках."
            msg = self._server_message(getattr(err, "detail", ""))
            return f"Сервер не принял запрос ({err.code}). {msg}".strip()
        if isinstance(err, (urllib.error.URLError, ConnectionError, OSError)):
            if self.local():
                return "Не могу дозваться до Ollama. Проверь, что она запущена (значок ламы в трее)."
            return "Нет связи с сервером. Проверь интернет."
        return f"Что-то пошло не так: {err}"

    def _run_tools(self, calls, i):
        if i >= len(calls):
            if self.local() or self.rounds > 4:
                self._finish_fast()     # маленькой модели второй вызов не нужен — отвечаем сразу
            else:
                self._request()         # умная облачная модель сама ответит по результатам
            return
        fn = calls[i].get("function", {})
        name = fn.get("name", "")
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {}

        def done(result):
            self.tool_results.append((name, str(result)))
            self.history.append({"role": "tool", "tool_name": name, "tool_call_id": calls[i].get("id", ""),
                                 "content": str(result)})
            self._run_tools(calls, i + 1)

        handler = getattr(self, "t_" + name, None)
        if handler is None:
            done(f"Нет такого инструмента: {name}")
            return
        try:
            handler(args, done)
        except Exception as e:  # noqa: BLE001
            done(f"Ошибка: {e}")

    def _finish_fast(self):
        """Ответ собирается из результатов инструментов сразу — экономит второй вызов модели."""
        import random
        addr = self.w.cfg["address"]
        parts = []
        for name, res in self.tool_results:
            low = res.lower()
            if "отказался" in low:
                parts.append(random.choice(["Хорошо, не трогаю.", "Как скажешь — оставлю как есть."]))
            elif name.startswith("list_"):
                parts.append(f"Вот, {addr}:\n{res}")
            elif any(w in low for w in ("не подключено", "нет ", "не нашёл", "не указано", "ошибка", "не ответило")):
                parts.append(res)
            else:
                parts.append(random.choice(["Готово.", "Сделано.", f"Как скажешь, {addr}.", "Уже."]) + " " + res)
        text = "\n".join(parts) or "Готово."
        if self.lead:
            text = self.lead + "\n" + text
        self.busy = False
        self.history.append({"role": "assistant", "content": text})
        self.on_reply(text)

    # ── инструменты: напоминания ──
    def t_get_datetime(self, a, done):
        now = datetime.datetime.now()
        done(f"Сейчас {now.strftime('%H:%M')}, {WEEKDAYS[now.weekday()]}, {now.strftime('%d.%m.%Y')}.")

    def t_set_reminder(self, a, done):
        now = datetime.datetime.now()
        text = (a.get("text") or "").strip() or "то, о чём просили"
        at = None
        if a.get("in_minutes") not in (None, ""):
            at = now + datetime.timedelta(minutes=float(a["in_minutes"]))
        elif a.get("time"):
            hh, mm = re.findall(r"\d+", str(a["time"]))[:2]
            day = now.date()
            if a.get("date"):
                try:
                    day = datetime.date.fromisoformat(a["date"])
                except ValueError:
                    pass
            at = datetime.datetime.combine(day, datetime.time(int(hh) % 24, int(mm) % 60))
            if at <= now and not a.get("date"):
                at += datetime.timedelta(days=1)
        if at is None:
            done("Не указано время. Спроси, когда напомнить.")
            return
        self.w.cfg.setdefault("reminders", []).append({"at": at.isoformat(timespec="minutes"), "text": text})
        self.w.cfg.save()
        when = at.strftime("%H:%M") + ("" if at.date() == now.date() else at.strftime(" %d.%m"))
        done(f"Напоминание поставлено на {when}: {text}")

    def t_list_reminders(self, a, done):
        rs = sorted(self.w.cfg.get("reminders", []), key=lambda r: r["at"])
        self.w.cfg["reminders"] = rs
        if not rs:
            done("Напоминаний нет.")
            return
        done("\n".join(f"{i + 1}. {r['at'].replace('T', ' ')} — {r['text']}" for i, r in enumerate(rs)))

    def t_delete_reminder(self, a, done):
        rs = sorted(self.w.cfg.get("reminders", []), key=lambda r: r["at"])
        n = int(a.get("number", 0)) - 1
        if 0 <= n < len(rs):
            r = rs.pop(n)
            self.w.cfg["reminders"] = rs
            self.w.cfg.save()
            done(f"Удалено напоминание: {r['text']}")
        else:
            done("Нет напоминания с таким номером.")

    # ── инструменты: дела ──
    def t_add_todo(self, a, done):
        t = (a.get("text") or "").strip()
        if not t:
            done("Пустое дело.")
            return
        self.w.cfg.setdefault("todos", []).append({"text": t, "done": False})
        self.w.cfg.save()
        done(f"Добавлено дело: {t}")

    def t_list_todos(self, a, done):
        ts = self.w.cfg.get("todos", [])
        if not ts:
            done("Список дел пуст.")
            return
        done("\n".join(f"{i + 1}. [{'x' if t['done'] else ' '}] {t['text']}" for i, t in enumerate(ts)))

    def t_complete_todo(self, a, done):
        ts = self.w.cfg.get("todos", [])
        n = int(a.get("number", 0)) - 1
        if 0 <= n < len(ts):
            ts[n]["done"] = True
            self.w.cfg.save()
            self.w.swarm.burst(self.w.hua.center().x(), self.w.hua.center().y(), n=4, radius=80)
            done(f"Выполнено: {ts[n]['text']}")
        else:
            done("Нет дела с таким номером.")

    def t_delete_todo(self, a, done):
        ts = self.w.cfg.get("todos", [])
        n = int(a.get("number", 0)) - 1
        if 0 <= n < len(ts):
            t = ts.pop(n)
            self.w.cfg.save()
            done(f"Удалено дело: {t['text']}")
        else:
            done("Нет дела с таким номером.")

    # ── инструменты: вкладки Chrome ──
    def _stale(self, tabs, hours):
        cutoff = (datetime.datetime.now().timestamp() - hours * 3600) * 1000
        return [t for t in tabs if not t.get("pinned") and not t.get("audible") and not t.get("active")
                and t.get("lastAccessed") and t["lastAccessed"] < cutoff]

    def t_count_tabs(self, a, done):
        def got(resp):
            if resp is None:
                done(self.w.bridge.not_connected_text())
                return
            tabs = resp.get("tabs", [])
            done(f"Открыто вкладок: {len(tabs)}. Не открывались больше 3 часов: {len(self._stale(tabs, 3))}.")
        self.w.bridge.request("list", {}, got)

    def t_close_inactive_tabs(self, a, done):
        hours = float(a.get("hours") or 3)

        def got(resp):
            if resp is None:
                done(self.w.bridge.not_connected_text())
                return
            stale = self._stale(resp.get("tabs", []), hours)
            if not stale:
                done(f"Нет вкладок, которые не открывали больше {hours:g} ч.")
                return
            titles = "\n".join("• " + (t.get("title") or t.get("url", ""))[:60] for t in stale[:12])
            more = f"\n…и ещё {len(stale) - 12}" if len(stale) > 12 else ""

            def answer(yes):
                if not yes:
                    done("Пользователь отказался закрывать вкладки.")
                    return
                self.w.eming_flourish_at_cursor()
                self.w.bridge.request("close", {"ids": [t["id"] for t in stale]},
                                      lambda r: done(f"Закрыто вкладок: {len(stale)}." if r else
                                                     "Расширение не ответило."))
            self.w.confirm(f"Закрыть вкладки, которые не открывали больше {hours:g} ч? Их {len(stale)}:\n\n"
                           f"{titles}{more}", answer)
        self.w.bridge.request("list", {}, got)

    # ── инструменты: загрузки ──
    def t_tidy_downloads(self, a, done):
        root = downloads_dir()
        if not os.path.isdir(root):
            done("Не нашёл папку «Загрузки».")
            return
        plan = []
        for name in os.listdir(root):
            p = os.path.join(root, name)
            ext = os.path.splitext(name)[1].lower()
            if not os.path.isfile(p) or ext in PARTIAL or name.startswith("~$"):
                continue
            for folder, exts in EXT.items():
                if ext in exts:
                    plan.append((p, folder))
                    break
        if not plan:
            done("В «Загрузках» и так порядок: раскладывать нечего.")
            return
        counts = {}
        for _, f in plan:
            counts[f] = counts.get(f, 0) + 1
        summary = "\n".join(f"• {f}: {n}" for f, n in counts.items())

        def answer(yes):
            if not yes:
                done("Пользователь отказался от уборки.")
                return
            moved = 0
            for p, folder in plan:
                dst_dir = os.path.join(root, folder)
                os.makedirs(dst_dir, exist_ok=True)
                base, ext = os.path.splitext(os.path.basename(p))
                dst = os.path.join(dst_dir, base + ext)
                k = 1
                while os.path.exists(dst):
                    dst = os.path.join(dst_dir, f"{base} ({k}){ext}")
                    k += 1
                try:
                    shutil.move(p, dst)
                    moved += 1
                except OSError:
                    pass
            done(f"Разложено файлов: {moved} из {len(plan)}.")
        self.w.confirm(f"Разложить файлы из «Загрузок» по папкам? Всего: {len(plan)}\n\n{summary}\n\n"
                       "Ничего не удаляется, только переносится.", answer)

    # ── инструменты: компьютер ──
    def t_find_files(self, a, done):
        q = (a.get("query") or "").strip()
        kind = a.get("kind") or "any"
        kf = tools_pc.known_folder(q) if kind != "file" else None
        if kf and len(q.split()) <= 2:
            self.found = [kf]
            done(f"Это стандартная папка: 1. {kf}")
            return

        def work():
            res = tools_pc.find_paths(q, kind)
            self.net.tool_done.emit(done, res)
        self.found_kind = kind
        threading.Thread(target=work, daemon=True).start()

    def _on_tool_bg(self, done, res):
        if isinstance(res, tuple) and res and res[0] == "app":
            self._app_found(done, res[1], res[2])
        else:
            self._found(done, res)

    def _found(self, done, res):
        self.found = [p for p, _ in res]
        if not res:
            done("Ничего не нашёл по такому названию в папках пользователя.")
            return
        if len(res) == 1:
            p, is_dir = res[0]
            tools_pc.reveal(p)
            done(f"Нашёл и открыл в Проводнике: {p}")
            return
        lines = "\n".join(f"{i + 1}. {'📁' if d else '📄'} {p}" for i, (p, d) in enumerate(res))
        done("Нашёл несколько вариантов (попроси открыть нужный номер):\n" + lines)

    def t_open_in_explorer(self, a, done):
        p = str(a.get("path") or "").strip().strip("«»\"")
        m = re.fullmatch(r"(?:№\s*)?(\d+)", p)
        if m and getattr(self, "found", None):
            n = int(m.group(1)) - 1
            if 0 <= n < len(self.found):
                p = self.found[n]
        if not os.path.exists(p):
            p = tools_pc.known_folder(p) or p
        if not os.path.exists(p):
            res = tools_pc.find_paths(p, "folder", limit=1, max_seconds=2.5)
            if res:
                p = res[0][0]
        if tools_pc.reveal(p):
            done(f"Открыл в Проводнике: {p}")
        else:
            done("Не нашёл такой папки. Можно поискать через find_files.")

    def t_open_app(self, a, done):
        name = (a.get("name") or "").strip()

        def work():
            app = tools_pc.find_app(name)
            self.net.tool_done.emit(done, ("app", name, app))
        threading.Thread(target=work, daemon=True).start()

    def _app_found(self, done, name, app):
        if not app:
            done(f"Не нашёл приложение «{name}» на компьютере. Можно открыть сайт через open_website.")
            return
        try:
            tools_pc.launch_app(app)
            done(f"Запустил {app[0]}.")
        except OSError as e:
            done(f"Не получилось запустить {app[0]}: {e}")

    def t_set_alarm(self, a, done):
        a = dict(a)
        a["text"] = a.get("text") or "Будильник"

        def ok(res):
            rs = self.w.cfg.get("reminders", [])
            if rs and "Напоминание поставлено" in res:
                rs[-1]["alarm"] = True
                self.w.cfg.save()
                res = res.replace("Напоминание поставлено", "Будильник заведён")
            done(res)
        self.t_set_reminder(a, ok)

    # ── инструменты: браузер ──
    def t_open_website(self, a, done):
        url = site_url(a.get("site", ""))
        where = open_url(url)
        done(f"Открыл {url} в {where}.")

    def t_search_web(self, a, done):
        from urllib.parse import quote
        q = (a.get("query") or "").strip()
        if not q:
            done("Не сказано, что искать.")
            return
        if a.get("where") == "youtube":
            url = "https://www.youtube.com/results?search_query=" + quote(q)
        else:
            url = "https://www.google.com/search?q=" + quote(q)
        where = open_url(url)
        done(f"Открыл поиск «{q}» в {where}.")

    # ── инструменты: развлечения ──
    def t_start_focus(self, a, done):
        m = int(a.get("minutes") or 25)
        self.w.start_focus(m)
        done(f"Фокус включён на {m} минут.")

    def t_roll_dice(self, a, done):
        res = self.w.roll_dice_result(bool(a.get("question")))
        done(res)

    def t_show_magic(self, a, done):
        e = a.get("effect")
        if e == "rain":
            self.w.crimson_rain()
        elif e == "eming":
            if self.w.eming.state == "sheathed":
                self.w.eming.release()
        else:
            self.w.swarm.release(20)
        done("Готово.")
