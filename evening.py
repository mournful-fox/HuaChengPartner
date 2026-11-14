"""Вечер кино: после 19:00 Хуа Чен зовёт Вэй Усяня — они пьют «Улыбку императора», играют в кости,
выбирают три фильма и открывают их вкладками. Лань Чжань приходит с 8:00 каждые 3 часа, зовёт Вэй Усяня
в Гусу и уходит; на одиннадцатый раз уводит его за руку, закрывает вкладки с фильмами и открывает
учёбу в Firefox под будильник.

Настройки (config.json): evening_enabled, evening_hour, lan_enabled, lan_start_hour, lan_interval_h,
lan_calls_needed, study_urls, film_query.
"""
import datetime
import math
import random
from urllib.parse import quote

from PySide6.QtCore import QPointF, Qt, QTimer

import ipc
from effects import Bubble, DiceRoll

JACKIE = ["Пьяный мастер (1978)", "Змея в тени орла (1978)", "Молодой мастер (1980)", "Проект А (1983)",
          "Полицейская история (1985)", "Доспехи бога (1986)", "Чудеса (1989)",
          "Доспехи бога 2: Операция Кондор (1991)", "Городской охотник (1993)", "Пьяный мастер 2 (1994)",
          "Разборка в Бронксе (1995)", "Громобой (1995)", "Первый удар (1996)", "Мистер Крутой (1997)",
          "Кто я? (1998)", "Час пик (1998)", "Шанхайский полдень (2000)", "Новая полицейская история (2004)",
          "Миф (2005)", "Запретное царство (2008)", "Маленький большой солдат (2010)",
          "Доспехи бога 3: Миссия Зодиак (2012)", "Иностранец (2017)"]
WUXIA = ["Крадущийся тигр, затаившийся дракон (2000)", "Герой (2002)", "Дом летающих кинжалов (2004)",
         "Проклятие золотого цветка (2006)", "Клятва (2005)", "Однажды в Китае (1991)",
         "Харчевня дракона (1992)", "Китайская история призраков (1987)", "Зу: Воины с волшебной горы (1983)",
         "Прах времён (1994)", "Тень (2018)", "Детектив Ди и тайна призрачного пламени (2010)",
         "Семь мечей (2005)", "Нефритовая династия (2019)", "Инь-ян мастер: Вечная мечта (2020)",
         "Раскрашенная кожа (2008)", "Чародей и Белая змея (2011)", "Битва у Красной скалы (2008)",
         "Бесстрашный (2006)", "Ип Ман (2008)", "Разборки в стиле кунг-фу (2004)",
         "Властелин мастер меча (1990)", "Убийца (2015)"]

POOLS = {
    # пары: (Вэй Усянь, Хуа Чен)
    "drink": [("Хуа Чен, наливай. «Улыбка императора» сама себя не выпьет.", "Пей помедленнее. Погреб не бездонный. Хотя… бездонный."),
              ("За {addr}! Чтоб пришла поскорее.", "За {addr}."),
              ("Спорим, я перепью Князя демонов?", "Смело. Глупо, но смело."),
              ("Это уже пятый? Или шестой?", "Одиннадцатый. Я считаю."),
              ("В Гусу за такое переписывают правила. Ха-ха!", "Хорошо, что мы не в Гусу."),
              ("Откуда у тебя столько вина?", "Проиграл один небожитель. Много раз."),
              ("Вкуснее только в Юньмэне!", "В Призрачном городе вкуснее всё. Но ты продолжай."),
              ("Ик! Это не я.", "Это ты.")],
    "argue": [("Давай смотреть то, где больше драк!", "Смотреть будем то, что выберет {addr}."),
              ("Джеки Чан сам делает трюки. Уважаю!", "Я тоже всё делаю сам. Никто не аплодирует."),
              ("А в конце герой обязательно летает по бамбуку!", "По бамбуку я тоже могу. Не впечатляет."),
              ("{Addr} всё не идёт. Нам больше достанется!", "{Addr} придёт. Я умею ждать."),
              ("Хочу попкорн. У демонов есть попкорн?", "У демонов есть всё. Попкорна нет."),
              ("Если фильм скучный — я буду комментировать.", "Ты будешь комментировать в любом случае."),
              ("Эй, {addr}! Фильмы стынут!", "Вкладки открыты, {addr}. Мы никуда не торопимся."),
              ("А давай сыграю музыку к фильму сам?", "Только без мертвецов в зале."),
              ("Спорим, главный злодей — учитель героя?", "Ты испортил мне три фильма подряд. Молчи."),
              ("Лань Чжань бы уснул на первой минуте.", "Ханьгуан-цзюнь спит по расписанию. Ты — где упадёшь.")],
    "duel_start": [("Сейчас я тебе покажу тёмный путь!", "Покажи. Только панель задач не сломай."),
                   ("Это был мой кувшин! Защищайся!", "Докажи, что твой."),
                   ("Ты жульничал в кости! Дуэль!", "Я просто удачлив. Но изволь."),
                   ("Спорим, мои вороны быстрее твоих бабочек?", "Проверим."),
                   ("Старейшина Илина вызывает Градоначальника!", "Градоначальник скучал. Нападай."),
                   ("Проигравший открывает следующий кувшин!", "Тогда иди за кувшином заранее.")],
    "duel_end": [("Ха-ха-ха! Ничья!", "Ничья. Потому что я поддавался."), ("Ладно-ладно, сдаюсь! Наливай.", "Разумно."),
                 ("Ты дерёшься нечестно! Мне нравится.", "Учился у лучших."), ("Уф… Перерыв на вино!", "Перерыв."),
                 ("Мои вороны требуют реванша.", "Мои бабочки согласны.")],
    "hit_w": ["Ай! Не по голове!", "Щекотно! Ха-ха!", "Мои волосы!", "Нечестно! Их слишком много!", "Эй, лента!", "Ладно, это было красиво."],
    "hit_h": ["Неплохо.", "Талисман? Серьёзно?", "Ворон сел мне на голову. Убери.", "Почти попал.", "Э-Мин, не смейся.", "Хм."],
    "chase": [("Не догонишь, не догонишь!", "Я и не тороплюсь."), ("Отдай кувшин!", "Сначала поймай."),
              ("Кто последний — тот Лань Цижэнь!", "…Это запрещённый приём."), ("Ха-ха! Слишком медленно!", "Я даю тебе фору."),
              ("Лови меня, Градоначальник!", "Зачем ловить то, что само вернётся к вину.")],
    "leap": [("Оп! Привет с другой стороны!", "Ещё раз перепрыгнешь — прибью к полу бабочками."), ("Смотри, как я умею!", "Впечатлён. Нет."),
             ("Выше головы Князя демонов!", "Слезь с неба."), ("Я лёгкий, как талисман!", "И такой же надоедливый.")],
    "prank": [("У тебя что-то на лбу! Ха-ха-ха!", "…Вэй Усянь."), ("Талисман «Не хмурься»! Действует?", "Нет."),
              ("Я изобрёл талисман от скуки. Испытываю на тебе!", "Сейчас ты испытаешь мой."),
              ("Не шевелись, это на удачу!", "Удача мне не нужна. Она у меня есть.")],
    "flute": [("♪ Слушай, это я сам сочинил!", "Только без мертвецов."), ("♪ Чэньцин соскучилась по публике.", "Публика терпит."),
              ("♪ Эту мелодию любят даже демоны!", "Не обобщай."), ("♪ Под неё хорошо пьётся.", "Под всё хорошо пьётся, если это ты.")],
    "dice": [("Опять две шестёрки?! Покажи рукав!", "В рукаве у меня только бабочки."), ("Кости заговорённые!", "Кости честные. Это я — нет."),
             ("Ну хоть раз выпадет пятёрка?", "Нет."), ("Я больше не играю! …Ещё разок.", "Я так и думал.")],
    "calm": [("…Тсс. {Addr} смотрит.", "Вот и молчи."), ("(шёпотом) Наливай.", "(шёпотом) Держи."), ("Хороший фильм?", "Не мешай ей.")],
}
LZ_CALLS = ["Вэй Ин. Возвращайся в Гусу.", "Вэй Ин. Уже поздно.", "Вэй Ин. В Гусу запрещено пить.",
            "Вэй Ин. Идём.", "Вэй Ин. Комендантский час.", "Вэй Ин. Не заставляй повторять.",
            "Вэй Ин. Правило номер семь.", "Вэй Ин.", "Вэй Ин. Довольно.", "Вэй Ин. Последний раз."]
