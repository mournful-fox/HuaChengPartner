"""«Жизнь» Хуа Чена: таймеры, экранное время, утро и вечер, дневник, письма, праздники,
памятные даты, привязанность и монеты, лавка, кости на ставки, буфер обмена, взгляд на экран,
бабочки-стражи и игра в мяч. Подмешивается в World из main.py."""
import datetime
import math
import random
import re
import time

from PySide6.QtCore import QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout)

import features
from effects import Bubble, DiceRoll

LEVELS = [(0, "знакомство"), (40, "доверие"), (150, "близость"), (400, "преданность"), (1000, "вечность")]
LEVEL_UP = {
    "доверие": "Знаешь, {addr}… с тобой спокойно. Я, кажется, начинаю привыкать к этому столу.",
    "близость": "{Addr}, если бы мне предложили весь Призрачный город или этот угол экрана рядом с тобой — я бы не думал.",
    "преданность": "Что бы ни случилось, {addr}, я буду здесь. Это не обещание — это просто факт.",
    "вечность": "Восемьсот лет я ждал. Ещё вечность рядом с тобой — совсем не страшно.",
}
REWARDS = {   # вид: (привязанность, монеты, лимит в день)
    "pet": (1, 1, 15), "todo": (3, 5, 30), "focus": (5, 10, 10), "diary": (4, 5, 2),
    "daily": (2, 3, 1), "timer": (1, 1, 10),
}
DEFAULT_BLOCKED = ["youtube.com", "tiktok.com", "vk.com", "instagram.com", "x.com", "twitter.com",
                   "reddit.com", "twitch.tv"]


