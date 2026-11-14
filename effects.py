"""Всё, что рисуется поверх экрана: серебряные бабочки, взмах ятагана, кости,
кровавый дождь, красная нить и облачка с репликами.
Слой «прозрачен» для мыши — клики проходят насквозь."""
import math
import random

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QLinearGradient,
                           QPainter, QPainterPath, QPen, QRadialGradient, QRegion)
from PySide6.QtWidgets import QWidget


def clamp(v, a, b):
    return a if v < a else b if v > b else v


# ───────────────────────── бабочки ─────────────────────────

class ButterflySprite:
    """Светящаяся бабочка из assets/butterfly.png. Смотрит вправо, тело — в точке body."""

    def __init__(self, path, body):
        from PySide6.QtGui import QPixmap
        self.src = QPixmap(path)
        self.body = body
        self.cache = {}

    def get(self, h, red=False):
        h = max(8, int(h))
        key = (h, red)
        if key not in self.cache:
            pm = self.src.scaledToHeight(h, Qt.SmoothTransformation)
            if red:                          # алый оттенок поверх свечения (украшение из лавки)
                from PySide6.QtGui import QPainter as _P
                pm = pm.copy()
                p = _P(pm)
                p.setCompositionMode(_P.CompositionMode_SourceAtop)
                p.fillRect(pm.rect(), QColor(220, 30, 50, 150))
                p.end()
            self.cache[key] = pm
        return self.cache[key]

    def draw(self, p, x, y, tilt_deg, flap, height, alpha, face_left=False, red=False):
        pm = self.get(height, red)
        bx, by = self.body[0] * pm.width(), self.body[1] * pm.height()
        p.save()
        p.translate(x, y)
        p.rotate(tilt_deg)
        # взмах: крылья «складываются» к телу по горизонтали и чуть приподнимаются
        fx = 0.35 + 0.65 * flap
        p.scale(-fx if face_left else fx, 0.92 + 0.08 * flap)
        p.setOpacity(alpha)
        p.drawPixmap(QPointF(-bx, -by), pm)
        p.restore()


SPRITE = None


def draw_butterfly(p, x, y, tilt_deg, flap, size, alpha, face_left=False, red=False):
    SPRITE.draw(p, x, y, tilt_deg, flap, size * 3.8, alpha, face_left, red)


class Butterfly:
    def __init__(self, x, y, mode="orbit", temp=False):
        self.x, self.y = x, y
        self.vx, self.vy = random.uniform(-60, 60), random.uniform(-60, 60)
        self.mode = mode
        self.temp = temp            # временная (из облака при телепорте и т.п.)
        self.life = 1.0             # для исчезающих
        self.fading = False
        self.alpha = 0.0 if temp else 0.0
        self.phase = random.uniform(0, math.tau)
        self.freq = random.uniform(9, 13)
        self.size = random.uniform(8, 12)
        self.ang = random.uniform(0, math.tau)
        self.orb_speed = random.uniform(0.35, 0.8) * random.choice((-1, 1))
        self.orb_rx = random.uniform(0.35, 0.65)
        self.orb_ry = random.uniform(0.25, 0.45)
        self.maxs = random.uniform(170, 260)
        self.goal = None            # (x, y) для режима go
        self.delay = 0.0
        self.then = None            # что делать по прибытии: "fade" / режим
        self.wander_t = 0.0
        self.t = random.uniform(0, 10)
        self.perch_t = 0.0
        self.landed = False
        self.dust_t = random.uniform(0, 0.2)

    def bounds(self):
        r = self.size * 4
        return QRect(int(self.x - r), int(self.y - r), int(2 * r), int(2 * r))