LZ_USER = ["{Addr}. Пора учиться.", "{Addr}. Дела ждут.", "{Addr}. Отдых окончен.", "{Addr}. За работу."]
WWX_REPLY = ["Лань Чжань! Ещё один кувшин!", "Лань Чжань, садись к нам!", "Пять минут! Ну три!",
             "Мы только выбрали фильм!", "Ты такой скучный, Лань Чжань… ха-ха!", "Не слышу, тут шумно!",
             "Хуа Чен, скажи ему!", "Лань-гэгэ, не сердись~", "А если я не пойду?", "…он сейчас правда подойдёт, да?"]


def a_ok(avail, x):
    return avail.left() + 40 <= x <= avail.right() - 40


class RemoteBuddy:
    """Гость — отдельная программа. Здесь только считаем его движения и шлём ему позу и место
    (его картинки хозяину сцены не нужны)."""

    def __init__(self, world, name, sock):
        self.w, self.name, self.sock = world, name, sock
        self.W = world.cfg["size"] * 0.8
        self.k = world.cfg["size"] / 560.0
        self.pose, self.flip = "idle", False
        self.x, self.lift, self.opacity, self.fade = 0.0, 0.0, 0.0, 0
        self.target_x, self.t, self.hop, self.pop = None, 0.0, 0.0, 0.0
        self.vis, self.last, self.last_t = False, None, 0.0
        self.speed, self.jump = 1.0, None

    def show(self):
        self.vis = True

    def hide(self):
        self.vis = False

    def setVisible(self, v):
        pass

    def isVisible(self):
        return self.vis

    def set_pose(self, pose, flip=None):
        self.pose = pose
        if flip is not None:
            self.flip = flip

    def head(self):
        return QPointF(self.x, self.w.floor_y() - self.w.cfg["size"] - 2)

    def walk_to(self, x):
        self.target_x = x

    def arrived(self):
        return self.target_x is None and self.jump is None

    def jump_to(self, x, height=110, dur=0.9, then=None):
        """Прыжок по дуге в точку x; then — куда бежать после приземления."""
        self.target_x = None
        self.jump = {"x0": self.x, "x1": x, "h": height, "t": 0.0, "dur": dur, "then": then}
        self.set_pose("laugh" if self.name == "wwx" else "idle", x < self.x)

    def fx(self, name, **args):
        """Просит гостя показать его собственный приём (талисман, вороны, волна…)."""
        ipc.send(self.sock, dict(args, cmd="fx", name=name))

    def step(self, dt):
        self.t += dt
        if self.fade:
            self.opacity = max(0.0, min(1.0, self.opacity + self.fade * dt * 1.5))
            if self.opacity in (0.0, 1.0):
                if self.opacity == 0.0:
                    self.vis = False
                self.fade = 0
        self.lift = 0.0
        if self.jump:
            j = self.jump
            j["t"] += dt
            k = min(1.0, j["t"] / j["dur"])
            self.x = j["x0"] + (j["x1"] - j["x0"]) * k
            self.lift = math.sin(k * math.pi) * j["h"]
            if k >= 1:
                self.target_x = j.get("then")
                self.jump = None
        elif self.target_x is not None:
            d = self.target_x - self.x
            if abs(d) < 3:
                self.target_x = None
                self.set_pose("idle", False)
            else:
                self.x += math.copysign(min(abs(d), 95 * self.k * 2.4 * self.speed * dt), d)
                self.set_pose("walk", d < 0)
                self.lift = abs(math.sin(self.t * 7)) * 7
        elif self.hop:
            self.lift = abs(math.sin(self.t * 9)) * self.hop
        st = {"cmd": "state", "x": round(self.x, 1), "lift": round(self.lift, 1), "pose": self.pose,
              "flip": self.flip, "op": round(self.opacity, 2)}
        if st != self.last or self.t - self.last_t > 0.5:
            self.last, self.last_t = st, self.t
            ipc.send(self.sock, st)

    def release(self):
        ipc.send(self.sock, {"cmd": "release"})


