"""«Руки» Хуа Чена на компьютере: поиск папок и файлов, Проводник, запуск приложений,
запись с микрофона и звук будильника. Всё — стандартными средствами Windows,
без прав администратора."""
import json
import math
import os
import re
import struct
import subprocess
import tempfile
import threading
import time
import wave

WIN = os.name == "nt"
NO_WINDOW = 0x08000000 if WIN else 0


def home():
    return os.path.expanduser("~")


def known_folders():
    """Основные папки пользователя (с учётом того, что их могли перенести, например в OneDrive)."""
    names = {
        "Рабочий стол": "Desktop", "Документы": "Documents", "Загрузки": "Downloads",
        "Изображения": "Pictures", "Музыка": "Music", "Видео": "Videos",
    }
    out = {}
    if WIN:
        try:
            import ctypes
            guids = {
                "Рабочий стол": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
                "Документы": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
                "Загрузки": "{374DE290-123F-4565-9164-39C4925E467B}",
                "Изображения": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
                "Музыка": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
                "Видео": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
            }
            import uuid
            for ru, g in guids.items():
                b = uuid.UUID(g).bytes_le
                buf = (ctypes.c_byte * 16)(*b)
                p = ctypes.c_wchar_p()
                if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(buf), 0, None, ctypes.byref(p)) == 0:
                    out[ru] = p.value
                    ctypes.windll.ole32.CoTaskMemFree(p)
        except Exception:  # noqa: BLE001
            pass
    for ru, en in names.items():
        out.setdefault(ru, os.path.join(home(), en))
    od = os.environ.get("OneDrive")
    if od and os.path.isdir(od):
        out["OneDrive"] = od
    return {k: v for k, v in out.items() if os.path.isdir(v)}


ALIASES = {
    "рабочий стол": "Рабочий стол", "рабочем столе": "Рабочий стол", "desktop": "Рабочий стол",
    "документ": "Документы", "documents": "Документы",
    "загрузк": "Загрузки", "downloads": "Загрузки", "скачанн": "Загрузки",
    "изображен": "Изображения", "картинк": "Изображения", "фото": "Изображения", "pictures": "Изображения",
    "музык": "Музыка", "music": "Музыка", "видео": "Видео", "videos": "Видео", "onedrive": "OneDrive",
}

SKIP = {"node_modules", "appdata", "$recycle.bin", "__pycache__", ".git", ".venv", "venv", "site-packages"}


def known_folder(name):
    low = (name or "").lower().strip()
    kf = known_folders()
    for alias, ru in ALIASES.items():
        if alias in low and ru in kf:
            # «папка Фото» может быть и обычной папкой с таким именем — известная только при точном совпадении
            return kf[ru]
    return None


def find_paths(query, kind="any", limit=8, max_seconds=4.0, max_depth=6):
    """Ищет папки/файлы по части имени в папках пользователя. kind: folder / file / any."""
    q = (query or "").lower().strip().strip("«»\"'")
    if not q:
        return []
    words = [w for w in re.split(r"\s+", q) if w]
    roots = list(dict.fromkeys(known_folders().values()))
    hits = []
    t0 = time.time()
    for root in roots:
        base_depth = root.rstrip("\\/").count(os.sep)
        for dirpath, dirnames, filenames in os.walk(root):
            if time.time() - t0 > max_seconds:
                break
            depth = dirpath.count(os.sep) - base_depth
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP and not d.startswith(".")
                           and depth < max_depth]
            items = []
            if kind in ("folder", "any"):
                items += [(d, True) for d in dirnames]
            if kind in ("file", "any"):
                items += [(f, False) for f in filenames]
            for name, is_dir in items:
                low = name.lower()
                if all(w in low for w in words):
                    stem = os.path.splitext(low)[0] if not is_dir else low
                    score = 3 if stem == q else 2 if stem.startswith(q) else 1
                    score += 0.5 if is_dir else 0
                    score -= depth * 0.05
                    hits.append((score, os.path.join(dirpath, name), is_dir))
    hits.sort(key=lambda h: (-h[0], len(h[1])))
    seen, out = set(), []
    for _, p, d in hits:
        if p not in seen:
            seen.add(p)
            out.append((p, d))
        if len(out) >= limit:
            break
    return out


def reveal(path):
    """Папку — открыть в Проводнике; файл — показать в Проводнике (выделенным)."""
    path = os.path.normpath(path)
    if not os.path.exists(path):
        return False
    if WIN:
        if os.path.isdir(path):
            os.startfile(path)  # noqa: S606
        else:
            subprocess.Popen(["explorer", "/select,", path], creationflags=NO_WINDOW)
    else:
        subprocess.Popen(["xdg-open", path if os.path.isdir(path) else os.path.dirname(path)])
    return True


# ── приложения ──
_apps = None
_apps_lock = threading.Lock()
APP_ALIASES = {
    "телеграм": "telegram", "телега": "telegram", "хром": "chrome", "гугл хром": "chrome",
    "спотифай": "spotify", "дискорд": "discord", "стим": "steam", "блокнот": "notepad",
    "калькулятор": "calculator", "ворд": "word", "эксель": "excel", "повер поинт": "powerpoint",
    "фотошоп": "photoshop", "зум": "zoom", "скайп": "skype", "ватсап": "whatsapp", "вотсап": "whatsapp",
    "вк": "vk", "обс": "obs", "проводник": "explorer", "параметры": "settings", "настройки windows": "settings",
    "яндекс музык": "яндекс музыка", "фигма": "figma", "нотион": "notion", "обсидиан": "obsidian",
}
BUILTIN = {"notepad": "notepad.exe", "calculator": "calc.exe", "explorer": "explorer.exe",
           "settings": "ms-settings:", "paint": "mspaint.exe"}


