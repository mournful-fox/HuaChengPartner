"""Хуа Чен на рабочем столе — десктоп-компаньон по мотивам DeskPartner.

Запуск:  python main.py   (или pythonw main.py — без чёрного окна консоли)
"""
import datetime
import math
import os
import random
import sys

from PySide6.QtCore import QElapsedTimer, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QCursor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
                               QSpinBox, QSystemTrayIcon)

import ipc
import phrases
from characters import NAMES, detect, me, set_current
from config import Config
from evening import EveningMixin
from life import LifeMixin
import effects
from effects import (Bubble, ButterflySprite, CrimsonRain, DiceRoll, Overlay, Particles,
                     RedString, Slash, Swarm)
from agent import Agent
from bridge import Bridge
from chat import ChatWindow, ConfirmCard
from eming import EMingWindow
from hua import HuaWindow
from phrases import greeting, plural_days, say

APP = "HuaChengPartner"


def base_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


class World(LifeMixin, EveningMixin):
    def __init__(self, app):
        self.app = app
        self.char = me()
        self.cfg = Config.load(self.char.id)
        if self.char.phrases:
            phrases.PHRASES = self.char.phrases
        phrases.PHRASES.setdefault("wake", ["Мм… Я не спал. Просто прикрыл глаз."])
        if not self.char.butterflies:
            self.cfg["butterflies"] = 0
            self.cfg["red_string"] = False
        self.remote, self.remote_t, self.remote_seen = None, 0.0, False
        self.extra = None
        scr = QGuiApplication.primaryScreen()
        self.screen_geo = scr.geometry()
        self.avail = scr.availableGeometry()
        self.now = 0.0
        self.hua = None
        import json
        if os.path.exists(self.asset("butterfly.png")):
            with open(self.asset("poses.json"), encoding="utf-8") as f:
                effects.SPRITE = ButterflySprite(self.asset("butterfly.png"), json.load(f)["butterfly"]["body"])
        self.overlay = Overlay(self)
        self.hua = HuaWindow(self)
        self.eming = EMingWindow(self)
        self.swarm = Swarm(self)
        self.string = RedString(self)
        self.effects = []
        self.bubbles = []
        self.focus_until = None
        self.break_until = None
        self.hidden = False
        self.next_speech = self.schedule_speech(first=True)
        self.last_hour_talk = None

        self.icon = (QIcon(self.asset("icon.png")) if os.path.exists(self.asset("icon.png"))
                     else make_icon(self.asset("butterfly.png")))
        app.setWindowIcon(self.icon)
        self.build_menu()
        self.tray = QSystemTrayIcon(self.icon)
        self.tray.setToolTip(self.char.name)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.on_tray)
        self.tray.show()

        self.overlay.show()
        self.hua.show()
        self.hua.raise_()

        self.clock = QElapsedTimer()
        self.clock.start()
        self.last_ms = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self.raise_timer = QTimer()
        self.raise_timer.timeout.connect(self.keep_on_top)
        self.raise_timer.start(4000)
        self.save_timer = QTimer()
        self.save_timer.timeout.connect(self.cfg.save)
        self.save_timer.start(60000)
        self.fs_hidden = False
        self.fs_timer = QTimer()
        self.fs_timer.timeout.connect(self.check_fullscreen)
        self.fs_timer.start(1500)
        self.hotkey = install_hotkey(app, {0x4843: self.toggle_hidden, 0x4844: self.open_chat,
                                           0x4845: self.toggle_voice, 0x4846: self.look_screen,
                                           0x4847: self.clipboard_action})
        import tools_pc
        self.tools_pc = tools_pc
        self.recorder = tools_pc.Recorder()
        self.voice_timer = QTimer()
        self.voice_timer.setSingleShot(True)
        self.voice_timer.timeout.connect(lambda: self.recorder.active and self.toggle_voice())
        self.alarm_card = None
        self.agent = Agent(self)
        self.bridge = Bridge(self)
        self.chat = None
        self.cards = []
        self.thinking = False
        self.last_rem_check = 0.0
        QTimer.singleShot(4000, self.agent.warmup)   # заранее загрузить модель в память
        self.setup_life()
        if self.char.module:                     # личный модуль персонажа: его эффекты, занятия и умения
            import importlib
            self.extra = importlib.import_module(self.char.module).Extra(self)
            self.build_menu()
            self.tray.setContextMenu(self.menu)
        self.setup_evening()
        self.ev_timer = QTimer()
        self.ev_timer.timeout.connect(lambda: self.char.id == "hua" and not self.char.guest
                                      and (self.check_evening(), self.check_lan()))
        self.link = ipc.Link(self, self.char.id)
        if self.char.guest:                      # нас позвали в гости: ждём указаний хозяина сцены
            self.remote = {"x": self.avail.right() + 600, "op": 0.0, "pose": "idle"}
        self.ev_timer.start(20000)
        # прописываемся в автозапуск при каждом старте (на случай, если .exe переложили в другую папку)
        set_autostart(self.cfg["autostart"])

        if not self.char.guest:
            QTimer.singleShot(1500, lambda: self.talk(text=self.greet_text()))

    # ── утилиты ──
    def asset(self, name):
        return os.path.join(base_dir(), "assets", name)

    def floor_y(self):
        return self.avail.bottom() + 1

    def is_night(self):
        h = datetime.datetime.now().hour
        return h >= 23 or h < 6

    def raining(self):
        return any(isinstance(fx, CrimsonRain) and fx.age < fx.dur for fx in self.effects)

    def add_dust(self, x, y):
        self.effects.append(Particles("dust", x, y))

    def add_hearts(self, x, y):
        self.effects.append(Particles("heart", x, y))

    def add_zzz(self, x, y):
        self.effects.append(Particles("zzz", x, y))

    def check_fullscreen(self):
        """Прячется, пока открыта полноэкранная игра или видео."""
        if not self.cfg.get("hide_fullscreen", True) or self.hidden and not self.fs_hidden:
            return
        fs = foreground_is_fullscreen(self.screen_geo) and not self.cards
        self.fs_hits = (getattr(self, "fs_hits", 0) + 1) if fs else 0
        fs = self.fs_hits >= 2                      # две проверки подряд — не реагируем на мелькание
        if fs and not self.hidden:
            self.fs_hidden = True
            self.toggle_hidden()
        elif not fs and self.fs_hidden:
            self.fs_hidden = False
            self.toggle_hidden()

    def focus_active(self):
        return self.focus_until is not None

    def keep_on_top(self):
        if self.hidden:
            return
        self.overlay.raise_()
        self.hua.raise_()
        if self.eming.isVisible():
            self.eming.raise_()

    # ── главный цикл ──
    def tick(self):
        ms = self.clock.elapsed()
        if self.remote and ms / 1000.0 - self.remote_t > (4 if self.remote_seen else 90):
            self.release_remote()                # хозяин сцены пропал
        dt = min(0.05, (ms - self.last_ms) / 1000.0)
        self.last_ms = ms
        self.now = ms / 1000.0
        if self.hidden:
            return
        self.hua.step(dt)
        self.eming.step(dt)
        self.swarm.step(dt)
        self.life_tick(dt)
        if self.extra:
            self.extra.tick(dt)
        self.evening_tick(dt)
        self.effects = [fx for fx in self.effects if fx.step(dt)]
        self.bubbles = [b for b in self.bubbles if b.step(dt)]
        if self.cfg["red_string"]:
            self.string.update_path()
        self.step_timers()
        self.overlay.refresh()

    def dirty_rects(self):
        rects = list(self.swarm.bounds())
        for fx in self.effects:
            rects += fx.bounds()
        for b in self.bubbles:
            b.layout(self.screen_geo)
            rects += b.bounds()
        if self.cfg["red_string"]:
            rects += self.string.bounds()
        if self.focus_active():
            rects.append(self.focus_rect())
        rects += self.life_rects()
        if self.extra:
            rects += self.extra.rects()
        return rects

    def draw_overlay(self, p):
        if self.cfg["red_string"]:
            self.string.draw(p)
        for fx in self.effects:
            fx.draw(p)
        self.swarm.draw(p)
        self.draw_life(p)
        if self.extra:
            self.extra.draw(p)
        for b in self.bubbles:
            if b.anchor_fn == self.hua_anchor and not self.hua.visible_now():
                continue  # пока он рассыпан на бабочек, облачко прячется
            b.draw(p, self.screen_geo)
        if self.focus_active():
            self.draw_focus(p)

    # ── реплики ──
    def schedule_speech(self, first=False):
        lo, hi = sorted((max(1, int(self.cfg["speech_min"])), max(1, int(self.cfg["speech_max"]))))
        if first:
            return self.now + 60 * random.uniform(lo * 0.3, lo)
        return self.now + 60 * random.uniform(lo, hi)

    def bubble(self, anchor_fn, kind=None, text=None, owner="hua"):
        if text is None:
            text = say(kind, self.cfg["address"])
        self.bubbles = [b for b in self.bubbles if b.owner != owner]
        self.bubbles.append(Bubble(anchor_fn, text, owner))

    def hua_anchor(self):
        h = self.hua.head()
        return QPointF(h.x(), h.y() - (30 if self.focus_active() else 0))

    def talk(self, kind=None, text=None):
        if not self.hua.isVisible():
            return
        if self.ev or self.lz_state:                 # идёт сценка — реплика встаёт в общую очередь, чтобы не наложиться
            self.enqueue(None, text if text is not None else say(kind, self.cfg["address"]), opt=True)
            return
        self.bubble(self.hua_anchor, kind, text, owner="hua")

    def time_kind(self):
        h = datetime.datetime.now().hour
        if 6 <= h < 11:
            return "morning"
        if 12 <= h < 15:
            return "day"
        if 18 <= h < 23:
            return "evening"
        if h >= 23 or h < 5:
            return "night"
        return "random"

    def step_timers(self):
        if self.now - self.last_rem_check > 1.0:
            self.last_rem_check = self.now
            self.check_reminders()
        if self.thinking and int(self.now * 2) % 6 == 0 and not any(b.owner == "think" for b in self.bubbles):
            self.bubble(self.hua_anchor, text="…", owner="think")
        if self.now > self.next_speech:
            self.next_speech = self.schedule_speech()
            if not self.focus_active() and not self.remote and not self.ev and not self.lz_state:
                tk = self.time_kind()
                self.talk(tk if tk != "random" and random.random() < 0.45 else "random")
        if self.focus_until is not None and self.now > self.focus_until:
            self.focus_until = None
            self.break_until = self.now + 5 * 60
            self.reward("focus")
            self.swarm.recall()
            # бабочка-вестник летит к курсору
            c = QCursor.pos()
            h = self.hua.anchor("hand")
            msg = self.swarm.spawn_temp(h.x(), h.y(), goal=(c.x() + 30, c.y() - 30), then="guard", maxs=420)
            msg.life = 5
            self.bubble(lambda: QPointF(msg.x, msg.y - 10), "focus_end", owner="hua")
            self.tray.showMessage(self.char.name + "", "Перерыв! Пять минут отдыха.", self.icon, 4000)
            self.update_focus_action()
        if self.break_until is not None and self.now > self.break_until:
            self.break_until = None
            self.talk("break_end")

    # ── агент ──
    def open_chat(self):
        if self.hidden:
            self.toggle_hidden()
        if self.chat is None:
            self.chat = ChatWindow(self)
        if self.hua.state == "sleep":
            self.hua.wake()
        self.chat.open()

    def hua_thinking(self, on):
        self.thinking = on
        if on:
            self.swarm.perch()
        else:
            self.bubbles = [b for b in self.bubbles if b.owner != "think"]

    def confirm(self, text, callback):
        card = ConfirmCard(self, text, lambda yes: (self.cards.remove(card) if card in self.cards else None,
                                                    callback(yes)))
        self.cards.append(card)

    def eming_flourish_at_cursor(self):
        c = QCursor.pos()
        self.add_slash(c.x(), c.y(), random.uniform(-40, 40), 120)

    def start_focus(self, minutes=25):
        self.focus_until = self.now + minutes * 60
        self.break_until = None
        if self.hua.state not in ("teleport", "drag"):
            self.hua.enter("idle")
        self.update_focus_action()

    def roll_dice_result(self, question):
        if question:
            faces = [random.randint(1, 6), random.randint(1, 6)]
            ans = "да" if sum(faces) % 2 == 0 else "нет"
            self.roll_dice(question, quiet=True, faces=faces)
            return f"Выпало {faces[0]} и {faces[1]}, сумма {sum(faces)} — ответ «{ans}»."
        self.roll_dice(False, quiet=True)
        return "Выпали две шестёрки, как всегда."

    def check_reminders(self):
        rs = self.cfg.get("reminders") or []
        if not rs:
            return
        now = datetime.datetime.now()
        due = [r for r in rs if datetime.datetime.fromisoformat(r["at"]) <= now]
        if not due:
            return
        self.cfg["reminders"] = [r for r in rs if r not in due]
        self.cfg.save()
        for r in due:
            if r.get("alarm"):
                self.fire_alarm(r["text"])
            else:
                self.fire_reminder(r["text"])

    def fire_reminder(self, text):
        if self.hidden:
            self.toggle_hidden()
        if self.hua.state == "sleep":
            self.hua.wake()
        c = QCursor.pos()
        h = self.hua.anchor("hand")
        msg = self.swarm.spawn_temp(h.x(), h.y(), goal=(c.x() + 30, c.y() - 30), then="guard", maxs=420)
        msg.life = 8
        addr = self.cfg["address"]
        line = f"{addr[:1].upper() + addr[1:]}, напоминаю: {text}"
        self.bubbles = [b for b in self.bubbles if b.owner != "hua"]
        self.bubbles.append(Bubble(lambda: QPointF(msg.x, msg.y - 10), line, "hua", duration=12))
        self.tray.showMessage(self.char.name + " напоминает", text, self.icon, 10000)

    # ── голос ──
    def toggle_voice(self):
        if self.hidden:
            self.toggle_hidden()
        if not self.agent.can_hear():
            # модель не понимает аудио — включаем голосовой ввод Windows прямо в поле чата
            self.open_chat()
            QTimer.singleShot(400, self.tools_pc.press_win_h)
            self.talk(text="Говори — Windows запишет текст. Потом нажми Enter.")
            return
        if self.recorder.active:
            self.voice_timer.stop()
            self.bubbles = [b for b in self.bubbles if b.owner != "mic"]
            if self.chat:
                self.chat.set_recording(False)
            try:
                wav = self.recorder.stop()
            except OSError as e:
                self.talk(text=f"Запись не сохранилась: {e}")
                return
            if not wav:
                self.talk(text="Я ничего не расслышал. Зажми и скажи ещё раз.")
                return
            self.open_chat()
            self.chat.send_voice(wav)
        else:
            try:
                self.recorder.start()
            except OSError as e:
                self.talk(text=f"Не могу включить микрофон: {e}. Проверь, что микрофон подключён и выбран "
                               "в «Параметры → Система → Звук → Ввод».")
                return
            if self.hua.state == "sleep":
                self.hua.wake()
            self.bubbles = [b for b in self.bubbles if b.owner != "mic"]
            self.bubbles.append(Bubble(self.hua_anchor, "🎙 Слушаю… Ещё раз Ctrl+Alt+V — отправить", "mic",
                                       duration=31))
            if self.chat:
                self.chat.set_recording(True)
            self.voice_timer.start(30000)   # больше 30 секунд не пишем

    # ── будильник ──
    def fire_alarm(self, text):
        if self.hidden:
            self.toggle_hidden()
        if self.hua.state == "sleep":
            self.hua.wake()
        self.tools_pc.play_alarm(os.path.dirname(self.cfg.path))
        self.swarm.release(30)
        addr = self.cfg["address"]
        self.talk(text=f"{addr[:1].upper() + addr[1:]}, пора! {text}")
        self.tray.showMessage(self.char.name + ": будильник", text, self.icon, 10000)
        if self.alarm_card:
            self.alarm_card.close()

        def answer(wake):
            self.tools_pc.stop_alarm()
            self.alarm_card = None
            if wake:
                self.talk(text="Доброе утро. Я рядом.")
            else:
                at = datetime.datetime.now() + datetime.timedelta(minutes=5)
                self.cfg.setdefault("reminders", []).append(
                    {"at": at.isoformat(timespec="minutes"), "text": text, "alarm": True})
                self.cfg.save()
                self.talk(text="Ладно, ещё пять минут. Но только пять.")
        self.alarm_card = ConfirmCard(self, f"⏰ {text}", answer, yes_text="Встаю", no_text="Ещё 5 минут")
        QTimer.singleShot(3 * 60 * 1000, self.tools_pc.stop_alarm)   # не звенеть бесконечно

    def install_extension(self):
        """Копирует расширение в папку настроек и открывает её в Проводнике."""
        import shutil
        dst = os.path.join(os.path.dirname(self.cfg.path), "chrome_extension")
        try:
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(self.asset("chrome_extension"), dst)
        except OSError as e:
            self.talk(text=f"Не вышло скопировать расширение: {e}")
            return
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(dst))
        QGuiApplication.clipboard().setText(dst)
        self.confirm("Как подключить расширение к Chrome:\n\n"
                     "1. Открой в Chrome адрес chrome://extensions\n"
                     "2. Справа вверху включи «Режим разработчика»\n"
                     "3. Нажми «Загрузить распакованное» и выбери папку, которую я только что открыл "
                     "(путь уже скопирован — можно вставить Ctrl+V)\n\n"
                     f"{dst}\n\nГотово? Нажми «Да», и я проверю связь.",
                     lambda yes: yes and QTimer.singleShot(3000, self.check_extension))

    def check_extension(self):
        self.talk(text="Связь с Chrome есть. Теперь могу разбирать твои вкладки."
                  if self.bridge.connected() else
                  "Пока не вижу расширение. Проверь, что оно включено, и перезапусти Chrome.")

    # ── эффекты ──
    def add_slash(self, x, y, angle, radius):
        self.effects.append(Slash(x, y, angle, radius))
        # бабочек рядом разносит в стороны
        for b in self.swarm.items:
            dx, dy = b.x - x, b.y - y
            d = math.hypot(dx, dy)
            if d < radius * 1.5:
                b.vx += dx / (d or 1) * 500
                b.vy += dy / (d or 1) * 500

    def roll_dice(self, question=False, quiet=False, faces=None):
        if self.hua.busy() or self.hua.state == "sleep":
            return
        self.cfg["dice"] += 1
        self.hua.enter("dice", dur=2.6)
        QTimer.singleShot(250, lambda: self._throw(question, quiet, faces))

    def _throw(self, question, quiet, faces=None):
        h = self.hua.anchor("hand")
        if question:
            faces = faces or [random.randint(1, 6), random.randint(1, 6)]
            kind = "dice_yes" if sum(faces) % 2 == 0 else "dice_no"
        else:
            faces = [6, 6]
            kind = "dice_lucky"
        self.effects.append(DiceRoll(self, h.x(), h.y(), faces,
                                     (lambda: None) if quiet else (lambda: self.talk(kind))))

    def crimson_rain(self):
        if any(isinstance(fx, CrimsonRain) for fx in self.effects):
            return
        self.effects.insert(0, CrimsonRain(self))
        if self.hua.state in ("idle", "walk", "sleep"):
            self.hua.enter("rain")
        QTimer.singleShot(900, lambda: self.talk("rain"))

    def slash_big(self):
        if self.eming.state == "sheathed":
            c = self.hua.anchor("hip")
            self.add_slash(c.x() - 40, c.y() - 40, random.uniform(-60, -20), self.hua.sprite_h * 0.55)
            self.swarm.burst(c.x(), c.y(), n=3, radius=90)
        else:
            self.eming.flourish()

    # ── фокус ──
    def focus_rect(self):
        h = self.hua.head()
        return QRect(int(h.x()) - 50, int(h.y()) - 30, 100, 30)

    def draw_focus(self, p):
        left = max(0, int(self.focus_until - self.now))
        r = self.focus_rect()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(*self.char.theme.get("badge", (45, 10, 16, 200))))
        p.drawRoundedRect(r.adjusted(14, 4, -14, -4), 8, 8)
        p.setPen(QColor(235, 240, 250))
        p.drawText(r, Qt.AlignCenter, f"⌛ {left // 60:02d}:{left % 60:02d}")

    def toggle_focus(self):
        if self.focus_active():
            self.focus_until = None
            self.talk(text="Хорошо. Отдыхай.")
        else:
            self.start_focus(25)
            self.talk("focus_start")
        self.update_focus_action()

    def update_focus_action(self):
        self.a_focus.setText("Остановить фокус" if self.focus_active() else "Фокус на 25 минут")

    # ── меню ──
    def build_menu(self):
        m = QMenu()
        self.menu = m
        m.addAction("Написать ему…  (Ctrl+Alt+Space)", self.open_chat)
        m.addAction("Сказать голосом  (Ctrl+Alt+V)", self.toggle_voice)
        m.addAction("Посмотри на экран  (Ctrl+Alt+S)", self.look_screen)
        m.addAction("Текст из буфера…  (Ctrl+Alt+C)", self.clipboard_action)
        m.addAction("Поговори со мной", lambda: self.talk(random.choice(["random", self.time_kind()])))

        bm = m.addMenu("Бабочки")
        bm.addAction("Выпустить стаю", self.release_swarm)
        bm.addAction("Позвать обратно", lambda: (self.swarm.recall(), self.talk("butterflies_back")))
        self.a_follow = QAction("Пусть летают за курсором", m, checkable=True)
        self.a_follow.setChecked(self.cfg["follow_cursor"])
        self.a_follow.toggled.connect(self.set_follow)
        bm.addAction(self.a_follow)

        em = m.addMenu("Э-Мин")
        em.addAction("Отпустить погулять", lambda: self.eming.state == "sheathed" and self.eming.release())
        em.addAction("Взмах!", self.slash_big)
        em.addAction("Отругать", self.eming.scold)
        em.addAction("К ноге", self.eming.recall)

        dm = m.addMenu("Кости")
        dm.addAction("Бросить на удачу", lambda: self.roll_dice(False))
        dm.addAction("Спросить: да или нет?", lambda: self.roll_dice(True))

        m.addAction("Кровавый дождь", self.crimson_rain)
        fun = m.addMenu("Призрачный город")
        fun.addAction("Лавка…", self.open_shop)
        fun.addAction("Кости на монеты…", self.dice_bet)
        fun.addAction("Поиграть с Э-Мином в мяч", self.play_ball)
        fun.addAction("Запустить фонарики", self.launch_lanterns)
        ev = m.addMenu("Гости")
        ev.addAction("Позвать Вэй Усяня (вечер кино)", self.start_evening)
        ev.addAction("Позвать Лань Чжаня", self.lan_visit)
        ev.addAction("Отпустить гостей", self.end_evening)
        for key, label in (("evening_enabled", "Вэй Усянь приходит вечером сам"),
                           ("lan_enabled", "Лань Чжань приходит по расписанию")):
            act = QAction(label, m, checkable=True)
            act.setChecked(self.cfg.get(key, True))
            act.toggled.connect(lambda v, key=key: self.cfg.__setitem__(key, v))
            ev.addAction(act)
        life = m.addMenu("Дневник и письма")
        life.addAction("Утренняя сводка", self.morning_summary)
        life.addAction("Рассказать, как прошёл день", self.ask_diary)
        life.addAction("Последнее письмо", self.show_last_letter)
        life.addAction("Попросить написать письмо", lambda: self.write_letter(manual=True))
        self.a_guard = QAction("Бабочки-стражи во время фокуса", m, checkable=True)
        self.a_guard.setChecked(self.cfg.get("focus_guard", True))
        self.a_guard.toggled.connect(lambda v: self.cfg.__setitem__("focus_guard", v))
        m.addAction(self.a_guard)
        self.a_string = QAction("Красная нить", m, checkable=True)
        self.a_string.setChecked(self.cfg["red_string"])
        self.a_string.toggled.connect(lambda v: self.cfg.__setitem__("red_string", v))
        m.addAction(self.a_string)
        m.addAction("Исчезнуть и появиться", lambda: self.hua.teleport())
        m.addAction("Уснуть / проснуться",
                    lambda: self.hua.wake() if self.hua.state == "sleep" else self.hua.sleep())
        self.a_focus = m.addAction("Фокус на 25 минут", self.toggle_focus)
        m.addSeparator()
        sm = m.addMenu("Размер")
        for label, px in (("Крошечный", 110), ("Маленький", 150), ("Средний", 190), ("Большой", 250)):
            a = sm.addAction(label, lambda px=px: self.set_size(px))
            a.setCheckable(True)
            a.setChecked(int(self.cfg["size"]) == px)
        self.a_calm = QAction("Спокойный режим (не бродит)", m, checkable=True)
        self.a_calm.setChecked(self.cfg.get("calm", False))
        self.a_calm.toggled.connect(lambda v: self.cfg.__setitem__("calm", v))
        m.addAction(self.a_calm)
        self.a_auto = QAction("Запускать при включении компьютера", m, checkable=True)
        self.a_auto.setChecked(self.cfg["autostart"])
        self.a_auto.toggled.connect(self.set_auto)
        m.addAction(self.a_auto)
        m.addAction("Позвать сюда", self.summon)
        self.a_hide = m.addAction("Спрятать  (Ctrl+Alt+H)", self.toggle_hidden)
        m.addAction("Расширение для Chrome…", self.install_extension)
        m.addAction("Статистика…", self.show_stats)
        m.addAction("Настройки…", self.show_settings)
        m.addSeparator()
        m.addAction("Выход", self.quit)
        self.adapt_menu()

    def show_menu(self, pos):
        self.menu.popup(pos)

    def set_size(self, px):
        self.cfg["size"] = px
        self.hua.load_sprite()
        self.eming.resize_for_size()
        self.swarm.rebuild()
        self.build_menu()
        self.tray.setContextMenu(self.menu)
        self.cfg.save()

    def set_auto(self, v):
        self.cfg["autostart"] = v
        set_autostart(v)
        self.cfg.save()
        self.talk(text="Буду встречать тебя каждый раз, как включишь компьютер." if v
                  else "Хорошо. Позовёшь сама, когда захочешь.")

    def release_swarm(self):
        self.swarm.release(20)
        self.talk("butterflies_out")

    def set_follow(self, v):
        self.cfg["follow_cursor"] = v
        self.swarm.apply_follow()
        if v:
            self.talk("follow_on")

    def on_tray(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.hidden:
                self.toggle_hidden()
            else:
                self.summon()

    def summon(self):
        if self.hidden:
            self.toggle_hidden()
        self.hua.summon()

    def toggle_hidden(self):
        self.hidden = not self.hidden
        for wdg in (self.overlay, self.hua):
            wdg.setVisible(not self.hidden)
        if self.hidden:
            self.eming.hide()
        elif self.eming.state != "sheathed":
            self.eming.show()
        for g in (self.wwx, self.lz):
            if g and (self.hidden or g.opacity > 0):
                g.setVisible(not self.hidden)
        self.a_hide.setText("Показать  (Ctrl+Alt+H)" if self.hidden else "Спрятать  (Ctrl+Alt+H)")

    def data_dir(self):
        return os.path.dirname(self.cfg.path)

    def show_stats(self):
        c = self.cfg
        text = (f"Вместе: {plural_days(c.days_together())}\n"
                f"Погладили: {c['pets']} раз\n"
                f"Телепортов: {c['teleports']}\n"
                f"Бросков костей: {c['dice']}\n"
                f"Монет: {c.get('coins', 0)} · близость: {self.affection_level()[1]} ({self.affection_level()[0]})")
        if self.extra:
            text = self.extra.stats()
        self.tray.showMessage(self.char.name + " — статистика", text, self.icon, 6000)
        if not self.extra:
            self.talk(text=f"Ты гладишь меня уже {c['pets']} раз. Я считаю.")

    def show_settings(self):
        dlg = SettingsDialog(self.cfg)
        if dlg.exec() == QDialog.Accepted:
            old_size = self.cfg["size"]
            dlg.apply()
            if self.cfg["size"] != old_size:
                self.hua.load_sprite()
                self.eming.resize_for_size()
            self.swarm.rebuild()
            self.a_follow.setChecked(self.cfg["follow_cursor"])
            self.a_string.setChecked(self.cfg["red_string"])
            self.a_calm.setChecked(self.cfg.get("calm", False))
            set_autostart(self.cfg["autostart"])
            self.a_auto.setChecked(self.cfg["autostart"])
            self.next_speech = self.schedule_speech()
            self.cfg.save()
            self.agent.reset()
            self.agent.effort_override = None   # новая модель — подбираем уровень размышлений заново
            self.agent.warmup()

    # ── несколько персонажей ──
    def adapt_menu(self):
        """Прячет пункты, которые есть только у Хуа Чена, и добавляет «Позвать друга»."""
        m = self.menu
        for a in m.actions():
            if a.text() in self.char.menu_hide:
                a.setVisible(False)
        if self.extra:
            self.extra.menu(m)
        self.friends_menu = QMenu("Позвать друга")
        self.friends_menu.aboutToShow.connect(self.fill_friends)
        self.friends_action = m.insertMenu(m.actions()[-1], self.friends_menu)
        m.aboutToShow.connect(self.update_friends)
        self.update_friends()

    def friends(self):
        """Другие персонажи, установленные на этом компьютере."""
        return [c for c in NAMES if c != self.char.id and ipc.installed(c)]

    def update_friends(self):
        fr = self.friends()
        self.friends_action.setVisible(bool(fr))
        for a in self.menu.actions():
            if a.text() == "Гости":
                a.setVisible(self.char.id == "hua" and bool(fr))

    def fill_friends(self):
        self.friends_menu.clear()
        for cid in self.friends():
            self.friends_menu.addAction(NAMES[cid], lambda cid=cid: self.agent.t_call_friend(
                {"who": cid}, lambda r: self.talk(text=r)))

    def do_banter(self):
        """Иногда перекидывается репликой с другом, если тот тоже запущен."""
        from characters import BANTER_ALL
        QTimer.singleShot(int(random.uniform(40, 90) * 60000), self.do_banter)
        if self.hidden or self.remote or self.ev or self.focus_active() or self.char.guest:
            return
        mine = BANTER_ALL.get(self.char.id, {})
        for cid in random.sample(list(mine), len(mine)):
            s = ipc.connect(cid, 100)
            if s:
                line, reply = random.choice(mine[cid])
                self.talk(text=self.fmt(line))
                ipc.send(s, {"cmd": "banter", "reply": reply})
                s.waitForBytesWritten(300)
                return

    def on_remote(self, msg):
        cmd = msg.get("cmd")
        if cmd == "state":
            self.remote, self.remote_t, self.remote_seen = msg, self.now, True
        elif cmd == "say":
            if msg.get("dur") and self.hua.isVisible():
                self.bubbles = [b for b in self.bubbles if b.owner != "hua"]
                self.bubbles.append(Bubble(self.hua_anchor, msg.get("text", ""), "hua", duration=float(msg["dur"])))
            else:
                self.talk(text=msg.get("text", ""))
        elif cmd == "release":
            self.release_remote()
        elif cmd == "fx" and self.extra and hasattr(self.extra, "remote_fx"):
            self.extra.remote_fx(msg.get("name"), msg)
        elif cmd == "banter" and not self.remote and not self.hidden:
            QTimer.singleShot(2500, lambda: self.talk(text=self.fmt(msg.get("reply", ""))))
        elif cmd == "summon":
            if self.hidden:
                self.toggle_hidden()
            self.hua.summon()

    def release_remote(self):
        self.remote = None
        if self.char.guest:
            QTimer.singleShot(400, self.quit)    # гость уходит домой
        else:
            self.hua.opacity = 1.0
            self.hua.enter("idle")

    def greet_text(self):
        a = self.cfg["address"]
        d = self.cfg.days_together()
        return self.char.greet[0 if d <= 1 else 1].format(addr=a, Addr=a[:1].upper() + a[1:], days=plural_days(d))

    def quit(self):
        self.cfg.save()
        self.tray.hide()
        self.app.quit()


class SettingsDialog(QDialog):
    def __init__(self, cfg):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.cfg = cfg
        self.setWindowTitle(me().name + " — настройки")
        f = QFormLayout(self)
        self.addr = QComboBox()
        self.addr.setEditable(True)
        self.addr.addItems(["гэгэ", "Ваше Высочество", "Дянься"])
        self.addr.setCurrentText(cfg["address"])
        f.addRow("Как обращаться к тебе:", self.addr)
        self.size = QSpinBox(minimum=90, maximum=500, singleStep=10, value=int(cfg["size"]))
        f.addRow("Рост персонажа (px):", self.size)
        # ── ИИ: где «живёт» мозг Хуа Чена ──
        from agent import PROVIDERS
        self.PROVIDERS = PROVIDERS
        self.keys = dict(cfg.get("api_keys") or {})
        self.cmodels = dict(cfg.get("cloud_models") or {})
        self.prov = QComboBox()
        for pid, p in PROVIDERS.items():
            self.prov.addItem(p["title"], pid)
        self.prov.setCurrentIndex(max(0, self.prov.findData(cfg.get("provider", "ollama"))))
        f.addRow("Мозг (модель ИИ):", self.prov)
        krow = QHBoxLayout()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("вставь API-ключ")
        self.getkey = QPushButton("Получить ключ")
        self.getkey.clicked.connect(self.open_keys)
        krow.addWidget(self.key, 1)
        krow.addWidget(self.getkey)
        self.key_label = QLabel("API-ключ:")
        f.addRow(self.key_label, krow)
        mrow = QHBoxLayout()
        self.model = QComboBox()
        self.model.setEditable(True)
        self.refresh = QPushButton("Обновить список")
        self.refresh.clicked.connect(lambda: self.fill_models(fetch=True))
        mrow.addWidget(self.model, 1)
        mrow.addWidget(self.refresh)
        f.addRow("Модель:", mrow)
        self.cur_prov = self.prov.currentData()
        self.prov.currentIndexChanged.connect(self.on_prov)
        self.load_prov()
        self.bf = QSpinBox(minimum=0, maximum=40, value=int(cfg["butterflies"]))
        f.addRow("Бабочек рядом:", self.bf)
        row = QHBoxLayout()
        self.smin = QSpinBox(minimum=1, maximum=240, value=int(cfg["speech_min"]))
        self.smax = QSpinBox(minimum=1, maximum=240, value=int(cfg["speech_max"]))
        row.addWidget(self.smin)
        row.addWidget(QLabel("–"))
        row.addWidget(self.smax)
        row.addWidget(QLabel("мин"))
        f.addRow("Реплики раз в:", row)
        self.walk = QSpinBox(minimum=1, maximum=60, value=int(cfg["eming_walk_minutes"]))
        f.addRow("Э-Мин гуляет (мин):", self.walk)
        self.string = QCheckBox("Красная нить к курсору", checked=cfg["red_string"])
        self.follow = QCheckBox("Бабочки летают за курсором", checked=cfg["follow_cursor"])
        self.eauto = QCheckBox("Хуа Чен сам отпускает Э-Мина", checked=cfg["eming_auto"])
        self.calm = QCheckBox("Спокойный режим: стоит на месте", checked=cfg.get("calm", False))
        self.fs = QCheckBox("Прятаться в полноэкранных играх и видео", checked=cfg.get("hide_fullscreen", True))
        self.auto = QCheckBox("Запускать вместе с Windows", checked=cfg["autostart"])
        self.auto.setEnabled(sys.platform == "win32")
        for cb in (self.string, self.follow, self.eauto, self.calm, self.fs, self.auto):
            f.addRow(cb)
        if not me().butterflies:                 # настройки бабочек и Э-Мина — только у Хуа Чена
            for wdg in (self.bf, self.walk, self.string, self.follow, self.eauto):
                f.setRowVisible(wdg, False)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    # ── выбор провайдера ──
    def load_prov(self):
        pid = self.prov.currentData()
        cloud = pid != "ollama"
        for w in (self.key, self.getkey, self.key_label):
            w.setVisible(cloud)
        self.key.setText(self.keys.get(pid, ""))
        self.fill_models(fetch=False)

    def save_prov(self):
        pid = self.cur_prov
        if pid == "ollama":
            self.cfg["model"] = self.model.currentText().strip() or "qwen3:4b"
        else:
            self.keys[pid] = self.key.text().strip()
            self.cmodels[pid] = self.model.currentText().strip()

    def on_prov(self):
        self.save_prov()
        self.cur_prov = self.prov.currentData()
        self.load_prov()

    def fill_models(self, fetch):
        from agent import cloud_models
        pid = self.prov.currentData()
        cur = self.model.currentText().strip() if fetch else ""
        self.model.clear()
        if pid == "ollama":
            items = ollama_models(self.cfg) or ["qwen3:4b", "gemma4:e4b", "qwen3:8b"]
            cur = cur or self.cfg.get("model", "qwen3:4b")
        else:
            default = self.PROVIDERS[pid]["model"]
            items = cloud_models(pid, self.key.text().strip()) if fetch else []
            if fetch and not items:
                self.refresh.setText("Не вышло — проверь ключ")
            elif fetch:
                self.refresh.setText(f"Найдено: {len(items)}")
            items = items or ([default] if default else [])
            cur = cur or self.cmodels.get(pid) or default
        self.model.addItems(items)
        self.model.setCurrentText(cur)

    def open_keys(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(self.PROVIDERS[self.prov.currentData()]["keys"]))

    def apply(self):
        c = self.cfg
        c["address"] = self.addr.currentText().strip() or "гэгэ"
        c["size"] = self.size.value()
        self.save_prov()
        c["provider"] = self.prov.currentData()
        c["api_keys"] = self.keys
        c["cloud_models"] = self.cmodels
        c["butterflies"] = self.bf.value()
        c["speech_min"], c["speech_max"] = sorted((self.smin.value(), self.smax.value()))
        c["eming_walk_minutes"] = self.walk.value()
        c["red_string"] = self.string.isChecked()
        c["follow_cursor"] = self.follow.isChecked()
        c["eming_auto"] = self.eauto.isChecked()
        c["autostart"] = self.auto.isChecked()
        c["calm"] = self.calm.isChecked()
        c["hide_fullscreen"] = self.fs.isChecked()


def set_autostart(on):
    if sys.platform != "win32" or me().guest:
        return
    try:
        _set_autostart(on)
    except OSError:
        pass


def _set_autostart(on):
    import winreg
    cid = me().id
    reg_name = APP if cid == "hua" else f"{APP}-{cid}"
    extra = "" if cid == "hua" else f" --as {cid}"
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                         0, winreg.KEY_SET_VALUE)
    try:
        if on:
            if getattr(sys, "frozen", False):
                cmd = f'"{sys.executable}"' + extra
            else:
                pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                cmd = f'"{pyw}" "{os.path.abspath(__file__)}"' + extra
            winreg.SetValueEx(key, reg_name, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, reg_name)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def make_icon(butterfly_path):
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(110, 10, 22))
    p.drawEllipse(1, 1, 62, 62)
    bf = QPixmap(butterfly_path).scaledToHeight(58, Qt.SmoothTransformation)
    p.drawPixmap(int(32 - bf.width() / 2), 3, bf)
    p.end()
    return QIcon(pm)


