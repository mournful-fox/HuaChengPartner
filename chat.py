"""Окошко переписки с Хуа Ченом и карточка подтверждения «Да / Нет»."""
import html

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

def style():
    from characters import me
    t = me().theme
    return f"""
QWidget {{ color: {t['text']}; font-family: 'Segoe UI'; font-size: 10pt; }}
QTextBrowser {{ background: transparent; border: none; }}
QLineEdit {{ background: {t['input_bg']}; border: 1px solid {t['input_border']}; border-radius: 8px; padding: 6px 8px;
            selection-background-color: {t['accent']}; }}
QPushButton {{ background: {t['accent']}; color: {t.get('btn_text', t['text'])}; border: 1px solid {t['btn_border']}; border-radius: 8px; padding: 5px 14px; }}
QPushButton:hover {{ background: {t['accent_hover']}; }}
QPushButton#ghost {{ background: transparent; color: {t['text']}; }}
QPushButton#ghost:hover {{ background: {t['accent']}; color: {t.get('btn_text', t['text'])}; }}
QLabel#title {{ color: {t['title']}; font-weight: 600; }}
QLabel#status {{ color: {t['status']}; font-size: 9pt; }}
"""


class _Panel(QWidget):
    """Тёмно-алая полупрозрачная панель с серебряной рамкой."""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        from characters import me
        self.theme = me().theme
        self.setStyleSheet(style())
        self._drag = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        p.fillPath(path, QColor(*self.theme["bg"]))
        if self.theme.get("motif") == "cloud":       # облачный узор Гусу в углу
            from gusu import draw_cloud
            p.setClipPath(path)
            draw_cloud(p, self.width() - 46, self.height() - 34, 40, self.theme["border"], 0.22)
            draw_cloud(p, self.width() * 0.3, self.height() - 16, 22, self.theme["border"], 0.13)
            p.setClipping(False)
        p.setPen(QPen(QColor(*self.theme["border"]), 1.3))
        p.drawPath(path)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def place_near(self, anchor, screen):
        x = int(anchor.x() - self.width() / 2)
        y = int(anchor.y() - self.height() - 16)
        x = max(screen.left() + 8, min(screen.right() - self.width() - 8, x))
        y = max(screen.top() + 8, y)
        self.move(QPoint(x, y))