def load_apps():
    """Список приложений из меню «Пуск» (Get-StartApps: и обычные программы, и из Microsoft Store)."""
    global _apps
    with _apps_lock:
        if _apps is not None:
            return _apps
        apps = []
        if WIN:
            try:
                ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
                      "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress")
                r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                                   capture_output=True, timeout=20, creationflags=NO_WINDOW)
                data = json.loads(r.stdout.decode("utf-8", "replace") or "[]")
                if isinstance(data, dict):
                    data = [data]
                apps = [(a["Name"], a["AppID"]) for a in data if a.get("Name") and a.get("AppID")]
            except Exception:  # noqa: BLE001
                apps = []
        _apps = apps
        return apps


def preload_apps():
    threading.Thread(target=load_apps, daemon=True).start()


def find_app(name):
    low = (name or "").lower().strip()
    for ru, en in APP_ALIASES.items():
        if ru in low:
            low = low.replace(ru, en)
    low = re.sub(r"^(приложение|программу|программа|прогу)\s+", "", low).strip()
    best, best_score = None, 0
    for title, appid in load_apps():
        t = title.lower()
        if t == low:
            score = 4
        elif t.startswith(low):
            score = 3
        elif low in t:
            score = 2
        elif all(w in t for w in low.split()):
            score = 1
        else:
            continue
        if "uninstall" in t or "удален" in t:
            continue
        if score > best_score or (score == best_score and best and len(title) < len(best[0])):
            best, best_score = (title, appid), score
    if best:
        return best
    for key, exe in BUILTIN.items():
        if key in low:
            return key, exe
    return None


def launch_app(app):
    title, appid = app
    if not WIN:
        return False
    if appid.endswith((".exe", ":")) and "\\" not in appid:
        os.startfile(appid)  # noqa: S606
    else:
        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + appid], creationflags=NO_WINDOW)
    return True


# ── микрофон (Windows MCI — ничего ставить не нужно) ──
class Recorder:
    def __init__(self):
        self.active = False
        self.path = os.path.join(tempfile.gettempdir(), "huacheng_voice.wav")

    def _mci(self, cmd):
        import ctypes
        buf = ctypes.create_unicode_buffer(256)
        err = ctypes.windll.winmm.mciSendStringW(cmd, buf, 256, None)
        if err:
            eb = ctypes.create_unicode_buffer(256)
            ctypes.windll.winmm.mciGetErrorStringW(err, eb, 256)
            raise OSError((eb.value or f"MCI error {err}").rstrip(". "))
        return buf.value

    def start(self):
        if not WIN:
            raise OSError("Запись с микрофона работает только в Windows.")
        try:
            self._mci("close hcrec")
        except OSError:
            pass
        self._mci("open new type waveaudio alias hcrec")
        # Формат задаём целиком и согласованно (иначе часть драйверов отвечает «недопустимое значение»).
        # Если драйвер не принимает ни один вариант — пишем в его формате по умолчанию, модель поймёт любой.
        for fmt in ("time format ms bitspersample 16 channels 1 samplespersec 16000 bytespersec 32000 alignment 2",
                    "time format ms bitspersample 16 channels 1 samplespersec 44100 bytespersec 88200 alignment 2",
                    "time format ms"):
            try:
                self._mci("set hcrec " + fmt)
                break
            except OSError:
                continue
        self._mci("record hcrec")
        self.active = True
        self.t0 = time.time()

    def stop(self):
        """Останавливает запись и возвращает WAV (bytes) или None, если слишком коротко."""
        if not self.active:
            return None
        self.active = False
        try:
            self._mci("stop hcrec")
            self._mci(f'save hcrec "{self.path}"')
        finally:
            try:
                self._mci("close hcrec")
            except OSError:
                pass
        if time.time() - self.t0 < 0.6:
            return None
        with open(self.path, "rb") as f:
            return f.read()


# ── будильник ──
def alarm_wav(folder):
    """Мягкий перезвон (создаётся один раз)."""
    path = os.path.join(folder, "alarm.wav")
    if os.path.exists(path):
        return path
    rate = 22050
    notes = [880.0, 1174.66, 1318.51, 1760.0]
    frames = bytearray()
    for k, f in enumerate(notes * 2):
        n = int(rate * 0.28)
        for i in range(n):
            env = math.exp(-i / (rate * 0.12))
            v = math.sin(2 * math.pi * f * i / rate) * 0.6 + math.sin(4 * math.pi * f * i / rate) * 0.15
            frames += struct.pack("<h", int(v * env * 9000))
    frames += b"\x00\x00" * int(rate * 0.6)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


def play_alarm(folder):
    if WIN:
        import winsound
        winsound.PlaySound(alarm_wav(folder), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)


def stop_alarm():
    if WIN:
        import winsound
        winsound.PlaySound(None, 0)


def press_win_h():
    """Включает голосовой ввод Windows (Win+H) в активном поле ввода."""
    if WIN:
        import ctypes
        k = ctypes.windll.user32.keybd_event
        k(0x5B, 0, 0, 0)
        k(0x48, 0, 0, 0)
        k(0x48, 0, 2, 0)
        k(0x5B, 0, 2, 0)