class Swarm:
    def __init__(self, world):
        self.w = world
        self.items = []
        self.release_until = 0.0
        self.dust = []          # искристая пыльца: [x, y, vx, vy, life, size]
        self.rebuild()

    def rebuild(self):
        self.items = [b for b in self.items if b.temp]
        c = self.w.hua.center() if self.w.hua else QPointF(500, 500)
        for i in range(int(self.w.cfg["butterflies"])):
            b = Butterfly(c.x() + random.uniform(-40, 40), c.y() + random.uniform(-40, 40))
            self.items.append(b)
        self.apply_follow()

    def permanent(self):
        return [b for b in self.items if not b.temp]

    def apply_follow(self):
        perm = self.permanent()
        n_follow = max(1, len(perm) // 4) if self.w.cfg["follow_cursor"] else 0
        for i, b in enumerate(perm):
            if b.mode in ("orbit", "follow"):
                b.mode = "follow" if i < n_follow else "orbit"

    def perch(self):
        """Одна бабочка садится Хуа Чену на палец (или на макушку, если он спит)."""
        free = [b for b in self.permanent() if b.mode == "orbit"]
        if free:
            b = random.choice(free)
            b.mode, b.perch_t, b.landed = "perch", random.uniform(6, 12), False

    def release(self, seconds=20):
        for b in self.permanent():
            b.mode = "wander"
            b.wander_t = 0
        self.release_until = self.w.now + seconds

    def recall(self):
        self.release_until = 0
        for b in self.permanent():
            b.mode = "orbit"
        self.apply_follow()

    def spawn_temp(self, x, y, goal=None, delay=0.0, then="fade", maxs=None, mode="go"):
        b = Butterfly(x, y, mode=mode, temp=True)
        b.goal, b.delay, b.then = goal, delay, then
        b.alpha = 0.0
        if maxs:
            b.maxs = maxs
        self.items.append(b)
        return b

    def burst(self, x, y, n=4, radius=60, life=2.5):
        """Несколько бабочек вспархивают из точки, кружат и тают."""
        for _ in range(n):
            a = random.uniform(0, math.tau)
            b = self.spawn_temp(x, y, goal=(x + math.cos(a) * radius, y + math.sin(a) * radius * 0.7 - 40),
                                then="fade", maxs=160)
            b.life = life

    def step(self, dt):
        w = self.w
        now = w.now
        if self.release_until and now > self.release_until:
            self.recall()
        cur = QCursor.pos()
        cx, cy = cur.x(), cur.y()
        hc = w.hua.center()
        scale = w.hua.sprite_h / 300.0
        area = w.avail
        dead = []
        for b in self.items:
            b.t += dt
            if b.delay > 0:
                b.delay -= dt
                b.alpha = min(1.0, b.alpha + dt * 4)
                b.vx *= 0.9
                b.vy *= 0.9
                b.x += b.vx * dt
                b.y += b.vy * dt
                continue
            # цель
            maxs = b.maxs
            if b.mode == "orbit":
                b.ang += b.orb_speed * dt
                rx = 230 * b.orb_rx * scale
                ry = 300 * b.orb_ry * scale
                tx = hc.x() + math.cos(b.ang) * rx
                ty = hc.y() + math.sin(b.ang) * ry + math.sin(b.ang * 2.3 + b.phase) * 15
                if not w.hua.visible_now():
                    tx, ty = hc.x(), hc.y()
            elif b.mode == "follow":
                b.ang += 1.4 * dt
                tx = cx + math.cos(b.ang + b.phase) * 34
                ty = cy - 26 + math.sin(b.ang * 1.3 + b.phase) * 20
                maxs = 420
            elif b.mode == "wander":
                b.wander_t -= dt
                if b.wander_t <= 0 or b.goal is None:
                    b.goal = (random.uniform(area.left() + 40, area.right() - 40),
                              random.uniform(area.top() + 40, area.bottom() - 40))
                    b.wander_t = random.uniform(2.5, 6)
                tx, ty = b.goal
            elif b.mode == "perch":
                h = w.hua.anchor("hand") if w.hua.pose == "idle" else w.hua.anchor("head")
                tx, ty = h.x() + 2, h.y() - b.size * 0.6
                b.perch_t -= dt
                if math.hypot(tx - b.x, ty - b.y) < 6:
                    b.x, b.y, b.vx, b.vy = tx, ty, 0.0, 0.0
                    b.landed = True
                if b.perch_t <= 0 or not w.hua.visible_now() or w.hua.state not in ("idle", "sleep"):
                    b.mode, b.landed = "orbit", False
                if b.landed:
                    continue
                maxs = 160
            elif b.mode == "guard":
                b.ang += 2.0 * dt
                tx = cx + math.cos(b.ang + b.phase) * 55
                ty = cy + math.sin(b.ang + b.phase) * 40
                maxs = 380
            else:  # go
                tx, ty = b.goal if b.goal else (b.x, b.y)
            dx, dy = tx - b.x, ty - b.y
            d = math.hypot(dx, dy) or 1e-3
            if b.mode == "go" and d < 12 and not b.fading:
                if b.then == "fade":
                    b.fading = True
                elif b.then:
                    b.mode = b.then
            sp = maxs * min(1.0, d / 110.0)
            ax = (dx / d * sp - b.vx) * 3.5
            ay = (dy / d * sp - b.vy) * 3.5
            # порхание
            ax += math.sin(b.t * 2.7 + b.phase) * 140
            ay += math.cos(b.t * 2.1 + b.phase * 1.7) * 140
            # шарахаются от курсора (кроме тех, что к нему привязаны)
            if b.mode in ("orbit", "wander"):
                ex, ey = b.x - cx, b.y - cy
                ed = math.hypot(ex, ey)
                if ed < 70:
                    k = (70 - ed) / 70 * 2400
                    ax += ex / (ed or 1) * k
                    ay += ey / (ed or 1) * k
            b.vx += ax * dt
            b.vy += ay * dt
            v = math.hypot(b.vx, b.vy)
            lim = maxs * 1.6
            if v > lim:
                b.vx *= lim / v
                b.vy *= lim / v
            b.x += b.vx * dt
            b.y += b.vy * dt
            if b.fading:
                b.life -= dt * 2.5
                b.alpha = max(0.0, min(b.alpha, b.life))
                if b.life <= 0:
                    dead.append(b)
            else:
                if b.temp:                      # страховка: временные не живут вечно
                    b.life -= dt / 6
                    if b.life <= 0.35:
                        b.fading = True
                b.alpha = min(1.0, b.alpha + dt * 3)
            b.dust_t -= dt
            if b.dust_t <= 0 and b.alpha > 0.3:
                b.dust_t = random.uniform(0.05, 0.14)
                self.dust.append([b.x + random.uniform(-4, 4), b.y + random.uniform(-2, 6),
                                  random.uniform(-12, 12), random.uniform(5, 25), 1.0,
                                  random.uniform(0.8, 1.9)])
        for b in dead:
            self.items.remove(b)
        for d in self.dust:
            d[0] += d[2] * dt
            d[1] += d[3] * dt
            d[4] -= dt * 1.1
        self.dust = [d for d in self.dust if d[4] > 0][-400:]

    def draw(self, p):
        if not getattr(self.w, "char", None) or not self.w.char.butterflies:
            return                                  # бабочки — только у Хуа Чена
        p.setPen(Qt.NoPen)
        gold = self.w.has("gold_dust") if hasattr(self.w, "has") else False
        red_on = self.w.has("red_bf") if hasattr(self.w, "has") else False
        halo = QColor(255, 205, 110) if gold else QColor(180, 205, 255)
        core = QColor(255, 236, 170) if gold else QColor(255, 255, 255)
        for x, y, _, _, life, sz in self.dust:
            a = int(255 * life)
            halo.setAlpha(a // 4)
            core.setAlpha(a)
            p.setBrush(halo)
            p.drawEllipse(QPointF(x, y), sz * 2.2, sz * 2.2)
            p.setBrush(core)
            p.drawEllipse(QPointF(x, y), sz * 0.7, sz * 0.7)
        for b in self.items:
            if b.alpha <= 0.01:
                continue
            if b.landed:   # сидит: медленно складывает и раскрывает крылья
                flap = 0.55 + 0.45 * math.sin(b.t * 2.2)
                draw_butterfly(p, b.x, b.y, -8, flap, b.size, b.alpha, face_left=True)
                continue
            flap = abs(math.sin(b.t * b.freq + b.phase))
            tilt = clamp(b.vy / 10.0, -25, 25) * (-1 if b.vx < 0 else 1)
            bob = math.sin(b.t * b.freq * 0.5 + b.phase) * 2
            red = red_on and (id(b) // 16) % 3 == 0
            draw_butterfly(p, b.x, b.y + bob, tilt, flap, b.size, b.alpha, face_left=b.vx < 0, red=red)

    def bounds(self):
        out = [b.bounds() for b in self.items]
        if self.dust:
            xs = [d[0] for d in self.dust]
            ys = [d[1] for d in self.dust]
            out.append(QRect(int(min(xs)) - 6, int(min(ys)) - 6, int(max(xs) - min(xs)) + 12,
                             int(max(ys) - min(ys)) + 12))
        return out


# ───────────────────────── взмах ятагана ─────────────────────────

class Slash:
    DUR = 0.55

    def __init__(self, x, y, angle_deg, radius=110):
        self.x, self.y, self.a, self.r = x, y, angle_deg, radius
        self.age = 0.0

    def step(self, dt):
        self.age += dt
        return self.age < self.DUR

    def draw(self, p):
        t = self.age
        grow = min(1.0, t / 0.14)
        grow = 1 - (1 - grow) ** 3
        alpha = 1.0 - max(0.0, (t - 0.14) / (self.DUR - 0.14))
        sweep = 170 * grow
        r = self.r
        p.save()
        p.translate(self.x, self.y)
        p.rotate(self.a)
        p.setOpacity(alpha)
        outer = QRectF(-r, -r, 2 * r, 2 * r)
        inner_r = r * 0.78
        off = r * 0.12
        inner = QRectF(-inner_r + off, -inner_r, 2 * inner_r, 2 * inner_r)
        path = QPainterPath()
        start = 95 - sweep / 2
        path.arcMoveTo(outer, start)
        path.arcTo(outer, start, sweep)
        path.arcTo(inner, start + sweep, -sweep)
        path.closeSubpath()
        g = QRadialGradient(0, 0, r)
        g.setColorAt(0.70, QColor(170, 200, 240, 0))
        g.setColorAt(0.86, QColor(215, 230, 250, 200))
        g.setColorAt(1.0, QColor(255, 255, 255, 255))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawPath(path)
        p.setPen(QPen(QColor(255, 255, 255, 230), 2))
        arc = QPainterPath()
        arc.arcMoveTo(outer, start)
        arc.arcTo(outer, start, sweep)
        p.setBrush(Qt.NoBrush)
        p.drawPath(arc)
        # искры
        p.setPen(QPen(QColor(230, 240, 255, 220), 1.4))
        for i in range(5):
            aa = math.radians(start + sweep * (i + 0.5) / 5)
            rr = r * (1.02 + 0.25 * t / self.DUR)
            p.drawLine(QPointF(math.cos(aa) * rr, -math.sin(aa) * rr),
                       QPointF(math.cos(aa) * (rr + 10), -math.sin(aa) * (rr + 10)))
        p.restore()

    def bounds(self):
        r = int(self.r * 1.45)
        return [QRect(int(self.x) - r, int(self.y) - r, 2 * r, 2 * r)]


# ───────────────────────── кости ─────────────────────────

PIPS = {1: [(0, 0)], 2: [(-1, -1), (1, 1)], 3: [(-1, -1), (0, 0), (1, 1)],
        4: [(-1, -1), (1, -1), (-1, 1), (1, 1)], 5: [(-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)],
        6: [(-1, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (1, 1)]}


class Die:
    def __init__(self, x, y, vx, vy, final, floor):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.rot = random.uniform(0, 90)
        self.vr = random.uniform(-720, 720)
        self.final = final
        self.face = random.randint(1, 6)
        self.floor = floor
        self.settled = False
        self.flip_t = 0

    def step(self, dt):
        if self.settled:
            return
        self.vy += 1500 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rot += self.vr * dt
        self.flip_t += dt
        if self.flip_t > 0.07:
            self.flip_t = 0
            self.face = random.randint(1, 6)
        if self.y > self.floor - 13:
            self.y = self.floor - 13
            self.vy *= -0.42
            self.vx *= 0.6
            self.vr *= 0.5
            if abs(self.vy) < 90:
                self.settled = True
                self.face = self.final
                self.rot = round(self.rot / 90) * 90


class DiceRoll:
    """Хуа Чен бросает кости. У китайских костей пипсы на «1» и «4» красные."""

    def __init__(self, world, x, y, faces, on_done):
        floor = world.floor_y()
        self.dice = [Die(x, y, random.uniform(-260, -120) * (1 + i * 0.4), random.uniform(-380, -250),
                         f, floor) for i, f in enumerate(faces)]
        self.on_done = on_done
        self.done_t = None
        self.age = 0

    def step(self, dt):
        self.age += dt
        for d in self.dice:
            d.step(dt)
        if self.done_t is None and all(d.settled for d in self.dice):
            self.done_t = self.age
            self.on_done()
        return not (self.done_t is not None and self.age - self.done_t > 4.0) and self.age < 12

    def draw(self, p):
        alpha = 1.0
        if self.done_t is not None:
            alpha = clamp(1 - (self.age - self.done_t - 3.2) / 0.8, 0, 1)
        for d in self.dice:
            p.save()
            p.translate(d.x, d.y)
            p.rotate(d.rot)
            p.setOpacity(alpha)
            s = 13
            p.setPen(QPen(QColor(90, 70, 60), 1.2))
            g = QLinearGradient(-s, -s, s, s)
            g.setColorAt(0, QColor(255, 252, 240))
            g.setColorAt(1, QColor(225, 215, 195))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(-s, -s, 2 * s, 2 * s), 5, 5)
            p.setPen(Qt.NoPen)
            red = d.face in (1, 4)
            p.setBrush(QColor(200, 20, 35) if red else QColor(30, 25, 25))
            rr = 4.2 if d.face == 1 else 2.6
            for px, py in PIPS[d.face]:
                p.drawEllipse(QPointF(px * 6.5, py * 6.5), rr, rr)
            p.restore()

    def bounds(self):
        return [QRect(int(d.x) - 24, int(d.y) - 24, 48, 48) for d in self.dice]


# ───────────────────────── кровавый дождь ─────────────────────────

class CrimsonRain:
    def __init__(self, world, duration=7.0):
        self.w = world
        self.age = 0.0
        self.dur = duration
        self.drops = []
        self.petals = []

    def step(self, dt):
        self.age += dt
        a = self.w.screen_geo
        if self.age < self.dur:
            for _ in range(int(220 * dt) + 1):
                self.drops.append([random.uniform(a.left() - 100, a.right()), a.top() - 20,
                                   random.uniform(900, 1300), random.uniform(14, 30)])
            if random.random() < dt * 6:
                self.petals.append([random.uniform(a.left(), a.right()), a.top() - 10,
                                    random.uniform(0, math.tau), random.uniform(60, 110)])
        floor = self.w.floor_y()
        for d in self.drops:
            d[1] += d[2] * dt
            d[0] += d[2] * 0.12 * dt
        self.drops = [d for d in self.drops if d[1] < floor]
        for pt in self.petals:
            pt[1] += pt[3] * dt
            pt[2] += dt * 2
            pt[0] += math.sin(pt[2]) * 40 * dt
        self.petals = [pt for pt in self.petals if pt[1] < floor - 4]
        return self.age < self.dur or self.drops or self.petals

    def draw(self, p):
        fade_in = clamp(self.age / 0.8, 0, 1)
        p.setOpacity(fade_in)
        p.setPen(QPen(QColor(190, 15, 35, 170), 1.6, Qt.SolidLine, Qt.RoundCap))
        for x, y, v, ln in self.drops:
            p.drawLine(QPointF(x, y), QPointF(x - ln * 0.12, y - ln))
        p.setPen(Qt.NoPen)
        for x, y, ph, _ in self.petals:
            p.save()
            p.translate(x, y)
            p.rotate(math.degrees(ph))
            p.setBrush(QColor(210, 30, 50, 210))
            p.drawEllipse(QPointF(0, 0), 6, 3.2 + 1.5 * math.sin(ph * 2))
            p.restore()
        p.setOpacity(1)

    def bounds(self):
        return [self.w.screen_geo]


# ───────────────────────── пыль, сердечки, Zzz ─────────────────────────

class Particles:
    """kind: dust — облачко из-под ног, heart — сердечко, zzz — буква z."""

    def __init__(self, kind, x, y):
        self.kind = kind
        self.items = []
        self.age = 0.0
        n = {"dust": 3, "heart": 3, "zzz": 1}[kind]
        for i in range(n):
            if kind == "dust":
                self.items.append([x + random.uniform(-6, 6), y - 4, random.uniform(-40, 40),
                                   random.uniform(-25, -8), random.uniform(4, 7)])
            elif kind == "heart":
                self.items.append([x + random.uniform(-40, 40), y - random.uniform(0, 20),
                                   random.uniform(-15, 15), random.uniform(-70, -45), random.uniform(7, 11)])
            else:
                self.items.append([x, y, -12, -22, 10])
        self.dur = {"dust": 0.6, "heart": 1.6, "zzz": 2.6}[kind]

    def step(self, dt):
        self.age += dt
        for it in self.items:
            it[0] += it[2] * dt
            it[1] += it[3] * dt
            if self.kind == "dust":
                it[4] += dt * 10
            if self.kind == "zzz":
                it[0] += math.sin(self.age * 3) * 10 * dt
                it[4] += dt * 3
        return self.age < self.dur

    def draw(self, p):
        a = clamp(1 - self.age / self.dur, 0, 1)
        for x, y, _, _, s in self.items:
            if self.kind == "dust":
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(235, 222, 200, int(150 * a)))
                p.drawEllipse(QPointF(x, y), s, s * 0.75)
            elif self.kind == "heart":
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(220, 40, 60, int(235 * a)))
                path = QPainterPath()
                path.moveTo(x, y + s * 0.9)
                path.cubicTo(x - s * 1.4, y - s * 0.1, x - s * 0.7, y - s * 1.2, x, y - s * 0.35)
                path.cubicTo(x + s * 0.7, y - s * 1.2, x + s * 1.4, y - s * 0.1, x, y + s * 0.9)
                p.drawPath(path)
            else:
                f = QFont("Segoe UI", int(s), QFont.Black)
                p.setFont(f)
                p.setPen(QColor(25, 20, 30, int(230 * a)))
                p.drawText(QPointF(x, y), "z")

    def bounds(self):
        return [QRect(int(it[0] - 25), int(it[1] - 30), 50, 50) for it in self.items]


# ───────────────────────── облачко с репликой ─────────────────────────

class Bubble:
    MAXW = 250

    def __init__(self, anchor_fn, text, owner="hua", duration=None):
        self.anchor_fn = anchor_fn
        self.text = text
        self.owner = owner
        self.age = 0.0
        self.dur = duration or (3.5 + len(text) / 14)
        self.font = QFont("Segoe UI", 10)
        fm = QFontMetrics(self.font)
        self.tr = fm.boundingRect(QRect(0, 0, self.MAXW, 1000), Qt.TextWordWrap, text)
        self.rect = QRectF()

    def step(self, dt):
        self.age += dt
        return self.age < self.dur

    def layout(self, screen):
        a = self.anchor_fn()
        pad = 10
        w = self.tr.width() + 2 * pad
        h = self.tr.height() + 2 * pad
        x = clamp(a.x() - w / 2, screen.left() + 4, screen.right() - w - 4)
        y = max(screen.top() + 4, a.y() - h - 14)
        self.rect = QRectF(x, y, w, h)
        return a

    def draw(self, p, screen):
        a = self.layout(screen)
        alpha = clamp(min(self.age / 0.2, (self.dur - self.age) / 0.4), 0, 1)
        p.setOpacity(alpha)
        r = self.rect
        path = QPainterPath()
        path.addRoundedRect(r, 10, 10)
        tx = clamp(a.x(), r.left() + 14, r.right() - 14)
        tail = QPainterPath()
        tail.moveTo(tx - 8, r.bottom() - 1)
        tail.lineTo(tx, r.bottom() + 11)
        tail.lineTo(tx + 8, r.bottom() - 1)
        path = path.united(tail)
        from characters import me
        th = me().theme
        p.setPen(QPen(QColor(*th["bubble_border"]), 1.4))
        p.setBrush(QColor(*th["bubble_bg"]))
        p.drawPath(path)
        p.setPen(QColor(*th["bubble_text"]))
        p.setFont(self.font)
        p.drawText(r.adjusted(10, 10, -10, -10), Qt.TextWordWrap, self.text)
        p.setOpacity(1)

    def bounds(self):
        return [self.rect.adjusted(-4, -4, 4, 16).toAlignedRect()]


# ───────────────────────── красная нить ─────────────────────────

class RedString:
    def __init__(self, world):
        self.w = world
        self.path = None

    def update_path(self):
        a = self.w.hua.anchor("hand")
        c = QCursor.pos()
        b = QPointF(c.x() + 2, c.y() + 2)
        dist = math.hypot(b.x() - a.x(), b.y() - a.y())
        sag = min(140, dist * 0.28) + math.sin(self.w.now * 2) * 6
        mid = QPointF((a.x() + b.x()) / 2, max(a.y(), b.y()) + sag)
        path = QPainterPath(a)
        path.quadTo(mid, b)
        self.path = path

    def draw(self, p):
        if not self.path or not self.w.hua.visible_now():
            return
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(120, 0, 10, 90), 4, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(self.path)
        p.setPen(QPen(QColor(215, 25, 40), 1.8, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(self.path)
        end = self.path.currentPosition()
        p.setBrush(QColor(215, 25, 40))
        p.setPen(Qt.NoPen)
        p.drawEllipse(end, 3, 3)

    def bounds(self):
        if not self.path:
            return []
        return [self.path.boundingRect().adjusted(-8, -8, 8, 8).toAlignedRect()]


# ───────────────────────── слой поверх экрана ─────────────────────────

class Overlay(QWidget):
    def __init__(self, world):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
                         | Qt.NoDropShadowWindowHint)
        self.w = world
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setGeometry(world.screen_geo)
        self.prev = QRegion()

    def refresh(self):
        rects = self.w.dirty_rects()
        origin = self.w.screen_geo.topLeft()
        reg = QRegion()
        for r in rects:
            reg = reg.united(QRegion(r.translated(-origin)))
        self.update(reg.united(self.prev))
        self.prev = reg

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setClipRegion(e.region())
        origin = self.w.screen_geo.topLeft()
        p.translate(-origin.x(), -origin.y())
        self.w.draw_overlay(p)
        p.end()
