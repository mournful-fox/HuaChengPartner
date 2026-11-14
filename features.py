"""Дополнительные возможности Хуа Чена: погода, музыка, снимок экрана, экранное время,
праздники, лавка Призрачного города, фонарики, мячик для Э-Мина.
Рисуется здесь только простое: фонарики, лепестки, мячик, монетки."""
import datetime
import json
import math
import os
import random
import threading
import time
import urllib.parse
import urllib.request

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (QColor, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen,
                           QRadialGradient)
from PySide6.QtWidgets import QWidget

WIN = os.name == "nt"

# ───────────────────────── погода (Open-Meteo, без ключа) ─────────────────────────
WEATHER_CODES = {
    0: "ясно", 1: "в основном ясно", 2: "переменная облачность", 3: "пасмурно", 45: "туман", 48: "изморозь",
    51: "лёгкая морось", 53: "морось", 55: "сильная морось", 61: "небольшой дождь", 63: "дождь",
    65: "сильный дождь", 66: "ледяной дождь", 67: "сильный ледяной дождь", 71: "небольшой снег", 73: "снег",
    75: "сильный снег", 77: "снежные зёрна", 80: "ливень", 81: "ливни", 82: "сильные ливни",
    85: "снегопад", 86: "сильный снегопад", 95: "гроза", 96: "гроза с градом", 99: "сильная гроза с градом",
}


def _get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "HuaChengPartner/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def weather(city):
    """Текущая погода и прогноз на сегодня. Возвращает строку или бросает исключение."""
    g = _get("https://geocoding-api.open-meteo.com/v1/search?count=1&language=ru&name=" + urllib.parse.quote(city))
    res = (g.get("results") or [None])[0]
    if not res:
        return f"Не нашёл город «{city}»."
    lat, lon = res["latitude"], res["longitude"]
    f = _get("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&timezone=auto"
             "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m"
             "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
             "&forecast_days=1" % (lat, lon))
    c, d = f["current"], f["daily"]
    now = WEATHER_CODES.get(c["weather_code"], "")
    day = WEATHER_CODES.get(d["weather_code"][0], "")
    rain = d.get("precipitation_probability_max", [None])[0]
    return (f"{res['name']}: сейчас {round(c['temperature_2m'])}°, ощущается как {round(c['apparent_temperature'])}°, "
            f"{now}, ветер {round(c['wind_speed_10m'])} км/ч. Днём {round(d['temperature_2m_min'][0])}…"
            f"{round(d['temperature_2m_max'][0])}°, {day}" + (f", вероятность осадков {rain}%." if rain is not None else "."))


# ───────────────────────── музыка (медиаклавиши) ─────────────────────────
MEDIA_KEYS = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "volume_up": 0xAF, "volume_down": 0xAE,
              "mute": 0xAD, "stop": 0xB2}


def media(action, times=1):
    if not WIN or action not in MEDIA_KEYS:
        return False
    import ctypes
    vk = MEDIA_KEYS[action]
    for _ in range(max(1, min(int(times), 50))):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
    return True


# ───────────────────────── снимок экрана ─────────────────────────
def screenshot_jpeg_b64(max_w=1400, quality=80):
    """Снимок основного экрана → JPEG в base64 (уменьшенный, чтобы быстро ушёл модели)."""
    import base64
    scr = QGuiApplication.primaryScreen()
    pm = scr.grabWindow(0)
    if pm.width() > max_w:
        pm = pm.scaledToWidth(max_w, Qt.SmoothTransformation)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, "JPG", quality)
    buf.close()
    return base64.b64encode(bytes(ba)).decode()


# ───────────────────────── экранное время ─────────────────────────
FRIENDLY = {"chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox", "telegram": "Telegram",
            "discord": "Discord", "steam": "Steam", "code": "VS Code", "winword": "Word", "excel": "Excel",
            "powerpnt": "PowerPoint", "explorer": "Проводник", "spotify": "Spotify", "obs64": "OBS",
            "photoshop": "Photoshop", "notepad": "Блокнот", "huachengpartner": "Хуа Чен"}