class LifeMixin:
    # ── инициализация ──
    def setup_life(self):
        self.screen_time = features.ScreenTime(self.cfg)
        self.st_timer = QTimer()
        self.st_timer.timeout.connect(self.screen_time.tick)
        self.st_timer.start(features.ScreenTime.STEP * 1000)
        self.daily_timer = QTimer()
        self.daily_timer.timeout.connect(self.check_daily)
        self.daily_timer.start(30000)
        QTimer.singleShot(8000, self.check_daily)
        self.cfg.setdefault("timers", [])
        self.cfg.setdefault("blocked_sites", list(DEFAULT_BLOCKED))
        self.cfg.setdefault("focus_guard", True)
        self.diary_mode = False
        self.pending_image = None
        self.next_petals = 0.0
        self.last_festival = 0.0
        self.ball = None
        self._red_tint = None

    # ── таймеры над головой ──
    def add_timer(self, minutes, label):
        self.cfg["timers"].append({"end": time.time() + minutes * 60, "label": label})
        self.cfg.save()

    def life_tick(self, dt):
        now = time.time()
        due = [t for t in self.cfg["timers"] if t["end"] <= now]
        if due:
            self.cfg["timers"] = [t for t in self.cfg["timers"] if t["end"] > now]
            self.cfg.save()
            for t in due:
                self.timer_done(t["label"])
        if self.ball:
            self.ball.step(dt)
        if self.has("petals") and self.now > self.next_petals and self.hua.visible_now():
            self.next_petals = self.now + random.uniform(35, 70)
            c = self.hua.center()
            self.effects.append(features.Petals(c.x(), c.y()))

    def timer_done(self, label):
        from tools_pc import play_chime
        play_chime(self.data_dir())
        c = QCursor.pos()
        h = self.hua.anchor("hand")
        msg = self.swarm.spawn_temp(h.x(), h.y(), goal=(c.x() + 30, c.y() - 30), then="guard", maxs=420)
        msg.life = 6
        self.bubbles = [b for b in self.bubbles if b.owner != "hua"]
        self.bubbles.append(Bubble(lambda: QPointF(msg.x, msg.y - 10), f"⏲ {label}: время вышло!", "hua", duration=10))
        self.tray.showMessage(self.char.name, f"Таймер «{label}» — время вышло", self.icon, 8000)
        self.reward("timer")

    def timer_rects(self):
        out = []
        h = self.hua.head()
        for i, _ in enumerate(self.cfg["timers"][:3]):
            out.append(QRect(int(h.x()) - 70, int(h.y()) - 58 - i * 22, 140, 22))
        return out

    def draw_life(self, p):
        now = time.time()
        rects = self.timer_rects()
        p.setFont(QFont("Segoe UI", 9))
        for r, t in zip(rects, self.cfg["timers"][:3]):
            left = max(0, int(t["end"] - now))
            text = f"⏲ {t['label'][:14]} {left // 60:02d}:{left % 60:02d}"
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(*self.char.theme.get("badge", (45, 10, 16, 200))))
            w = p.fontMetrics().horizontalAdvance(text) + 16
            rr = QRect(r.center().x() - w // 2, r.top() + 2, w, r.height() - 4)
            p.drawRoundedRect(rr, 8, 8)
            p.setPen(QColor(235, 240, 250))
            p.drawText(rr, Qt.AlignCenter, text)
        if self.has("lantern") and self.hua.visible_now():
            h = self.hua.head()
            features.draw_small_lantern(p, h.x() - self.hua.cur().width() * 0.55, h.y() + 30, self.now)
        if self.has("night_stars") and self.is_night() and self.hua.visible_now():
            h = self.hua.head()
            p.setPen(Qt.NoPen)
            for i in range(6):
                a = (math.sin(self.now * 2 + i * 1.7) + 1) / 2
                x = h.x() + math.cos(i * 1.1) * 70
                y = h.y() - 20 - abs(math.sin(i * 2.3)) * 50
                p.setBrush(QColor(255, 245, 210, int(200 * a)))
                p.drawEllipse(QPointF(x, y), 1.8 + a, 1.8 + a)

    def life_rects(self):
        rects = self.timer_rects()
        h = self.hua.head()
        if self.has("lantern"):
            x = h.x() - self.hua.cur().width() * 0.55
            rects.append(QRect(int(x) - 30, int(h.y()), 60, 70))
        if self.has("night_stars") and self.is_night():
            rects.append(QRect(int(h.x()) - 85, int(h.y()) - 85, 170, 80))
        return rects

    # ── привязанность и монеты ──
    def affection_level(self):
        pts = int(self.cfg.get("affection", 0))
        cur = LEVELS[0]
        for lv in LEVELS:
            if pts >= lv[0]:
                cur = lv
        return pts, cur[1]

    def reward(self, kind):
        aff, coins, limit = REWARDS.get(kind, (0, 0, 0))
        day = datetime.date.today().isoformat()
        cnt = self.cfg.setdefault("reward_counts", {})
        if cnt.get("day") != day:
            cnt.clear()
            cnt["day"] = day
        if cnt.get(kind, 0) >= limit:
            return
        cnt[kind] = cnt.get(kind, 0) + 1
        before = self.affection_level()[1]
        self.cfg["affection"] = int(self.cfg.get("affection", 0)) + aff
        features.add_coins(self.cfg, coins)
        after = self.affection_level()[1]
        if after != before and after in LEVEL_UP and self.char.id == "hua":
            addr = self.cfg["address"]
            c = self.hua.center()
            self.swarm.burst(c.x(), c.y(), n=10, radius=140)
            QTimer.singleShot(800, lambda: self.talk(text=LEVEL_UP[after].format(
                addr=addr, Addr=addr[:1].upper() + addr[1:])))

    def has(self, item):
        return item in self.cfg.get("owned", []) and self.cfg.get("cosmetics", {}).get(item, True)

    # ── ежедневные события ──
    def check_daily(self):
        if self.hidden or self.char.guest or not self.char.daily:
            return
        now = datetime.datetime.now()
        today = now.date().isoformat()
        active = features.idle_seconds() < 120
        if self.cfg.get("last_daily") != today and active:
            self.cfg["last_daily"] = today
            self.reward("daily")
            self.check_dates(now.date())
        if 6 <= now.hour < 12 and self.cfg.get("last_morning") != today and active:
            self.cfg["last_morning"] = today
            QTimer.singleShot(1500, self.morning_summary)
        if 21 <= now.hour <= 23 and self.cfg.get("last_diary_ask") != today and active and not self.focus_active():
            self.cfg["last_diary_ask"] = today
            self.ask_diary()
        if now.hour == 22 and self.cfg.get("last_st_report") != today and active:
            self.cfg["last_st_report"] = today
            self.talk(text="Итог дня: " + self.screen_time.report())
        if now.hour >= 18 and active:
            self.maybe_letter(now.date())
        fest = features.festival_today(self.cfg, now.date())
        if fest and self.now - self.last_festival > 2 * 3600:
            self.last_festival = self.now
            self.celebrate(fest)
        self.cfg.save()

    def check_dates(self, d):
        tomorrow = (d + datetime.timedelta(days=1)).strftime("%d.%m")
        today = d.strftime("%d.%m")
        for item in self.cfg.get("dates", []):
            if item["date"] == today:
                self.tray.showMessage(self.char.name, f"Сегодня: {item['what']}", self.icon, 10000)
                QTimer.singleShot(4000, lambda w=item["what"]: self.talk(text=f"Сегодня {w}. Не забудь, {self.cfg['address']}."))
            elif item["date"] == tomorrow:
                QTimer.singleShot(6000, lambda w=item["what"]: self.talk(text=f"Завтра {w}. Говорю заранее, чтобы ты успела подготовиться."))

    def celebrate(self, fest):
        key, name = fest
        self.effects.insert(0, features.Lanterns(self, duration=25))
        c = self.hua.center()
        self.swarm.burst(c.x(), c.y(), n=8, radius=160)
        addr = self.cfg["address"]
        if key == "birthday":
            text = f"С днём рождения, {addr}. В этот день весь Призрачный город зажигает фонари — для тебя."
        elif key.startswith("days"):
            text = f"Сегодня {name}, {addr}. Я считаю каждый."
        else:
            text = f"{name[:1].upper() + name[1:]}, {addr}. Смотри — фонари плывут."
        QTimer.singleShot(1200, lambda: self.talk(text=text))

    def launch_lanterns(self):
        self.effects.insert(0, features.Lanterns(self, duration=20))

    # ── утренняя сводка ──
    def morning_summary(self):
        lines = [datetime.datetime.now().strftime("Сегодня %d.%m, ") +
                 ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"][
                     datetime.date.today().weekday()] + "."]
        today = datetime.date.today()
        rs = [r for r in self.cfg.get("reminders", []) if r["at"].startswith(today.isoformat())]
        if rs:
            lines.append("Напоминания: " + ", ".join(f"{r['at'][11:16]} — {r['text']}" for r in rs[:5]))
        todos = [t["text"] for t in self.cfg.get("todos", []) if not t["done"]]
        if todos:
            lines.append("Дела: " + "; ".join(todos[:5]) + (" …" if len(todos) > 5 else ""))
        dd = [d["what"] for d in self.cfg.get("dates", []) if d["date"] == today.strftime("%d.%m")]
        if dd:
            lines.append("Особый день: " + ", ".join(dd))
        city = self.cfg.get("city")

        def show(weather=None):
            if weather:
                lines.insert(1, weather)
            addr = self.cfg["address"]
            self.card(f"🦋 Доброе утро, {addr}.\n\n" + "\n".join(lines), [("Спасибо", "ok")], lambda k: None)
        if city:
            import threading

            def work():
                try:
                    w = features.weather(city)
                except Exception:  # noqa: BLE001
                    w = None
                self.agent.net.tool_done.emit(lambda r: show(r[1]), ("plain", w))
            threading.Thread(target=work, daemon=True).start()
        else:
            lines.append("(Скажи мне свой город — буду рассказывать и погоду.)")
            show()

    # ── дневник ──
    def ask_diary(self):
        addr = self.cfg["address"]

        def answer(k):
            if k == "yes":
                self.diary_mode = True
                self.open_chat()
                self.chat.add("hua", "Рассказывай. Я запишу каждое слово, что важно.")
        self.card(f"Как прошёл твой день, {addr}? Расскажешь мне?", [("Не сегодня", "no"), ("Рассказать", "yes")], answer)

    # ── письма ──
    def maybe_letter(self, d):
        last = self.cfg.get("last_letter")
        try:
            ref = datetime.date.fromisoformat(last or self.cfg.get("first_launch"))
        except (TypeError, ValueError):
            ref = d
        if (d - ref).days < 7 or getattr(self, "_letter_busy", False):
            return
        self._letter_busy = True
        self.write_letter()

    def write_letter(self, manual=False):
        mem = "\n".join("- " + m for m in (self.cfg.get("memories") or [])[-20:]) or "- пока немного"
        diary = self.cfg.get("diary") or {}
        week = "\n".join(f"{k}: {diary[k]}" for k in sorted(diary)[-7:]) or "записей нет"
        done = [t["text"] for t in self.cfg.get("todos", []) if t["done"]][-10:]
        prompt = (f"Напиши короткое письмо (5–8 предложений) пользователю от своего лица, в своём характере, "
                  f"обращаясь «{self.cfg['address']}». Тёплое, личное, чуть игривое; опирайся на то, что знаешь, "
                  f"без выдуманных фактов о пользователе. Подпишись в конце. Не цитируй книги.\n"
                  f"Что ты знаешь:\n{mem}\nДневник за неделю:\n{week}\n"
                  f"Сделанные дела: {', '.join(done) or 'нет данных'}\n"
                  f"Вместе уже {self.cfg.days_together()} дн.")

        def got(text):
            self._letter_busy = False
            if not text:
                if manual:
                    self.talk(text="Перо не слушается… Попробую написать позже.")
                return
            self.cfg["last_letter"] = datetime.date.today().isoformat()
            self.cfg.setdefault("letters", []).append({"date": self.cfg["last_letter"], "text": text})
            self.cfg["letters"] = self.cfg["letters"][-20:]
            self.cfg.save()
            h = self.hua.anchor("hand")
            c = QCursor.pos()
            self.swarm.spawn_temp(h.x(), h.y(), goal=(c.x() + 20, c.y() - 20), then="fade", maxs=380)
            QTimer.singleShot(1200, lambda: self.card(f"✉ Письмо от {self.char.gen}\n\n" + text,
                                                      [("Сохранить в сердце", "ok")], lambda k: None))
        self.agent.one_shot(prompt, got)

    def show_last_letter(self):
        ls = self.cfg.get("letters") or []
        if not ls:
            self.talk(text="Я ещё не писал тебе писем. Подожди немного — или попроси, и я возьмусь за перо.")
            return
        L = ls[-1]
        self.card(f"✉ Письмо от {L['date']}\n\n{L['text']}", [("Закрыть", "ok")], lambda k: None)

    # ── карточка с вариантами ──
    def card(self, text, options, callback):
        from chat import ChoiceCard
        c = ChoiceCard(self, text, options, lambda k: (self.cards.remove(c) if c in self.cards else None, callback(k)))
        self.cards.append(c)
        return c

    # ── буфер обмена ──
    def clipboard_action(self):
        text = QGuiApplication.clipboard().text().strip()
        if not text:
            self.talk(text="Буфер обмена пуст. Скопируй текст — и снова позови меня.")
            return
        preview = text[:140] + ("…" if len(text) > 140 else "")
        cyr = len(re.findall(r"[а-яё]", text.lower())) > len(re.findall(r"[a-z]", text.lower()))
        tasks = {
            "tr": f"Переведи на {'английский' if cyr else 'русский'} язык. Выведи только перевод.",
            "ex": "Объясни простыми словами, что здесь написано и что это значит. Коротко, по-русски.",
            "sh": "Сократи этот текст, сохранив смысл. Выведи только сокращённый текст.",
            "fx": "Исправь орфографию, пунктуацию и стиль, не меняя смысла. Выведи только исправленный текст.",
        }

        def go(k):
            if k not in tasks:
                return
            self.hua_thinking(True)
            self.talk(text="Сейчас посмотрю…")

            def got(res):
                self.hua_thinking(False)
                if not res:
                    self.talk(text="Не вышло — модель не ответила. Попробуй ещё раз.")
                    return
                if k != "ex":
                    QGuiApplication.clipboard().setText(res)
                self.open_chat()
                self.chat.add("me", f"[{ {'tr': 'перевести', 'ex': 'объяснить', 'sh': 'сократить', 'fx': 'исправить'}[k]}] {preview}")
                self.chat.add("hua", res)
                self.talk(text="Готово. Результат уже в буфере — вставляй." if k != "ex" else "Объяснил в чате.")
            self.agent.one_shot(tasks[k] + "\n\nТекст:\n" + text[:8000], got)
        self.card(f"Что сделать с текстом из буфера?\n\n«{preview}»",
                  [("Перевести", "tr"), ("Объяснить", "ex"), ("Сократить", "sh"), ("Исправить", "fx"), ("Отмена", "no")], go)

    # ── взгляд на экран ──
    def hide_chat_briefly(self):
        self._hidden_for_shot = [w for w in ([self.chat] if self.chat else []) + list(self.cards) if w.isVisible()]
        for w in self._hidden_for_shot:
            w.hide()

    def show_chat_again(self):
        for w in getattr(self, "_hidden_for_shot", []):
            w.show()
        self._hidden_for_shot = []

    def look_screen(self):
        self.hide_chat_briefly()

        def shoot():
            try:
                self.pending_image = features.screenshot_jpeg_b64()
            except Exception as e:  # noqa: BLE001
                self.show_chat_again()
                self.talk(text=f"Не получилось сделать снимок: {e}")
                return
            self.show_chat_again()
            self.open_chat()
            self.chat.attach_image()
        QTimer.singleShot(250, shoot)

    # ── кости на монеты ──
    def dice_bet(self):
        coins = int(self.cfg.get("coins", 0))
        bet = 10
        if coins < bet:
            self.talk(text=f"У тебя {coins} монет, а ставка — {bet}. Сделай пару дел, и сыграем.")
            return

        def play(k):
            if k not in ("lt", "eq", "gt"):
                return
            user_wins = random.random() < 0.3        # иногда он поддаётся
            win_sums = {"lt": range(2, 7), "eq": [7], "gt": range(8, 13)}[k]
            lose_sums = [s for s in range(2, 13) if s not in win_sums]
            target = random.choice(list(win_sums) if user_wins else lose_sums)
            a = random.randint(max(1, target - 6), min(6, target - 1))
            faces = [a, target - a]
            if user_wins:
                gain = bet * (4 if k == "eq" else 1)
                features.add_coins(self.cfg, gain)
                line = random.choice([f"Выпало {target}. Твоя взяла… На этот раз я позволил. +{gain} монет.",
                                      f"{target}! Хм. Кости сегодня на твоей стороне. +{gain}."])
            else:
                features.add_coins(self.cfg, -bet)
                line = random.choice([f"Выпало {target}. Удача никогда меня не покидает. −{bet} монет.",
                                      f"{target}. Не расстраивайся, {self.cfg['address']}: против меня никто не выигрывает. −{bet}."])
            self.cfg.save()
            if self.hua.busy() or self.hua.state == "sleep":
                self.hua.enter("idle")
            self.hua.enter("dice", dur=2.6)
            h = self.hua.anchor("hand")
            QTimer.singleShot(250, lambda: self.effects.append(DiceRoll(self, h.x(), h.y(), faces,
                                                                        lambda: self.talk(text=line))))
        self.card(f"Ставка {bet} монет (у тебя {coins}). Сколько выпадет на двух костях?\n"
                  "Угадаешь «ровно 7» — получишь вчетверо.",
                  [("Меньше 7", "lt"), ("Ровно 7", "eq"), ("Больше 7", "gt"), ("Отмена", "no")], play)

    # ── лавка ──
    def open_shop(self):
        ShopDialog(self).exec()

    # ── бабочки-стражи ──
    def on_tab(self, url, tab_id):
        if not (self.focus_active() and self.cfg.get("focus_guard", True) and url):
            return
        host = re.sub(r"^https?://(www\.|m\.)?", "", url).split("/")[0].lower()
        if any(host == s or host.endswith("." + s) for s in self.cfg.get("blocked_sites", [])):
            self.bridge.request("close", {"ids": [tab_id]}, lambda r: None)
            left = max(1, int((self.focus_until - self.now) // 60))
            c = self.hua.center()
            self.swarm.burst(c.x(), c.y(), n=4, radius=100)
            if self.extra and hasattr(self.extra, "guard_line"):
                self.talk(text=self.extra.guard_line(host, left))
                return
            self.talk(text=f"Бабочки закрыли {host}. Ещё {left} мин, {self.cfg['address']}. Потом — сколько угодно.")

    # ── мячик для Э-Мина ──
    def play_ball(self):
        if self.ball is None:
            self.ball = features.BallWindow(self)
        c = QCursor.pos()
        if self.eming.state == "sheathed":
            self.eming.release()
        self.ball.start(c.x(), c.y())
        self.talk(text="Брось ему мяч — схвати мышкой и кинь. Э-Мин принесёт.")


class ShopDialog(QDialog):
    def __init__(self, world):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.w = world
        self.setWindowTitle("Лавка Призрачного города")
        self.lay = QVBoxLayout(self)
        self.render()

    def render(self):
        while self.lay.count():
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                while it.layout().count():
                    sub = it.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()
        cfg = self.w.cfg
        pts, lvl = self.w.affection_level()
        self.lay.addWidget(QLabel(f"<b>Монеты: {cfg.get('coins', 0)}</b> · близость: {lvl} ({pts})<br>"
                                  "<small>Монеты дают за дела, фокус, дневник и просто за то, что ты рядом.</small>"))
        owned = cfg.setdefault("owned", [])
        cos = cfg.setdefault("cosmetics", {})
        for key, name, price, desc in features.SHOP:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"<b>{name}</b> — {desc}"), 1)
            if key in owned:
                on = cos.get(key, True)
                b = QPushButton("Выключить" if on else "Включить")
                b.clicked.connect(lambda _=False, k=key: self.toggle(k))
            else:
                b = QPushButton(f"Купить · {price}")
                b.setEnabled(cfg.get("coins", 0) >= price)
                b.clicked.connect(lambda _=False, k=key, p=price: self.buy(k, p))
            row.addWidget(b)
            self.lay.addLayout(row)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        self.lay.addWidget(close)

    def buy(self, key, price):
        cfg = self.w.cfg
        if cfg.get("coins", 0) < price:
            return
        features.add_coins(cfg, -price)
        cfg.setdefault("owned", []).append(key)
        cfg.setdefault("cosmetics", {})[key] = True
        cfg.save()
        self.w.swarm.rebuild()
        self.w.talk(text="Хороший выбор. В Призрачном городе такое не продают кому попало.")
        self.render()

    def toggle(self, key):
        cos = self.w.cfg.setdefault("cosmetics", {})
        cos[key] = not cos.get(key, True)
        self.w.cfg.save()
        self.w.swarm.rebuild()
        self.render()