def foreground_is_fullscreen(screen):
    """Windows: активное окно занимает весь экран (игра, видео) и это не рабочий стол."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return False
    cls = ctypes.create_unicode_buffer(64)
    u.GetClassNameW(hwnd, cls, 64)
    if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "#32769"):
        return False
    if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
        return False
    style = u.GetWindowLongW(hwnd, -16)          # GWL_STYLE
    if style & 0x00C00000 == 0x00C00000:         # есть заголовок — обычное (пусть и развёрнутое) окно
        return False
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return False
    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    dpr = QGuiApplication.primaryScreen().devicePixelRatio()
    w, h = screen.width() * dpr, screen.height() * dpr
    return r.left <= 0 and r.top <= 0 and (r.right - r.left) >= w and (r.bottom - r.top) >= h


def ollama_models(cfg):
    """Список скачанных моделей Ollama (пусто, если Ollama не запущена)."""
    import json
    import urllib.request
    try:
        url = cfg.get("ollama_url", "http://127.0.0.1:11434").rstrip("/") + "/api/tags"
        with urllib.request.urlopen(url, timeout=1.5) as r:
            return [m["name"] for m in json.loads(r.read().decode()).get("models", [])]
    except Exception:  # noqa: BLE001
        return []


def install_hotkey(app, callbacks):
    """Ctrl+Alt+H — спрятать/показать, Ctrl+Alt+Space — написать ему (только Windows)."""
    if me().guest:
        return None
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    from PySide6.QtCore import QAbstractNativeEventFilter

    class Filter(QAbstractNativeEventFilter):
        def nativeEventFilter(self, etype, message):
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312 and msg.wParam in callbacks:   # WM_HOTKEY
                    QTimer.singleShot(0, callbacks[msg.wParam])
                    return True, 0
            except Exception:
                pass
            return False, 0

    f = Filter()
    app.installNativeEventFilter(f)
    ctypes.windll.user32.RegisterHotKey(None, 0x4843, 0x0001 | 0x0002 | 0x4000, ord("H"))
    ctypes.windll.user32.RegisterHotKey(None, 0x4844, 0x0001 | 0x0002 | 0x4000, 0x20)   # пробел
    ctypes.windll.user32.RegisterHotKey(None, 0x4845, 0x0001 | 0x0002 | 0x4000, ord("V"))
    ctypes.windll.user32.RegisterHotKey(None, 0x4846, 0x0001 | 0x0002 | 0x4000, ord("S"))   # экран
    ctypes.windll.user32.RegisterHotKey(None, 0x4847, 0x0001 | 0x0002 | 0x4000, ord("C"))   # буфер
    return f


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setQuitOnLastWindowClosed(False)
    args = sys.argv[1:]
    cid = detect(sys.argv)
    set_current(cid, guest="--guest" in args)
    if ipc.is_running(cid):                     # этот персонаж уже запущен — просто зовём его
        s = ipc.connect(cid)
        ipc.send(s, {"cmd": "summon"})
        s.waitForBytesWritten(300)
        return
    world = World(app)
    ipc.register(cid)
    QTimer.singleShot(int(random.uniform(10, 25) * 60000), world.do_banter)
    app.aboutToQuit.connect(world.cfg.save)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
