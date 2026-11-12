"""Окошко переписки с Хуа Ченом и карточка подтверждения «Да / Нет»."""
import html

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

STYLE = """
QWidget { color: #f3e9e9; font-family: 'Segoe UI'; font-size: 10pt; }
QTextBrowser { background: transparent; border: none; }
QLineEdit { background: #2a0a10; border: 1px solid #b9c3d3; border-radius: 8px; padding: 6px 8px;
            selection-background-color: #8a1424; }
QPushButton { background: #7d1020; border: 1px solid #c9d2e0; border-radius: 8px; padding: 5px 14px; }
QPushButton:hover { background: #a3172b; }
QPushButton#ghost { background: transparent; }
QLabel#title { color: #d9e2f0; font-weight: 600; }
QLabel#status { color: #aab4c4; font-size: 9pt; }
"""


class _Panel(QWidget):
    """Тёмно-алая полупрозрачная панель с серебряной рамкой."""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)
        self._drag = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        p.fillPath(path, QColor(40, 8, 14, 238))
        p.setPen(QPen(QColor(200, 210, 225), 1.3))
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
        t = QLabel("Хуа Чен")
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
        world.agent.on_status = lambda t: self.status.setText(t or ("Хуа Чен думает…" if world.agent.busy else ""))
        lay.addLayout(row)
        self.lines = []

    def open(self):
        from agent import PROVIDERS
        p = self.w.agent.provider()
        self.title.setText("Хуа Чен · " + ("Ollama, " + self.w.agent.model() if p == "ollama"
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
        color = "#e9b8c0" if who == "me" else "#dfe7f4"
        name = "Ты" if who == "me" else "Хуа Чен"
        body = html.escape(text).replace("\n", "<br>")
        self.lines.append(f"<p style='margin:4px 0'><b style='color:{color}'>{name}:</b> {body}</p>")
        self.view.setHtml("".join(self.lines[-60:]))
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def clear(self):
        self.lines = []
        self.view.clear()
        self.w.agent.reset()

    def send(self):
        text = self.input.text().strip()
        if not text or self.w.agent.busy:
            return
        self.input.clear()
        self.add("me", text)
        self.status.setText("Хуа Чен думает…")
        self.w.hua_thinking(True)
        self.w.agent.ask(text, self.reply)

    def send_voice(self, wav):
        self.add("me", "🎙 …")
        self.status.setText("Хуа Чен слушает запись…")
        self.w.hua_thinking(True)
        self.w.agent.ask_voice(wav, self.reply, on_transcript=self.set_transcript)

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