def foreground_app():
    """Имя программы на переднем плане (или None)."""
    if not WIN:
        return None
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = k.OpenProcess(0x1000, False, pid.value)          # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(520)
        if not k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return None
        name = os.path.splitext(os.path.basename(buf.value))[0]
        return FRIENDLY.get(name.lower(), name)
    finally:
        k.CloseHandle(h)


def idle_seconds():
    if not WIN:
        return 0
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    li = LASTINPUTINFO()
    li.cbSize = ctypes.sizeof(li)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li))
    return (ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000.0


class ScreenTime:
    """Раз в 5 секунд отмечает, какая программа открыта (если человек за компьютером)."""
    STEP = 5

    def __init__(self, cfg):
        self.cfg = cfg

    def tick(self):
        if idle_seconds() > 300:
            return
        app = foreground_app()
        if not app:
            return
        day = datetime.date.today().isoformat()
        st = self.cfg.setdefault("screen_time", {})
        d = st.setdefault(day, {})
        d[app] = d.get(app, 0) + self.STEP
        for old in sorted(st)[:-14]:         # храним две недели
            st.pop(old, None)

    def report(self, day=None):
        day = day or datetime.date.today().isoformat()
        d = self.cfg.get("screen_time", {}).get(day, {})
        if not d:
            return "За этот день данных нет."
        total = sum(d.values())
        top = sorted(d.items(), key=lambda kv: -kv[1])[:6]
        fmt = lambda s: f"{s // 3600} ч {s % 3600 // 60} мин" if s >= 3600 else f"{s // 60} мин"  # noqa: E731
        return f"Всего за компьютером: {fmt(total)}. Больше всего: " + ", ".join(f"{a} — {fmt(s)}" for a, s in top)


# ───────────────────────── праздники ─────────────────────────
# Китайский Новый год по годам; Праздник фонарей — 15-й день 1-го месяца (= Новый год + 14 дней).
CNY = {2027: (2, 6), 2028: (1, 26), 2029: (2, 13), 2030: (2, 3)}
MID_AUTUMN = {2026: (9, 25), 2027: (9, 15), 2028: (10, 3)}


def festival_today(cfg, today=None):
    """Возвращает (ключ, название) праздника сегодня или None."""
    t = today or datetime.date.today()
    y = t.year
    if y in CNY:
        cny = datetime.date(y, *CNY[y])
        if t == cny:
            return "cny", "Новый год по лунному календарю"
        if t == cny + datetime.timedelta(days=14):
            return "lantern", "Праздник фонарей"
    if y in MID_AUTUMN and t == datetime.date(y, *MID_AUTUMN[y]):
        return "midautumn", "Праздник середины осени"
    bd = cfg.get("birthday")          # «ДД.ММ»
    if bd and t.strftime("%d.%m") == bd:
        return "birthday", "твой день рождения"
    try:
        days = (t - datetime.date.fromisoformat(cfg.get("first_launch"))).days + 1
    except (TypeError, ValueError):
        days = 0
    if days in (30, 100, 365, 500, 730, 1000):
        return f"days{days}", f"{days} дней вместе"
    return None


class Lanterns:
    """Красные бумажные фонарики плывут снизу вверх по экрану."""

    def __init__(self, world, duration=25.0, count=18):
        self.w = world
        self.age = 0.0
        self.dur = duration
        a = world.screen_geo
        self.items = [[random.uniform(a.left() + 40, a.right() - 40), a.bottom() + random.uniform(20, 600),
                       random.uniform(30, 60), random.uniform(0, math.tau), random.uniform(16, 28)]
                      for _ in range(count)]

    def step(self, dt):
        self.age += dt
        for it in self.items:
            it[1] -= it[2] * dt
            it[3] += dt
            it[0] += math.sin(it[3] * 0.8) * 10 * dt
        return self.age < self.dur

    def draw(self, p):
        fade = max(0.0, min(1.0, (self.dur - self.age) / 3))
        for x, y, _, ph, s in self.items:
            p.save()
            p.translate(x, y)
            p.rotate(math.sin(ph) * 6)
            p.setOpacity(fade)
            glow = QRadialGradient(0, 0, s * 2.2)
            glow.setColorAt(0, QColor(255, 170, 80, 120))
            glow.setColorAt(1, QColor(255, 120, 40, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QPointF(0, 0), s * 2.2, s * 2.2)
            g = QLinearGradient(-s, 0, s, 0)
            g.setColorAt(0, QColor(150, 15, 25))
            g.setColorAt(0.5, QColor(235, 60, 45))
            g.setColorAt(1, QColor(150, 15, 25))
            p.setBrush(g)
            p.drawEllipse(QRectF(-s * 0.8, -s, s * 1.6, s * 2))
            p.setBrush(QColor(210, 160, 60))
            p.drawRect(QRectF(-s * 0.45, -s * 1.08, s * 0.9, s * 0.18))
            p.drawRect(QRectF(-s * 0.45, s * 0.9, s * 0.9, s * 0.18))
            p.setPen(QPen(QColor(200, 20, 30), 1.4))
            p.drawLine(QPointF(0, s * 1.1), QPointF(0, s * 1.6))
            p.restore()
        p.setOpacity(1)

    def bounds(self):
        return [QRect(int(x - s * 2.3), int(y - s * 2.3), int(s * 4.6), int(s * 5)) for x, y, _, _, s in self.items]


# ───────────────────────── лавка Призрачного города ─────────────────────────
SHOP = [
    ("lantern", "Фонарик рядом", 60, "маленький красный фонарик парит рядом с ним"),
    ("petals", "Лепестки", 80, "время от времени вокруг кружат алые лепестки"),
    ("red_bf", "Алые бабочки", 120, "часть бабочек становится алой"),
    ("gold_dust", "Золотая пыльца", 100, "шлейф бабочек становится золотым"),
    ("night_stars", "Ночные искры", 70, "по ночам над ним мерцают искорки"),
]


def add_coins(cfg, n):
    cfg["coins"] = int(cfg.get("coins", 0)) + int(n)
    return cfg["coins"]


class Petals:
    """Несколько лепестков вокруг Хуа Чена (украшение из лавки)."""

    def __init__(self, x, y):
        self.items = [[x + random.uniform(-80, 80), y - random.uniform(60, 160), random.uniform(0, math.tau),
                       random.uniform(25, 45)] for _ in range(6)]
        self.age = 0.0

    def step(self, dt):
        self.age += dt
        for it in self.items:
            it[1] += it[3] * dt
            it[2] += dt * 2
            it[0] += math.sin(it[2]) * 25 * dt
        return self.age < 4.0

    def draw(self, p):
        p.setPen(Qt.NoPen)
        p.setOpacity(max(0.0, min(1.0, (4.0 - self.age) / 1.0)))
        for x, y, ph, _ in self.items:
            p.save()
            p.translate(x, y)
            p.rotate(math.degrees(ph))
            p.setBrush(QColor(215, 35, 55, 220))
            p.drawEllipse(QPointF(0, 0), 5, 2.6 + 1.2 * math.sin(ph * 2))
            p.restore()
        p.setOpacity(1)

    def bounds(self):
        return [QRect(int(x) - 10, int(y) - 10, 20, 20) for x, y, _, _ in self.items]


def draw_small_lantern(p, x, y, t):
    s = 9
    p.save()
    p.translate(x, y + math.sin(t * 1.5) * 4)
    p.rotate(math.sin(t) * 5)
    glow = QRadialGradient(0, 0, s * 2.4)
    glow.setColorAt(0, QColor(255, 170, 80, 110))
    glow.setColorAt(1, QColor(255, 120, 40, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(glow)
    p.drawEllipse(QPointF(0, 0), s * 2.4, s * 2.4)
    p.setBrush(QColor(220, 45, 40))
    p.drawEllipse(QRectF(-s * 0.8, -s, s * 1.6, s * 2))
    p.setBrush(QColor(210, 160, 60))
    p.drawRect(QRectF(-s * 0.45, -s * 1.08, s * 0.9, s * 0.2))
    p.drawRect(QRectF(-s * 0.45, s * 0.9, s * 0.9, s * 0.2))
    p.setPen(QPen(QColor(200, 20, 30), 1.2))
    p.drawLine(QPointF(0, s * 1.1), QPointF(0, s * 1.7))
    p.restore()


# ───────────────────────── мячик для Э-Мина ─────────────────────────
class BallWindow(QWidget):
    """Мячик: бросаешь мышью — Э-Мин ловит и приносит обратно к курсору."""
    R = 13

    def __init__(self, world):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.w = world
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setCursor(Qt.OpenHandCursor)
        s = self.R * 2 + 6
        self.resize(s, s)
        self.x = self.y = 0.0
        self.vx = self.vy = 0.0
        self.held = False          # держит ли мышь
        self.carried = False       # несёт ли Э-Мин
        self.drag = None
        self.until = 0.0
        self.spin = 0.0

    def start(self, x, y):
        self.x, self.y = x, y - 40
        self.vx, self.vy = random.uniform(-200, 200), -300
        self.until = self.w.now + 180
        self.show()
        self.raise_()

    def stop(self):
        self.hide()
        self.carried = False

    def on_ground(self):
        return self.y >= self.w.floor_y() - self.R - 1 and abs(self.vy) < 30

    def step(self, dt):
        if not self.isVisible():
            return
        if self.w.now > self.until:
            self.stop()
            self.w.eming.fetch_done()
            return
        a = self.w.avail
        if not self.held and not self.carried:
            self.vy += 1400 * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            floor = self.w.floor_y() - self.R
            if self.y > floor:
                self.y = floor
                self.vy *= -0.55
                self.vx *= 0.8
                if abs(self.vy) < 40:
                    self.vy = 0
            if self.x < a.left() + self.R or self.x > a.right() - self.R:
                self.vx *= -0.7
                self.x = max(a.left() + self.R, min(a.right() - self.R, self.x))
            self.spin += self.vx * dt * 2
        self.move(int(self.x - self.width() / 2), int(self.y - self.height() / 2))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = self.width() / 2
        p.translate(c, c)
        p.rotate(self.spin)
        g = QRadialGradient(-self.R * 0.35, -self.R * 0.35, self.R * 1.4)
        g.setColorAt(0, QColor(255, 120, 110))
        g.setColorAt(1, QColor(150, 10, 25))
        p.setPen(QPen(QColor(90, 0, 10), 1.2))
        p.setBrush(g)
        p.drawEllipse(QPointF(0, 0), self.R, self.R)
        p.setPen(QPen(QColor(240, 210, 120), 1.6))
        p.drawArc(QRectF(-self.R, -self.R * 0.35, self.R * 2, self.R * 0.7), 0, 180 * 16)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.held = True
            self.carried = False
            self.w.eming.fetch_release()
            g = e.globalPosition()
            self.drag = [(g.x(), g.y(), time.time())]

    def mouseMoveEvent(self, e):
        if self.held:
            g = e.globalPosition()
            self.x, self.y = g.x(), g.y()
            self.drag = (self.drag + [(g.x(), g.y(), time.time())])[-5:]

    def mouseReleaseEvent(self, e):
        if not self.held:
            return
        self.held = False
        (x0, y0, t0), (x1, y1, t1) = self.drag[0], self.drag[-1]
        dt = max(0.016, t1 - t0)
        self.vx = max(-1600, min(1600, (x1 - x0) / dt))
        self.vy = max(-1600, min(1600, (y1 - y0) / dt))
        self.until = self.w.now + 180
        self.w.eming.fetch(self)