class ChatWindow(_Panel):
    def __init__(self, world):
        super().__init__()
        self.w = world
        self.resize(360, 380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        top = QHBoxLayout()
        from characters import me
        self.me = me().name
        t = QLabel(self.me)
        t.setObjectName("title")
        self.title = t
        top.addWidget(t)
        top.addStretch()
        clear = QPushButton("Новый разговор")
        clear.setObjectName("ghost")
        clear.clicked.connect(self.clear)
        close = QPushButton("✕")
        close.setObjectName("ghost")
        close.clicked.connect(self.hide)
        top.addWidget(clear)
        top.addWidget(close)
        lay.addLayout(top)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(False)
        lay.addWidget(self.view, 1)
        self.status = QLabel("")
        self.status.setObjectName("status")
        lay.addWidget(self.status)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Напиши ему…  (Esc — закрыть)")
        self.input.returnPressed.connect(self.send)
        row = QHBoxLayout()
        row.addWidget(self.input, 1)
        self.mic = QPushButton("🎙")
        self.mic.setToolTip("Сказать голосом (Ctrl+Alt+V)")
        self.mic.clicked.connect(world.toggle_voice)
        row.addWidget(self.mic)
        world.agent.on_status = lambda t: self.status.setText(t or (f"{self.me} думает…" if world.agent.busy else ""))
        lay.addLayout(row)
        self.lines = []

    def open(self):
        from agent import PROVIDERS
        p = self.w.agent.provider()
        self.title.setText(self.me + " · " + ("Ollama, " + self.w.agent.model() if p == "ollama"
                                           else PROVIDERS[p]["title"].split(" (")[0]))
        self.place_near(self.w.hua.head(), self.w.avail)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(e)

    def add(self, who, text):
        color = self.theme["me_color"] if who == "me" else self.theme["name_color"]
        name = "Ты" if who == "me" else self.me
        body = html.escape(text).replace("\n", "<br>")
        self.lines.append(f"<p style='margin:4px 0'><b style='color:{color}'>{name}:</b> {body}</p>")
        self.view.setHtml("".join(self.lines[-60:]))
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def clear(self):
        self.lines = []
        self.view.clear()
        self.w.agent.reset()

    def attach_image(self):
        self.add("me", "📷 [снимок экрана]")
        self.status.setText("Снимок прикреплён — спроси, что нужно (или просто нажми Enter).")
        self.input.setFocus()

    def send(self):
        text = self.input.text().strip()
        img = self.w.pending_image
        if (not text and not img) or self.w.agent.busy:
            return
        self.input.clear()
        if text:
            self.add("me", text)
        self.status.setText(f"{self.me} думает…")
        self.w.hua_thinking(True)
        if img:
            self.w.pending_image = None
            self.w.agent.ask_with_image(text, img, self.reply)
            return
        if self.w.diary_mode:                 # вечерний рассказ о дне — сразу в дневник
            self.w.diary_mode = False
            day = __import__("datetime").date.today().isoformat()
            diary = self.w.cfg.setdefault("diary", {})
            diary[day] = (diary.get(day, "") + " " + text).strip()
            self.w.cfg.save()
            self.w.reward("diary")
            text = "(Это мой рассказ о сегодняшнем дне, ты уже записал его в дневник. Ответь тепло и коротко.) " + text
        if self.w.extra and self.w.extra.on_user_text(text):
            pass
        self.w.agent.ask(text, self.reply)

    def send_voice(self, wav):
        self.add("me", "🎙 …")
        self.w.hua_thinking(True)
        if self.w.agent.provider() == "gemini":          # Gemini понимает аудио сам
            self.status.setText(f"{self.me} слушает запись…")
            self.w.agent.ask_voice(wav, self.reply, on_transcript=self.set_transcript)
        else:                                            # OpenAI / Groq: сначала распознаём речь
            self.status.setText("Распознаю речь…")
            self.w.agent.transcribe_then_ask(wav, self.reply, self.set_transcript)

    def set_transcript(self, heard):
        if self.lines and "🎙 …" in self.lines[-1]:
            self.lines.pop()
        self.add("me", "🎙 " + heard)

    def set_recording(self, on):
        self.mic.setText("■" if on else "🎙")

    def reply(self, text):
        self.status.setText("")
        self.w.hua_thinking(False)
        self.add("hua", text)
        self.w.talk(text=text if len(text) < 160 else text[:157] + "…")


class ChoiceCard(_Panel):
    """Карточка с несколькими кнопками: options = [(подпись, ключ), …]."""

    def __init__(self, world, text, options, callback):
        super().__init__()
        self.cb = callback
        self.setMinimumWidth(340)
        self.setMaximumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lab = QLabel(text)
        lab.setWordWrap(True)
        lay.addWidget(lab)
        row = QHBoxLayout()
        row.addStretch()
        for i, (label, key) in enumerate(options):
            b = QPushButton(label)
            if i < len(options) - 1 and len(options) > 1:
                b.setObjectName("ghost")
            b.clicked.connect(lambda _=False, k=key: self._done(k))
            row.addWidget(b)
        lay.addLayout(row)
        self.adjustSize()
        self.place_near(world.hua.head(), world.avail)
        self.show()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._done(None)

    def _done(self, key):
        cb, self.cb = self.cb, None
        self.close()
        if cb:
            cb(key)


class ConfirmCard(_Panel):
    """Карточка подтверждения: агент сам ничего не закрывает и не переносит без «Да»."""

    def __init__(self, world, text, callback, yes_text="Да", no_text="Нет"):
        super().__init__()
        self.cb = callback
        self.setMinimumWidth(320)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setTextInteractionFlags(Qt.NoTextInteraction)
        lay.addWidget(lab)
        row = QHBoxLayout()
        row.addStretch()
        no = QPushButton(no_text)
        no.setObjectName("ghost")
        yes = QPushButton(yes_text)
        no.clicked.connect(lambda: self._done(False))
        yes.clicked.connect(lambda: self._done(True))
        row.addWidget(no)
        row.addWidget(yes)
        lay.addLayout(row)
        self.adjustSize()
        self.place_near(world.hua.head(), world.avail)
        self.show()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._done(False)

    def _done(self, yes):
        cb, self.cb = self.cb, None
        self.close()
        if cb:
            cb(yes)
