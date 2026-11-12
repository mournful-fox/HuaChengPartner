"""Э-Мин — живой ятаган Хуа Чена. Ведёт себя как ревнивый щенок: скачет по панели задач,
увязывается за курсором, дуется, если его отругать, и ревнует, когда гладят хозяина.

Внешний вид: по умолчанию рисуется серебряный изогнутый ятаган с красной кистью.
Если положить в папку assets свой рисунок eming.png (клинок остриём ВПРАВО, прозрачный фон),
программа возьмёт его.
"""
import math
import os
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QCursor, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtWidgets import QWidget

GRAV = 1300


class EMingWindow(QWidget):
    def __init__(self, world):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.w = world
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        path = world.asset("eming.png")
        self.custom = QPixmap(path) if os.path.exists(path) else None
        self.state = "sheathed"
        self.x = self.y = 0.0
        self.vx = self.vy = 0.0
        self.angle = 0.0      # градусы; 0 — остриё вправо
        self.facing = 1
        self.t = 0.0
        self.timer = 0.0
        self.out_until = 0.0
        self.spin_left = 0.0
        self.drag = None
        self.resize_for_size()

    def resize_for_size(self):
        self.L = self.w.cfg["size"] * (0.85 if self.custom else 0.6)
        s = int(self.L * 1.6)
        self.S = s
        self.resize(s, s)

    def thickness(self):
        if self.custom and not self.custom.isNull():
            return self.L * self.custom.height() / self.custom.width() * 0.4
        return self.L * 0.09

    # ── команды ──
    def release(self, jealous=False):
        w = self.w
        hip = w.hua.anchor("hip")
        self.x, self.y = hip.x(), hip.y()
        self.vx, self.vy = random.uniform(-200, 200), -420
        self.angle = -90
        self.state = "jealous" if jealous else "jump"
        self.timer = 3.5 if jealous else 0
        self.out_until = w.now + w.cfg["eming_walk_minutes"] * 60
        self.show()
        self.raise_()
        w.swarm.burst(hip.x(), hip.y(), n=2, radius=50)
        if jealous:
            w.bubble(self.bubble_anchor, "eming_jealous", owner="eming")
        else:
            w.talk("eming_out")

    def recall(self, scold=False):
        if self.state == "sheathed":
            return
        self.state = "return"
        self.w.talk("eming_scold" if scold else "eming_back")

    def flourish(self):
        """Взмах: Э-Мин крутится и оставляет серебряный росчерк."""
        if self.state == "sheathed":
            self.release()
        self.spin_left = 0.55
        self.w.add_slash(self.x, self.y, random.uniform(-40, 40), self.L * 0.75)
        self.w.bubble(self.bubble_anchor, "eming_click", owner="eming")

    def bubble_anchor(self):
        return QPointF(self.x, self.y - self.L * 0.3)

    # ── логика ──
    def step(self, dt):
        if self.state == "sheathed":
            return
        self.t += dt
        w = self.w
        a = w.avail
        floor = w.floor_y() - self.thickness()
        cur = QCursor.pos()

        if self.state not in ("return", "drag", "sheathed") and w.now > self.out_until:
            self.recall()

        if self.state in ("jump", "fall"):
            self.vy += GRAV * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.angle += (self.vx * 0.9) * dt * (2 if self.state == "jump" else 1)
            if self.y >= floor:
                self.y = floor
                if self.state == "fall" and self.vy > 500:
                    self.vy *= -0.35
                    self.vx *= 0.5
                else:
                    self.land()
        elif self.state == "ground":
            self.timer -= dt
            target = 0 if self.facing > 0 else 180
            wag = math.sin(self.t * 14) * 9 if self.wagging else 0
            self.angle += (target + wag - self.angle) * min(1, dt * 10)
            if self.timer <= 0:
                self.next_action()
        elif self.state == "sulk":
            self.timer -= dt
            self.angle += (172 - self.angle) * min(1, dt * 4)   # лежит, отвернувшись
            if self.timer <= 0:
                self.land()
        elif self.state in ("follow", "jealous", "return"):
            if self.state == "return":
                hip = w.hua.anchor("hip")
                tx, ty, sp = hip.x(), hip.y(), 700
            else:
                ang = self.t * 3
                r = 46 if self.state == "follow" else 30
                tx, ty = cur.x() + math.cos(ang) * r, cur.y() + 20 + math.sin(ang) * r * 0.6
                sp = 520 if self.state == "follow" else 700
            dx, dy = tx - self.x, ty - self.y
            d = math.hypot(dx, dy) or 1e-3
            want = sp * min(1, d / 90)
            self.vx += (dx / d * want - self.vx) * min(1, dt * 5)
            self.vy += (dy / d * want - self.vy) * min(1, dt * 5)
            self.x += self.vx * dt
            self.y += self.vy * dt
            # летит остриём вперёд
            if math.hypot(self.vx, self.vy) > 40:
                target = math.degrees(math.atan2(self.vy, self.vx))
                diff = (target - self.angle + 540) % 360 - 180
                self.angle += diff * min(1, dt * 8)
            self.timer -= dt
            if self.state == "return" and d < 20:
                self.sheathe()
                return
            if self.state in ("follow", "jealous") and self.timer <= 0:
                if self.state == "jealous":
                    w.add_slash(self.x, self.y, random.uniform(-30, 30), self.L * 0.6)
                self.state = "fall"
                self.vx, self.vy = random.uniform(-80, 80), -100
        elif self.state == "drag":
            pass

        if self.spin_left > 0:
            self.spin_left -= dt
            self.angle += 1300 * dt

        self.x = max(a.left() + 20, min(a.right() - 20, self.x))
        self.y = min(self.y, floor) if self.state not in ("follow", "jealous", "return", "drag") else self.y
        self.move(int(self.x - self.S / 2), int(self.y - self.S / 2))
        self.update()

    wagging = False

    def land(self):
        self.state = "ground"
        self.vx = self.vy = 0
        self.y = self.w.floor_y() - self.thickness()
        self.facing = 1 if math.cos(math.radians(self.angle)) >= 0 else -1
        self.angle %= 360
        if self.angle > 180:
            self.angle -= 360
        self.timer = random.uniform(1.5, 4)
        self.wagging = random.random() < 0.3

    def next_action(self):
        r = random.random()
        if r < 0.55:      # прыжок вбок
            self.state = "jump"
            self.facing = random.choice((-1, 1)) if random.random() < 0.3 else self.facing
            self.vx = self.facing * random.uniform(120, 260)
            self.vy = -random.uniform(300, 480)
        elif r < 0.72:    # увязаться за курсором
            self.state = "follow"
            self.timer = random.uniform(5, 9)
            if random.random() < 0.4:
                self.w.bubble(self.bubble_anchor, "eming_follow", owner="eming")
        elif r < 0.80:    # вернуться к хозяину ненадолго — прыгнуть рядом
            hx = self.w.hua.fx
            self.state = "jump"
            self.vx = max(-400, min(400, (hx - self.x) * 0.9))
            self.vy = -500
        else:             # повилять рукоятью на месте
            self.wagging = True
            self.timer = random.uniform(1.5, 3)

    def sheathe(self):
        self.state = "sheathed"
        self.hide()
        hip = self.w.hua.anchor("hip")
        self.w.swarm.burst(hip.x(), hip.y(), n=2, radius=40)

    # ── мышь ──
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            g = e.globalPosition()
            self.drag = {"start": g, "moved": False, "last": g, "dx": self.x - g.x(), "dy": self.y - g.y()}

    def mouseMoveEvent(self, e):
        if not self.drag:
            return
        g = e.globalPosition()
        d = self.drag
        if not d["moved"] and (g - d["start"]).manhattanLength() > 6:
            d["moved"] = True
            self.state = "drag"
        if d["moved"]:
            self.vx = (g.x() - d["last"].x()) * 40
            self.vy = (g.y() - d["last"].y()) * 40
            d["last"] = g
            self.x, self.y = g.x() + d["dx"], g.y() + d["dy"]
            self.angle = math.sin(self.w.now * 25) * 15 - 90   # висит и дрыгается

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or not self.drag:
            return
        moved = self.drag["moved"]
        self.drag = None
        if moved:
            self.state = "fall"
            self.vx = max(-900, min(900, self.vx))
            self.vy = max(-900, min(900, self.vy))
        else:
            self.flourish()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.recall()

    def contextMenuEvent(self, e):
        self.w.show_menu(e.globalPos())

    def scold(self):
        """Хуа Чен отчитал — Э-Мин дуется."""
        if self.state == "sheathed":
            return
        self.w.talk("eming_scold")
        if self.w.hua.state in ("idle", "walk"):
            self.w.hua.enter("scold", dur=2.2)
        self.state = "sulk"
        self.timer = 8
        self.vx = self.vy = 0
        self.y = self.w.floor_y() - self.thickness()
        self.w.bubble(self.bubble_anchor, "eming_sulk", owner="eming")

    # ── отрисовка ──
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        c = self.S / 2
        p.translate(c, c)
        p.save()
        p.rotate(self.angle)
        if self.custom and not self.custom.isNull():
            if getattr(self, "_pm_w", None) != int(self.L):
                self._pm = self.custom.scaledToWidth(int(self.L), Qt.SmoothTransformation)
                self._pm_w = int(self.L)
            pm = self._pm
            p.drawPixmap(int(-pm.width() / 2), int(-pm.height() / 2), pm)
            pommel = None
        else:
            pommel = self.draw_blade(p)
        p.restore()
        if pommel is not None:
            # кисть всегда висит вниз, как бы ни был повёрнут клинок
            a = math.radians(self.angle)
            px = pommel.x() * math.cos(a) - pommel.y() * math.sin(a)
            py = pommel.x() * math.sin(a) + pommel.y() * math.cos(a)
            self.draw_tassel(p, px, py)
        p.end()

    def draw_blade(self, p):
        L = self.L
        # клинок
        blade = QPainterPath()
        blade.moveTo(-0.26 * L, -0.028 * L)
        blade.cubicTo(0.0, -0.035 * L, 0.33 * L, -0.07 * L, 0.5 * L, -0.2 * L)
        blade.cubicTo(0.43 * L, -0.02 * L, 0.06 * L, 0.075 * L, -0.26 * L, 0.03 * L)
        blade.closeSubpath()
        g = QLinearGradient(0, -0.12 * L, 0, 0.06 * L)
        g.setColorAt(0, QColor(150, 160, 178))
        g.setColorAt(0.45, QColor(238, 242, 250))
        g.setColorAt(1, QColor(170, 180, 198))
        p.setBrush(g)
        p.setPen(QPen(QColor(70, 78, 95), 1.1))
        p.drawPath(blade)
        # дол и блик по лезвию
        p.setBrush(Qt.NoBrush)
        dol = QPainterPath()
        dol.moveTo(-0.22 * L, -0.012 * L)
        dol.cubicTo(0.0, -0.02 * L, 0.25 * L, -0.045 * L, 0.38 * L, -0.11 * L)
        p.setPen(QPen(QColor(120, 130, 150, 160), 1.2))
        p.drawPath(dol)
        edge = QPainterPath()
        edge.moveTo(-0.2 * L, 0.024 * L)
        edge.cubicTo(0.05 * L, 0.06 * L, 0.4 * L, -0.02 * L, 0.48 * L, -0.17 * L)
        p.setPen(QPen(QColor(255, 255, 255, 230), 1.4))
        p.drawPath(edge)
        # гарда — серебряный полумесяц
        guard = QPainterPath()
        guard.moveTo(-0.27 * L, -0.085 * L)
        guard.quadTo(-0.22 * L, 0, -0.27 * L, 0.085 * L)
        guard.quadTo(-0.31 * L, 0, -0.27 * L, -0.085 * L)
        p.setPen(QPen(QColor(80, 88, 105), 1))
        p.setBrush(QColor(205, 212, 225))
        p.drawPath(guard)
        # рукоять, обмотанная тёмной тканью
        grip = QRectF(-0.48 * L, -0.026 * L, 0.2 * L, 0.052 * L)
        p.setBrush(QColor(42, 30, 36))
        p.setPen(QPen(QColor(20, 12, 16), 1))
        p.drawRoundedRect(grip, 3, 3)
        p.setPen(QPen(QColor(170, 175, 190, 200), 1))
        x = grip.left() + 4
        while x < grip.right() - 2:
            p.drawLine(QPointF(x, grip.top() + 1), QPointF(x + 4, grip.bottom() - 1))
            x += 6
        # навершие
        p.setPen(QPen(QColor(80, 88, 105), 1))
        p.setBrush(QColor(210, 216, 228))
        p.drawEllipse(QPointF(-0.495 * L, 0), 0.03 * L, 0.035 * L)
        return QPointF(-0.5 * L, 0)

    def draw_tassel(self, p, x, y):
        L = self.L
        sw = math.sin(self.t * 3) * 4 - self.vx * 0.01
        ln = 0.22 * L
        end = QPointF(x + sw, y + ln)
        p.setPen(QPen(QColor(200, 20, 35), 1.6))
        p.drawLine(QPointF(x, y), end)
        p.setBrush(QColor(200, 20, 35))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(x + sw * 0.3, y + ln * 0.3), 2.4, 2.4)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(215, 160, 60), 1.8))
        p.drawEllipse(end + QPointF(0, 5), 5, 6)
        p.setPen(QPen(QColor(220, 228, 240), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(end + QPointF(0, 12), end + QPointF(sw * 0.4, 12 + 0.22 * L))
