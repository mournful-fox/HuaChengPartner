"""Чиби Хуа Чен: позы из assets/*.png + процедурная анимация (дыхание, прыжки, сплющивание).

Позы: idle — стоит, на палец садится бабочка; walk — идёт; dice — бросает кости;
umbrella — под красным зонтом во время кровавого дождя; sleep — дремлет;
pet — радуется, когда гладят; scold — отчитывает Э-Мина.
"""
import json
import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QCursor, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

POSES = ["idle", "walk", "dice", "umbrella", "sleep", "pet", "scold", "drink", "swing"]
PAD = 22
PAD_B = 4


class HuaWindow(QWidget):
    def __init__(self, world):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.w = world
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        from characters import me
        self.char = me()
        with open(world.asset("poses.json"), encoding="utf-8") as f:
            known = json.load(f)
        self.orig = {p: QPixmap(world.asset(f + ".png")) for p, f in self.char.poses.items()}
        self.meta = {}
        for p, f in self.char.poses.items():
            w_, h_ = self.orig[p].width(), self.orig[p].height()
            self.meta[p] = known.get(f) or {"head": [w_ / 2, 0], "hip": [w_ * 0.6, h_ * 0.72],
                                            "hand": [w_ * 0.25, h_ * 0.45]}
        self.pose = "idle"
        self.flip = False
        self.load_sprite()

        a = world.avail
        self.fx = a.left() + a.width() * float(world.cfg.get("pos_x", 0.8))
        self.fy = world.floor_y()
        self.hover = 0.0
        self.state = "idle"
        self.state_t = 0.0          # сколько длится текущее состояние
        self.state_dur = 0.0
        self.target_x = None
        self.opacity = 1.0
        self.t = 0.0
        self.next_decision = 6.0
        self.drag = None
        self.drag_vx = 0.0
        self.tp = None
        self.pet_times = []
        self.last_drag_talk = -99
        self.pop = 0.0              # «упругий» отскок при смене позы
        self.sway = 0.0
        self.last_cursor = QCursor.pos()
        self.idle_since = 0.0       # когда последний раз двигалась мышь
        self.zzz_t = 0.0

    # ── спрайты ──
    def load_sprite(self):
        size = int(self.w.cfg["size"])
        self.k = size / self.orig["idle"].height()
        self.pix = {p: self.orig[p].scaled(round(self.orig[p].width() * self.k),
                                           round(self.orig[p].height() * self.k),
                                           Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    for p in self.orig}
        self.sprite_h = size
        mw = max(p.width() for p in self.pix.values())
        mh = max(p.height() for p in self.pix.values())
        self.W = mw + 2 * PAD
        self.H = mh + PAD + PAD_B
        self.resize(self.W, self.H)
        self.samples = {}
        for p, pm in self.pix.items():
            img = pm.toImage()
            step = max(3, pm.height() // 45)
            self.samples[p] = [(x, y) for y in range(0, img.height(), step)
                               for x in range(0, img.width(), step) if img.pixelColor(x, y).alpha() > 200]

    def cur(self):
        return self.pix[self.pose]

    def set_pose(self, pose):
        if pose not in self.pix:
            pose = "idle"
        if pose != self.pose:
            self.pose = pose
            self.pop = 1.0

    def lift(self):
        """Вертикальное смещение от прыжков/парения."""
        if self.state == "walk":
            return abs(math.sin(self.t * 7)) * 7 * self.k * 2.4
        return self.hover

    def sprite_origin(self):
        pm = self.cur()
        return QPointF(self.fx - pm.width() / 2, self.fy - self.lift() - pm.height())

    def anchor(self, name):
        pm = self.cur()
        o = self.sprite_origin()
        ax, ay = self.meta[self.pose][name]
        x = ax * self.k
        if self.flip:
            x = pm.width() - x
        return QPointF(o.x() + x, o.y() + ay * self.k)

    def center(self):
        o = self.sprite_origin()
        pm = self.cur()
        return QPointF(o.x() + pm.width() * 0.5, o.y() + pm.height() * 0.45)

    def head(self):
        p = self.anchor("head")
        return QPointF(p.x(), p.y() - 2)

    def visible_now(self):
        return self.isVisible() and self.opacity > 0.3

    # ── состояния ──
    def enter(self, state, dur=0.0, pose=None):
        self.state = state
        self.state_t = 0.0
        self.state_dur = dur
        self.set_pose(pose or dict(self.char.state_pose, walk="walk").get(state, "idle"))
        if state != "walk":
            self.flip = False

    def busy(self):
        return self.state in ("teleport", "drag", "dice", "rain", "pet", "scold", "scene")

    def step(self, dt):
        self.t += dt
        self.state_t += dt
        self.pop = max(0.0, self.pop - dt * 5)
        r = self.w.remote
        if r:                                   # нами управляет хозяин сцены (другой процесс)
            self.state = "scene"
            self.set_pose(r.get("pose", "idle"))
            self.flip, self.opacity = bool(r.get("flip")), float(r.get("op", 1))
            self.fx, self.fy, self.hover = float(r.get("x", self.fx)), self.w.floor_y(), float(r.get("lift", 0))
            self.move(int(self.fx - self.W / 2), int(self.fy - self.hover - self.H + PAD_B))
            self.update()
            return
        a = self.w.avail
        floor = self.w.floor_y()

        # следим, двигается ли мышь (для дремоты)
        c = QCursor.pos()
        if (c - self.last_cursor).manhattanLength() > 3:
            self.last_cursor = c
            self.idle_since = self.w.now
            if self.state == "sleep":
                d = math.hypot(c.x() - self.fx, c.y() - (self.fy - self.sprite_h / 2))
                if d < self.sprite_h * 1.2 or self.state_t > 20:
                    self.wake()

        if self.state == "idle":
            self.hover += (0 - self.hover) * min(1, dt * 3)
            if self.t > self.next_decision and not self.w.focus_active():
                self.decide()
        elif self.state == "walk":
            sp = 70 * self.k * 2.4 * getattr(self, "speed_mul", 1.0)
            d = self.target_x - self.fx
            self.flip = d < 0
            if abs(d) < 3:
                self.speed_mul = 1.0
                self.enter("idle")
                self.next_decision = self.t + random.uniform(6, 15)
            else:
                self.fx += math.copysign(min(abs(d), sp * dt), d)
                # пыль из-под ног на каждом «приземлении»
                if abs(math.sin(self.t * 7)) < 0.12 and random.random() < 0.5:
                    self.w.add_dust(self.fx - math.copysign(self.cur().width() * 0.25, d), floor)
        elif self.state == "fall":
            self.fy += (floor - self.fy) * min(1, dt * 2.2) + 30 * dt
            if self.fy >= floor:
                self.fy = floor
                self.enter("idle")
                self.next_decision = self.t + random.uniform(5, 10)
        elif self.state == "sleep":
            self.zzz_t -= dt
            if self.zzz_t <= 0:
                self.zzz_t = 1.6
                h = self.anchor("head")
                self.w.add_zzz(h.x() - self.cur().width() * 0.2, h.y() + 10)
        elif self.state == "teleport":
            self.step_teleport(dt)
        elif self.state in ("dice", "pet", "scold"):
            if self.state_t > self.state_dur:
                self.enter("idle")
                self.next_decision = self.t + random.uniform(5, 10)
        elif self.state == "rain":
            if not self.w.raining():
                self.enter("idle")

        half = self.cur().width() / 2
        self.fx = max(a.left() + half, min(a.right() - half, self.fx))
        self.fy = min(self.fy, floor)

        target_sway = 0.0
        if self.state == "walk":
            target_sway = math.sin(self.t * 7) * 3
        elif self.state == "drag":
            target_sway = max(-14, min(14, -self.drag_vx * 0.02))
        self.sway += (target_sway - self.sway) * min(1, dt * 10)

        # окно ставим так, чтобы низ позы был на «полу», а по центру — fx
        self.move(int(self.fx - self.W / 2), int(self.fy - self.lift() - self.H + PAD_B))
        self.update()

    def decide(self):
        w = self.w
        if w.extra and w.extra.decide(self):     # у персонажа свои занятия
            return
        cfg = w.cfg
        a = w.avail
        half = self.cur().width() / 2
        # давно не трогали мышь — задремал
        if w.now - self.idle_since > 240 or (w.is_night() and random.random() < 0.25):
            self.enter("sleep")
            return
        if cfg.get("calm"):
            r = random.random()
            if r < 0.15:
                w.swarm.perch()
            self.next_decision = self.t + random.uniform(10, 20)
            return
        r = random.random()
        if r < 0.30:
            self.next_decision = self.t + random.uniform(8, 18)
            if random.random() < 0.5:
                w.swarm.perch()      # бабочка садится на палец
        elif r < 0.70:
            x = self.fx
            for _ in range(10):
                x = random.uniform(a.left() + half, a.right() - half)
                if abs(x - self.fx) > 150:
                    break
            self.target_x = x
            self.enter("walk")
        elif r < 0.76:
            if self.char.teleport:
                self.teleport()
            else:
                self.next_decision = self.t + random.uniform(6, 12)
        elif r < 0.84 and self.char.eming and cfg["eming_auto"] and w.eming.state == "sheathed":
            w.eming.release()
            self.next_decision = self.t + 10
        elif r < 0.90:
            if self.char.id == "hua":           # кости — забава только Хуа Чена
                w.roll_dice(False, quiet=True)
            else:
                self.next_decision = self.t + random.uniform(6, 12)
        else:
            w.swarm.release(15)
            self.next_decision = self.t + 12

    def wake(self):
        self.enter("idle")
        self.pop = 1.0
        self.idle_since = self.w.now
        self.next_decision = self.t + random.uniform(4, 8)
        if random.random() < 0.5:
            self.w.talk("wake")

    def sleep(self):
        self.enter("sleep")

    # ── телепорт: рассыпается на бабочек и собирается в другом месте ──
    def teleport(self, dest_x=None):
        if self.state == "teleport":
            return
        a = self.w.avail
        if self.state != "idle":
            self.enter("idle")
        half = self.cur().width() / 2
        if dest_x is None:
            for _ in range(10):
                dest_x = random.uniform(a.left() + half, a.right() - half)
                if abs(dest_x - self.fx) > 300:
                    break
        dest_x = max(a.left() + half, min(a.right() - half, dest_x))
        self.state = "teleport"
        self.tp = {"t": 0.0, "dest": dest_x, "moved": False}
        self.w.cfg["teleports"] += 1
        o = self.sprite_origin()
        pm = self.cur()
        dest_o = QPointF(dest_x - pm.width() / 2, self.w.floor_y() - pm.height())
        samples = self.samples[self.pose]
        for sx, sy in random.sample(samples, min(36 if self.char.butterflies else 14, len(samples))):
            gx, gy = random.choice(samples)
            self.w.swarm.spawn_temp(o.x() + sx, o.y() + sy, goal=(dest_o.x() + gx, dest_o.y() + gy),
                                    delay=random.uniform(0.05, 0.6), then="fade",
                                    maxs=random.uniform(380, 520))

    def step_teleport(self, dt):
        tp = self.tp
        tp["t"] += dt
        t = tp["t"]
        if t < 0.7:
            self.opacity = 1 - t / 0.7
        elif t < 1.6:
            self.opacity = 0
            if not tp["moved"]:
                tp["moved"] = True
                self.fx = tp["dest"]
                self.fy = self.w.floor_y()
                self.hover = 0
        elif t < 2.3:
            self.opacity = (t - 1.6) / 0.7
        else:
            self.opacity = 1
            self.enter("idle")
            self.pop = 1.0
            self.next_decision = self.t + random.uniform(6, 12)
            if random.random() < 0.5:
                self.w.talk("teleport")

    def summon(self):
        self.show()
        self.teleport(QCursor.pos().x())

    # ── мышь ──
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.state != "teleport":
            g = e.globalPosition()
            self.drag = {"start": g, "dx": self.fx - g.x(), "dy": self.fy - g.y(),
                         "moved": False, "lastx": g.x()}

    def mouseMoveEvent(self, e):
        if not self.drag:
            return
        g = e.globalPosition()
        d = self.drag
        if not d["moved"] and (g - d["start"]).manhattanLength() > 6:
            d["moved"] = True
            self.enter("drag", pose="idle")
            self.hover = 0
            if self.t - self.last_drag_talk > 25:
                self.last_drag_talk = self.t
                self.w.talk("drag")
        if d["moved"]:
            self.drag_vx = (g.x() - d["lastx"]) * 30
            d["lastx"] = g.x()
            self.fx = g.x() + d["dx"]
            self.fy = g.y() + d["dy"]

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or not self.drag:
            return
        moved = self.drag["moved"]
        self.drag = None
        self.drag_vx = 0
        if moved:
            self.enter("fall" if self.fy < self.w.floor_y() - 2 else "idle")
            self.w.cfg["pos_x"] = (self.fx - self.w.avail.left()) / max(1, self.w.avail.width())
            if random.random() < 0.3:
                self.w.talk("drop")
        else:
            self.pet()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.w.open_chat()

    def contextMenuEvent(self, e):
        self.w.show_menu(e.globalPos())

    def pet(self):
        w = self.w
        if self.state == "sleep":
            self.wake()
            return
        if self.busy() and self.state != "pet":
            return
        w.cfg["pets"] += 1
        w.reward("pet")
        now = w.now
        self.pet_times = [t for t in self.pet_times if now - t < 60] + [now]
        self.enter("pet", dur=1.8)
        h = self.anchor("head")
        if w.extra and hasattr(w.extra, "on_pet") and w.extra.on_pet(len(self.pet_times)):
            return
        w.add_hearts(h.x(), h.y() + self.cur().height() * 0.2)
        if self.char.eming and len(self.pet_times) >= 5 and w.eming.state == "sheathed":
            self.pet_times.clear()
            w.eming.release(jealous=True)
            return
        if random.random() < 0.6:
            w.talk("pet")

    # ── отрисовка ──
    def paintEvent(self, e):
        pm = self.cur()
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setOpacity(self.opacity)
        sx = sy = 1.0
        if self.state in ("idle", "fall", "drag"):
            b = math.sin(self.t * 1.8)
            sx, sy = 1 - b * 0.006, 1 + b * 0.012          # дыхание
        elif self.state == "sleep":
            b = math.sin(self.t * 1.1)
            sx, sy = 1 + b * 0.012, 1 + b * 0.022          # глубокое сонное дыхание
        elif self.state == "walk":
            ph = abs(math.sin(self.t * 7))
            sy = 0.94 + 0.08 * ph                          # сплющивается при приземлении
            sx = 1.04 - 0.05 * ph
        elif self.state == "pet":
            sq = math.exp(-self.state_t * 3) * math.sin(self.state_t * 18)
            sx, sy = 1 + sq * 0.07, 1 - sq * 0.09          # «желейный» отклик
        elif self.state == "dice":
            sy = 1 + math.exp(-self.state_t * 5) * 0.05
        if self.pop > 0:                                   # упругая смена позы
            k = math.sin(self.pop * math.pi) * 0.08
            sx, sy = sx * (1 + k), sy * (1 - k)
        shake = 0.0
        if self.state == "scold" and self.state_t < 0.6:
            shake = math.sin(self.state_t * 60) * 2.5
        p.translate(self.W / 2 + shake, self.H - PAD_B)
        p.rotate(self.sway)
        p.scale(-sx if self.flip else sx, sy)
        p.drawPixmap(int(-pm.width() / 2), -pm.height(), pm)
        p.end()