class EveningMixin:
    def summon_guest(self, cid, then):
        """Зовёт гостя: подключается к его программе или запускает её. then(гость) или then(None)."""
        if not self.cfg.get("guests_separate", True):        # режим проверки без второго процесса
            then(RemoteBuddy(self, cid, None))
            return
        sock = ipc.connect(cid)
        if sock:
            then(RemoteBuddy(self, cid, sock))
            return
        try:
            ipc.launch(cid, guest=True)
        except OSError:
            then(None)
            return
        tries = [0]

        def poll():
            s = ipc.connect(cid)
            if s:
                then(RemoteBuddy(self, cid, s))
            elif tries[0] > 40:
                then(None)
            else:
                tries[0] += 1
                QTimer.singleShot(1000, poll)
        QTimer.singleShot(1500, poll)

    def setup_evening(self):
        c = self.cfg
        for k, v in (("evening_enabled", True), ("evening_hour", 19), ("lan_enabled", True),
                     ("lan_start_hour", 8), ("lan_interval_h", 3), ("lan_calls_needed", 10), ("lan_calls", 0),
                     ("study_urls", ["https://app.hackviser.com/login"]),
                     ("film_query", "{title} смотреть онлайн")):
            c.setdefault(k, v)
        self.lz_state, self.lz_t = None, 0.0
        self.ev_summoning = False
        self.ev_free = False           # гость двигается свободно (погоня, дуэль), а не стоит рядом
        self.ev_decks = {}
        self.sq, self.sq_until = [], 0.0
        self.ev_last_kind = None
        self.film_tab_ids = []
        self.ev_act = None
        self.wwx = self.lz = None
        self.ev = None            # текущая фаза или None
        self.ev_t = 0.0           # время в фазе
        self.ev_sub = None
        self.ev_calm = False
        self.ev_films = []

    # ── помощники ──
    def fmt(self, s):
        a = self.cfg["address"]
        return s.format(addr=a, Addr=a[:1].upper() + a[1:])

    # ── реплики в сценах идут строго по очереди: на экране всегда только одна ──
    def say_as(self, who, text, opt=False):
        self.enqueue(who, text, opt)

    def hc_say(self, text, opt=False):
        self.enqueue(None, text, opt)

    def enqueue(self, who, text, opt=False):
        if opt and (self.sq or self.speaking()):     # необязательная реплика не встаёт в очередь
            return
        if len(self.sq) < 10:
            self.sq.append((who, self.fmt(text)))

    def speaking(self):
        return self.now < self.sq_until

    def speech_tick(self):
        if not self.sq or self.speaking():
            return
        who, text = self.sq.pop(0)
        dur = max(2.4, min(6.5, 1.6 + len(text) / 15))
        self.sq_until = self.now + dur + 0.3
        if who is None:
            if self.hua.isVisible():
                self.bubbles = [b for b in self.bubbles if b.owner != "hua"]
                self.bubbles.append(Bubble(self.hua_anchor, text, "hua", duration=dur))
        elif getattr(who, "sock", None):
            ipc.send(who.sock, {"cmd": "say", "text": text, "dur": dur})
        else:
            self.bubbles = [b for b in self.bubbles if b.owner != who.name]
            self.bubbles.append(Bubble(who.head, text, who.name, duration=dur))

    def hop_over(self):
        """Вэй Усянь никогда не проходит сквозь Хуа Чена: если тот на пути — перепрыгивает через него."""
        w, h = self.wwx, self.hua
        if not (w and w.isVisible() and w.target_x is not None and not w.jump and h.isVisible()):
            return
        s = self.cfg["size"]
        d = 1 if w.target_x > w.x else -1
        ahead = (h.fx - w.x) * d                                  # сколько до Хуа Чена по ходу движения
        if 0 < ahead < s * 0.75 and (w.target_x - h.fx) * d > s * 0.3:
            land = h.fx + d * s * 0.8
            if (w.target_x - land) * d < 0:
                land = w.target_x
            w.jump_to(land, s * 1.25, 0.85, then=w.target_x if abs(w.target_x - land) > 3 else None)
            self.add_dust(w.x, self.floor_y())

    LOOKS_LEFT = {("hua", "idle"), ("hua", "drink")}      # позы, нарисованные лицом влево; остальные смотрят вправо

    def turn(self, who, cid, target_x, x):
        """Разворачивает персонажа лицом к точке target_x с учётом того, куда смотрит рисунок позы."""
        if abs(target_x - x) > 5:
            who.flip = (target_x < x) != ((cid, who.pose) in self.LOOKS_LEFT)

    def face_each_other(self):
        """Кто стоит — смотрит на собеседника."""
        h = self.hua
        w = self.wwx if self.wwx and self.wwx.isVisible() else None
        z = self.lz if self.lz and self.lz.isVisible() and self.lz_state != "out" else None
        if w and w.arrived():
            self.turn(w, "wwx", z.x if (z and (self.lz_state == "said" or self.ev == "lan_take")) else h.fx, w.x)
        if z and z.arrived():
            self.turn(z, "lz", w.x if w else h.fx, z.x)
        if h.state != "walk" and (w or z) and (self.ev or self.lz_state):
            self.turn(h, "hua", z.x if (z and not w) else w.x, h.fx)

    def gap(self):
        return self.cfg["size"] * 1.7

    def ev_phase(self, name):
        self.ev, self.ev_t, self.ev_sub = name, 0.0, None

    def hc_pose(self, pose):
        self.hua.enter("scene", pose=pose)

    def check_evening(self):
        now = datetime.datetime.now()
        today = now.date().isoformat()
        if (self.ev is None and self.cfg.get("evening_enabled") and now.hour >= int(self.cfg["evening_hour"])
                and self.cfg.get("last_evening") != today and not self.hidden and not self.focus_active()
                and ipc.installed("wwx")):
            self.start_evening()

    # ── запуск и завершение ──
    def start_evening(self, quiet=False):
        if self.ev or self.ev_summoning:
            return
        self.cfg["last_evening"] = datetime.date.today().isoformat()
        self.cfg.save()
        self.ev_summoning = True
        self.hc_say("Вэй Усянь. За тобой пришли." if quiet else
                    "Вэй Усянь! Солнце село. Выходи — у меня есть «Улыбка императора».")
        self.summon_guest("wwx", lambda b: self.begin_evening(b, quiet))

    def begin_evening(self, buddy, quiet):
        self.ev_summoning = False
        if buddy is None:                            # Вэй Усянь не установлен или не отозвался
            self.hc_say("Вэй Усянь не отзывается. Видно, спит.")
            return
        self.wwx = buddy
        if self.hua.state == "sleep":
            self.hua.wake()
        a = self.avail
        room = a.right() - self.gap() * 1.6
        if self.hua.fx > room:                       # освобождаем место справа для гостя
            self.hua.target_x = room
            self.hua.enter("walk")
        self.ev_calm, self.ev_films = False, []
        w = self.wwx
        w.x, w.opacity, w.fade = a.right() - w.W / 2, 0.0, 1
        w.target_x = None
        w.show()
        self.ev_act = None
        if quiet:
            w.walk_to(self.hua.fx + self.gap())
            self.ev_phase("guest")
        else:
            self.ev_phase("call")

    def end_evening(self, quiet=False):
        from tools_pc import stop_alarm
        stop_alarm()
        gone = [b for b in (self.wwx, self.lz) if b]
        for b in gone:
            if b.isVisible():
                b.fade = -1
        QTimer.singleShot(1500, lambda: [b.release() for b in gone])
        self.ev = None
        self.ev_act, self.ev_free = None, False
        self.lz_state = None
        if self.hua.state == "scene":
            self.hua.enter("idle")
            self.hua.next_decision = self.hua.t + 8
        if not quiet:
            self.hc_say("Гости разошлись. Остались мы с тобой, {addr}.")

    # ── главный шаг (вызывается каждый кадр) ──
    def evening_tick(self, dt):
        for b in (self.wwx, self.lz):
            if b and b.isVisible():
                b.step(dt)
        self.lan_tick(dt)
        self.hop_over()
        self.speech_tick()
        self.face_each_other()
        if not self.ev:
            return
        self.ev_t += dt
        h, w = self.hua, self.wwx
        if h.state in ("idle", "fall") and h.state != "walk" and h.fy >= self.floor_y() - 1:
            self.hc_pose("idle")
        if h.state == "walk" and not self.ev_free:
            return
        if w.arrived() and not self.ev_free and self.ev not in ("call", "lan_take", "leave"):
            side = 1 if (w.x >= h.fx or self.lz_state) else -1      # остаётся с той стороны, где стоит
            if not a_ok(self.avail, h.fx + side * self.gap()):
                side = -side
            goal = h.fx + side * self.gap()
            if abs(goal - w.x) > self.cfg["size"] * 0.6:
                w.speed = 1.6
                w.walk_to(goal)                                 # далеко — идёт (а через Хуа Чена перепрыгнет)
            else:
                w.x += (goal - w.x) * min(1, dt * 6)            # держится рядом с Хуа Ченом
        getattr(self, "ev_" + self.ev)(dt)
        self.face_each_other()                     # ещё раз после смены поз, чтобы не мигал разворот

    def once(self, key):
        """True один раз за фазу для данного ключа."""
        if self.ev_sub is None:
            self.ev_sub = set()
        if key in self.ev_sub:
            return False
        self.ev_sub.add(key)
        return True

    # ── фазы ──
    def ev_call(self, dt):
        w = self.wwx
        if self.once("go"):
            w.walk_to(self.hua.fx + self.gap())
        if w.arrived():
            self.ev_phase("greet")

    def ev_greet(self, dt):
        if self.once("a"):
            self.wwx.set_pose("laugh")
            self.say_as(self.wwx, "Хуа Чен! Ты сказал «Улыбка императора»? Я уже здесь!")
        if self.ev_t > 3.5 and self.once("b"):
            self.hc_say("Целый погреб. Держи кувшин.")
        if self.ev_t > 6:
            self.ev_phase("drink")

    def ev_drink(self, dt):
        if self.once("a"):
            self.hc_pose("drink")
            self.wwx.set_pose("drink", True)
        if self.ev_t > 5 and self.once("b"):
            self.wwx.set_pose("laugh", False)
            self.hc_pose("idle")
            self.say_as(self.wwx, "Вот это вино! Сыграем в кости? На то, кто выбирает фильм.")
        if self.ev_t > 8.5:
            self.ev_phase("dice")

    def ev_dice(self, dt):
        if self.once("a"):
            self.hc_pose("dice")
            hand = self.hua.anchor("hand")
            self.effects.append(DiceRoll(self, hand.x(), hand.y(), [6, 6], lambda: None))
        if self.ev_t > 3.5 and self.once("b"):
            self.wwx.set_pose("angry", True)
            self.say_as(self.wwx, "Опять две шестёрки?! Ты жульничаешь!")
        if self.ev_t > 6.5 and self.once("c"):
            self.hc_pose("idle")
            self.hc_say("Удача. Но выбирать будем вместе — так интереснее.")
        if self.ev_t > 9.5:
            self.ev_phase("pick")

    def pick_films(self):
        seen = self.cfg.get("films_seen", [])
        j = [f for f in JACKIE if f not in seen] or JACKIE
        x = [f for f in WUXIA if f not in seen] or WUXIA
        picks = [random.choice(j), random.choice(x)]
        rest = [f for f in j + x if f not in picks]
        picks.append(random.choice(rest))
        random.shuffle(picks)
        self.cfg["films_seen"] = (seen + picks)[-24:]
        self.cfg.save()
        return picks

    def ev_pick(self, dt):
        if self.once("a"):
            self.ev_films = self.pick_films()
            self.wwx.set_pose("laugh", False)
            self.say_as(self.wwx, f"Хочу «{self.ev_films[0][:-7]}»! Там дерутся красиво.")
        if self.ev_t > 3.5 and self.once("b"):
            self.hc_say(f"«{self.ev_films[1][:-7]}». {{Addr}} оценит.")
        if self.ev_t > 7 and self.once("c"):
            self.wwx.set_pose("idle")
            self.say_as(self.wwx, f"И «{self.ev_films[2][:-7]}» — на случай, если вино не кончится!")
        if self.ev_t > 10 and self.once("d"):
            import agent
            for f in self.ev_films:
                agent.open_url("https://www.google.com/search?q=" + quote(self.cfg["film_query"].format(title=f)))
            text = "🎬 Наш топ-3 на сегодня:\n\n" + "\n".join(f"{i + 1}. {f}" for i, f in enumerate(self.ev_films)) + \
                   "\n\nВкладки уже открыты. Ждём тебя!"

            def answer(k):
                if k == "go" and self.ev:
                    self.ev_calm = True
                    self.hc_say("Приятного просмотра, {addr}. Мы посидим тихо. Почти.")
            self.card(text, [("Позже", "later"), ("Иду смотреть", "go")], answer)
            self.tray.showMessage("Хуа Чен и Вэй Усянь", "Топ-3 фильмов выбран, вкладки открыты", self.icon, 8000)
            self.cfg["films_last"] = self.ev_films
            QTimer.singleShot(3000, self.remember_film_tabs)
            self.fresh_banter()
            self.ev_next = 4.0
            self.ev_phase("wait")

    # ── реплики без повторов ──
    def line(self, pool):
        d = self.ev_decks.setdefault(pool, [])
        if not d:
            d.extend(random.sample(POOLS[pool], len(POOLS[pool])))
        return d.pop()

    def pair(self, pool, delay=2.6):
        """Вэй Усянь говорит, Хуа Чен отвечает."""
        a, b = self.line(pool)
        self.say_as(self.wwx, a)
        self.hc_say(b)

    def fresh_banter(self):
        """Если есть модель — просит сочинить несколько свежих перебранок на этот вечер."""
        prompt = ("Придумай 6 коротких шутливых перебранок между Вэй Усянем (весёлый, дразнится, любит вино) и Хуа Ченом "
                  "(спокойный, насмешливый, удачливый). Они пьют вино и ждут, когда хозяйка придёт смотреть фильм. "
                  "Каждая реплика — до 12 слов, без имён в начале. Верни ТОЛЬКО JSON: [[\"реплика Вэй Усяня\", \"ответ Хуа Чена\"], …]")

        def got(text):
            import json
            import re
            m = re.search(r"\[\s*\[.*\]\s*\]", text or "", re.S)
            try:
                pairs = [(str(p[0]), str(p[1])) for p in json.loads(m.group(0)) if len(p) >= 2] if m else []
            except (ValueError, TypeError):
                pairs = []
            good = [p for p in pairs if 3 < len(p[0]) < 110 and 1 < len(p[1]) < 110 and "{" not in p[0] + p[1]]
            self.ev_decks.setdefault("argue", []).extend(good[:6])
        try:
            self.agent.one_shot(prompt, got, system="Ты пишешь короткие смешные диалоги на русском. Отвечай только JSON.")
        except Exception:  # noqa: BLE001
            pass

    def stage(self, act, key, t):
        """True один раз, когда занятие дошло до момента t."""
        if act["t"] >= t and key not in act["done"]:
            act["done"].add(key)
            return True
        return False

    def wwx_pos(self):
        return QPointF(self.wwx.x, self.floor_y() - self.cfg["size"] * 0.5)

    def hc_pos(self):
        return self.hua.center()

    def hc_run(self, x, speed=2.0):
        a = self.avail
        h = self.hua
        h.speed_mul = speed
        h.target_x = max(a.left() + 80, min(a.right() - 80, x))
        h.enter("walk")

    def hit_hc(self):
        h = self.hua
        h.pop = 1.0
        c = self.hc_pos()
        self.add_dust(h.fx, self.floor_y())
        self.swarm.burst(c.x(), c.y(), n=3, radius=70)
        if random.random() < 0.55:
            self.hc_say(self.line("hit_h"), opt=True)

    def hit_wwx(self):
        w = self.wwx
        w.set_pose("scared", False)
        w.hop = 16
        w.fx("smoke")
        self.add_dust(w.x, self.floor_y())
        if random.random() < 0.55:
            self.say_as(w, self.line("hit_w"), opt=True)

    def hc_attack(self):
        self.hc_pose("swing")
        t = self.wwx_pos()
        if random.random() < 0.6:                          # рой бабочек
            hnd = self.hua.anchor("hand")
            for _ in range(8):
                b = self.swarm.spawn_temp(hnd.x(), hnd.y(), goal=(t.x() + random.uniform(-25, 25), t.y() + random.uniform(-40, 30)),
                                          delay=random.uniform(0, 0.25), then="fade", maxs=random.uniform(520, 680))
                b.life = 1.2
        else:                                              # росчерк Э-Мина
            QTimer.singleShot(450, lambda: self.add_slash(t.x(), t.y(), random.uniform(-40, 40), self.cfg["size"] * 0.55))

    def wwx_attack(self):
        w = self.wwx
        w.set_pose("angry", True)
        w.hop = 8
        c = self.hc_pos()
        w.fx(random.choice(("talisman", "crows", "talisman")), x=c.x(), y=c.y())

    def ev_wait(self, dt):
        """Пока хозяйка не пришла — пьют, носятся и перекидываются приёмами. После «Иду смотреть» сидят тихо."""
        if self.ev_t > 5 * 3600:
            self.end_evening()
            return
        if self.lz_state in ("said",):                       # пока Лань Чжань говорит — притихли
            return
        act = self.ev_act
        if act:
            act["t"] += dt
            if getattr(self, "act_" + act["kind"])(act):
                self.act_end()
            return
        if self.ev_t < self.ev_next or self.sq or self.speaking():
            return
        if self.ev_calm:
            kind = random.choice(("drink", "drink", "whisper"))
        else:
            kinds = [k for k in ("drink", "duel", "duel", "chase", "chase", "leap", "flute", "dice", "argue", "argue", "prank")
                     if k != self.ev_last_kind]
            kind = random.choice(kinds)
        self.ev_last_kind = kind
        self.ev_act = {"kind": kind, "t": 0.0, "done": set()}

    def act_end(self):
        w = self.wwx
        self.ev_act, self.ev_free = None, False
        w.hop, w.speed = 0, 1.0
        if self.hua.state != "walk":
            self.hc_pose("idle")
        w.set_pose("idle", False)
        self.ev_next = self.ev_t + (random.uniform(30, 60) if self.ev_calm else random.uniform(3, 8))

    def act_drink(self, act):
        if self.stage(act, "a", 0):
            self.hc_pose("drink")
            self.wwx.set_pose("drink", True)
            if not self.ev_calm and random.random() < 0.7:
                self.pair("drink")
        return act["t"] > 5.5

    def act_whisper(self, act):
        if self.stage(act, "a", 0):
            self.pair("calm")
        return act["t"] > 5

    def act_argue(self, act):
        if self.stage(act, "a", 0):
            self.wwx.set_pose("laugh", False)
            self.pair("argue")
        if self.stage(act, "b", 2.6):
            self.hua.pop = 1.0
        return act["t"] > 6

    def act_flute(self, act):
        if self.stage(act, "a", 0):
            self.wwx.set_pose("flute", True)
            self.wwx.fx("notes", dur=5.5)
            self.pair("flute", delay=3.0)
        return act["t"] > 6.5

    def act_dice(self, act):
        if self.stage(act, "a", 0):
            self.hc_pose("dice")
            hand = self.hua.anchor("hand")
            self.effects.append(DiceRoll(self, hand.x(), hand.y(), [6, 6], lambda: None))
        if self.stage(act, "b", 3.2):
            self.wwx.set_pose("angry", True)
            self.hc_pose("idle")
            self.pair("dice")
        return act["t"] > 8

    def act_prank(self, act):
        w = self.wwx
        if self.stage(act, "a", 0):
            w.set_pose("laugh", False)
            hd = self.hua.head()
            w.fx("talisman", x=hd.x(), y=hd.y() + 28, stick=2.6)
            self.pair("prank", delay=2.2)
        if self.stage(act, "b", 0.7):
            self.hua.pop = 1.0
        if self.stage(act, "c", 4.0):
            self.hc_attack()
        if self.stage(act, "d", 4.8):
            self.hit_wwx()
        return act["t"] > 6.8

    def act_leap(self, act):
        w, h = self.wwx, self.hua
        if self.stage(act, "a", 0):
            self.ev_free = True
            w.set_pose("laugh", False)
            act["back"] = w.x
            side = -1 if w.x > h.fx else 1
            x = h.fx + side * self.gap()
            if not self.avail.left() + 70 < x < self.avail.right() - 70:
                x = h.fx + side * self.cfg["size"] * 0.8     # у края экрана прыгает поближе
            w.jump_to(max(self.avail.left() + 40, min(self.avail.right() - 40, x)), self.cfg["size"] * 1.25, 1.0)
            self.pair("leap", delay=1.3)
        if self.stage(act, "b", 2.8):
            w.jump_to(act["back"], self.cfg["size"] * 1.25, 1.0)
        return act["t"] > 4.2

    def act_chase(self, act):
        """Вэй Усянь удирает, Хуа Чен бежит ЗА ним. Разворачиваясь, беглец перепрыгивает через преследователя."""
        w, h, a = self.wwx, self.hua, self.avail
        g = self.gap()
        if self.stage(act, "a", 0):
            self.ev_free = True
            self.pair("chase")
            lo, hi = a.left() + 90, a.right() - 90
            act["legs"] = [hi, lo] if w.x > h.fx else [lo, hi]             # сначала — прочь от Хуа Чена
            act["leg"] = -1
        if w.arrived() and act["t"] > 0.2:
            act["leg"] += 1
            if act["leg"] == len(act["legs"]):               # добежал: Хуа Чен останавливается на расстоянии разговора
                side = 1 if h.fx > w.x else -1
                self.hc_run(w.x + side * g, 1.2)
            if act["leg"] >= len(act["legs"]):
                return h.state != "walk"
            w.speed = 2.4
            w.walk_to(act["legs"][act["leg"]])
            self.add_dust(w.x, self.floor_y())
        if act["leg"] < 0 or act["leg"] >= len(act["legs"]) or w.target_x is None or w.jump:
            return act["t"] > 30
        d = 1 if w.target_x > w.x else -1                    # куда бежит Вэй Усянь
        if (w.x - h.fx) * d > 0:                             # Хуа Чен позади — догоняет
            x = max(a.left() + 80, min(a.right() - 80, w.x - d * g * 0.6))
            if abs(x - h.fx) > 12:
                h.speed_mul, h.target_x = 1.9, x
                if h.state != "walk":
                    h.enter("walk")
        elif h.state == "walk":                              # беглец несётся навстречу — Хуа Чен ждёт, тот перепрыгнет
            h.target_x = h.fx
        return act["t"] > 30

    def act_duel(self, act):
        w, h, a = self.wwx, self.hua, self.avail
        g = self.gap()
        if self.stage(act, "a", 0):
            self.ev_free = True
            self.pair("duel_start", delay=2.0)
            hx = max(a.left() + 90, min(h.fx, a.right() - 90 - 2 * g))
            if hx < h.fx - 5:
                self.hc_run(hx, 1.6)
            w.speed = 1.8
            w.walk_to(hx + 2 * g)
            act["v"], act["vt"] = 0, None
        if act["vt"] is None:
            if act["t"] > 3.2 and w.arrived() and h.state != "walk":
                act["vt"] = act["t"]
            return act["t"] > 20
        t = act["t"] - act["vt"]
        v = int(t // 2.3)
        if v < 4:
            if v >= act["v"]:
                act["v"] = v + 1
                act["hit"] = False
                w.hop = 0
                if v % 2 == 0:
                    self.hc_pose("idle")
                    self.wwx_attack()
                else:
                    w.set_pose("idle", True)
                    self.hc_attack()
            if not act.get("hit") and t - v * 2.3 > 0.85:
                act["hit"] = True
                if v % 2 == 0:
                    self.hit_hc()
                else:
                    self.hit_wwx()
            return False
        if self.stage(act, "end", act["vt"] + 9.2):
            w.hop = 0
            w.set_pose("laugh", False)
            self.hc_pose("idle")
            self.pair("duel_end", delay=2.0)
            w.speed = 1.4
            w.walk_to(h.fx + g)
        return t > 9.2 + 3.2 and w.arrived()

    def ev_guest(self, dt):
        """Вэй Усянь просто стоит рядом (его привели ради Лань Чжаня)."""

    # ── Лань Чжань: приходит по расписанию, зовёт один раз и уходит; на 11-й раз уводит ──
    def check_lan(self):
        now = datetime.datetime.now()
        start, step = int(self.cfg["lan_start_hour"]), max(1, int(self.cfg["lan_interval_h"]))
        if (not self.cfg.get("lan_enabled") or not ipc.installed("lz") or self.hidden or self.focus_active() or self.lz_state
                or now.hour < start or (now.hour - start) % step or self.ev in ("lan_take", "leave")):
            return
        slot = now.strftime("%Y-%m-%d-%H")
        if self.cfg.get("lan_last_slot") == slot:
            return
        self.cfg["lan_last_slot"] = slot
        self.lan_visit()

    def lan_visit(self):
        if self.lz_state:
            return
        self.lz_state = "summon"
        self.summon_guest("lz", self.lan_begin)

    def lan_begin(self, z):
        if z is None:                                # Лань Чжань не установлен или не отозвался
            self.lz_state = None
            return
        self.lz = z
        left = self.avail.left() + z.W / 2
        if self.hua.fx - self.gap() < left and self.hua.state in ("idle", "scene"):   # место слева для гостя
            self.hua.target_x = left + self.gap()
            if self.hua.state == "idle":
                self.hua.enter("walk")
        z.x, z.opacity, z.fade = left, 0.0, 1
        z.show()
        take = int(self.cfg.get("lan_calls", 0)) >= int(self.cfg["lan_calls_needed"])
        with_wwx = ipc.installed("wwx") or bool(self.ev)
        if take and with_wwx and self.ev is None:    # Вэй Усяня нет рядом — он выходит на зов
            self.start_evening(quiet=True)
        z.walk_to(max(left, self.hua.fx - self.gap()))
        self.lz_state, self.lz_t = ("take_in" if take and with_wwx else "solo" if take else "in"), 0.0

    def wwx_here(self):
        return bool(self.ev and self.wwx and self.wwx.isVisible() and self.wwx.arrived())

    def lan_tick(self, dt):
        z = self.lz
        if not self.lz_state or self.lz_state == "summon":
            return
        self.lz_t += dt
        if self.lz_state == "in" and z.arrived():
            n = int(self.cfg.get("lan_calls", 0))
            self.cfg["lan_calls"] = n + 1
            self.cfg.save()
            z.set_pose("call", False)
            total = int(self.cfg["lan_calls_needed"])
            alone = not ipc.installed("wwx") and not self.ev     # Вэй Усяня нет — зовёт учиться хозяйку
            line = LZ_USER[n % len(LZ_USER)] if alone else LZ_CALLS[n % len(LZ_CALLS)]
            self.say_as(z, f"{line}  ({n + 1}/{total})")
            if alone:
                QTimer.singleShot(2200, lambda: self.hc_say(random.choice(
                    ["Он прав, {addr}. Но решать тебе.", "Ханьгуан-цзюнь строг. Я бы дал тебе ещё час."])))
            elif self.wwx_here():
                QTimer.singleShot(2200, lambda: self.say_as(self.wwx, WWX_REPLY[n % len(WWX_REPLY)]))
                self.ev_act = None
                self.ev_free = False
                self.wwx.hop, self.wwx.speed = 0, 1.0
                self.wwx.target_x = self.wwx.jump = None
                self.wwx.set_pose("scared", False)
                self.hc_pose("idle")
            else:
                QTimer.singleShot(2200, lambda: self.hc_say(random.choice(
                    ["Его здесь нет. Он приходит вечером.", "Вэй Усянь спит. Зайди позже.",
                     "Ты разминулся с ним, Ханьгуан-цзюнь."])))
            self.lz_state, self.lz_t = "said", 0.0
        elif self.lz_state == "solo" and z.arrived():
            self.cfg["lan_calls"] = 0
            self.cfg.save()
            z.set_pose("call", False)
            self.say_as(z, "{Addr}. Довольно отдыха. Учиться.")
            self.study_time(taken=False)
            self.lz_state, self.lz_t = "said", 0.0
        elif self.lz_state == "said" and self.lz_t > 6 and not self.sq and not self.speaking():
            z.walk_to(self.avail.left() - 150)
            QTimer.singleShot(1800, lambda: setattr(z, "fade", -1))
            self.lz_state, self.lz_t = "out", 0.0
        elif self.lz_state == "out" and self.lz_t > 4:
            z.target_x = None
            z.release()
            self.lz_state = None
        elif (self.lz_state == "take_in" and z.arrived() and self.ev and self.ev != "call"
              and self.wwx and self.wwx.arrived()):
            self.cfg["lan_calls"] = 0
            self.cfg.save()
            self.ev_act = None
            self.wwx.hop = 0
            self.lz_state = None
            self.ev_phase("lan_take")

    def ev_lan_take(self, dt):
        """Одиннадцатый раз: Вэй Усянь удирает, Лань Чжань догоняет, гасит всё волной гуциня и уводит за руку."""
        z, w, h = self.lz, self.wwx, self.hua
        edge = self.avail.right() - 110
        if self.once("a"):
            self.ev_free = True
            self.hc_pose("idle")
            self.say_as(z, "Вэй Ин. Довольно.")
            w.speed, z.speed = 2.3, 1.0
            w.set_pose("scared", False)
            w.walk_to(edge)
            QTimer.singleShot(900, lambda: self.say_as(w, "Не пойду! Хуа Чен, задержи его!"))
            QTimer.singleShot(2600, lambda: self.hc_say("Это ваши семейные дела. Я не вмешиваюсь."))
        if self.ev_t > 1.6 and self.once("a2"):
            z.speed = 2.9
            z.walk_to(edge - self.gap() * 0.6)
        if self.ev_t < 1.7 or not (z.arrived() and w.arrived()):
            return
        if self.once("b"):
            self.take_t = self.ev_t
            z.fx("wave")
            z.set_pose("reach", False)
            w.set_pose("angry", True)
            self.say_as(z, "Идём. Учиться.")
            QTimer.singleShot(1500, lambda: self.say_as(w, "Лань Чжань! Мой кувшин!.."))
            self.study_time()
        if self.ev_t - self.take_t > 4.5 and self.once("c"):
            out = self.avail.right() + 200
            z.speed = w.speed = 1.2
            z.walk_to(out)
            w.walk_to(out + self.gap() * 0.6)
            QTimer.singleShot(2500, lambda: [setattr(b, "fade", -1) for b in (z, w)])
            self.ev_phase("leave")

    def ev_leave(self, dt):
        if self.once("a"):
            self.hc_pose("idle")
            self.hc_say("…Его увели. {Addr}, тебе тоже пора учиться. Я прослежу.")
        if self.ev_t > 5:
            self.end_evening(quiet=True)

    def film_tabs(self, tabs):
        from urllib.parse import unquote_plus
        titles = [f[:-7].lower() for f in self.cfg.get("films_last", [])]
        out = []
        for t in tabs:
            url = unquote_plus(t.get("url") or "").lower()
            name = (t.get("title") or "").lower()
            if t.get("id") in self.film_tab_ids or any(x in url or x in name for x in titles):
                out.append(t)
        return out

    def remember_film_tabs(self):
        def got(resp):
            if resp:
                self.film_tab_ids = [t["id"] for t in self.film_tabs(resp.get("tabs", []))]
        self.bridge.request("list", {}, got)

    def study_time(self, taken=True):
        """Закрыть три вкладки с фильмами (остальные — только с подтверждением),
        открыть учёбу в Firefox, включить будильник."""
        from tools_pc import open_in_firefox, play_alarm, stop_alarm

        def got(resp):
            if resp:
                tabs = resp.get("tabs", [])
                films = self.film_tabs(tabs)
                fid = {t["id"] for t in films}
                others = [t for t in tabs if t["id"] not in fid and not t.get("pinned")]
                if films:
                    self.bridge.request("close", {"ids": list(fid)}, lambda r: None)
                self.film_tab_ids = []
                if others:
                    self.confirm(f"Лань Чжань закрыл вкладки с фильмами. Закрыть и остальные вкладки Chrome? Их {len(others)}.",
                                 lambda yes: yes and self.bridge.request(
                                     "close", {"ids": [t["id"] for t in others]}, lambda r: None))
            QTimer.singleShot(600, lambda: open_in_firefox(self.cfg.get("study_urls") or []))
        self.bridge.request("list", {}, got)
        play_alarm(self.data_dir())
        self.card(("⏰ Лань Чжань увёл Вэй Усяня учиться. Твоя очередь, " if taken else
                   "⏰ Лань Чжань зовёт учиться, ") + self.cfg["address"] + ".",
                  [("Иду учиться", "ok")], lambda k: stop_alarm())
        QTimer.singleShot(3 * 60 * 1000, stop_alarm)
