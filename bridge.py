"""Связь с расширением Chrome: локальный WebSocket-сервер на 127.0.0.1:47321.
Принимает подключения только от расширений браузера (Origin chrome-extension://...)."""
import itertools
import json

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocketServer

PORT = 47321


class Bridge:
    def __init__(self, world):
        self.w = world
        self.server = QWebSocketServer("HuaChengPartner", QWebSocketServer.NonSecureMode)
        self.sock = None
        self.pending = {}
        self.ids = itertools.count(1)
        from characters import me
        self.ok = self.server.listen(QHostAddress.LocalHost, PORT + me().port)   # у каждого персонажа свой порт
        self.server.newConnection.connect(self._on_conn)

    def connected(self):
        return self.sock is not None

    def not_connected_text(self):
        return ("Расширение Chrome не подключено. Нужно установить его: меню Хуа Чена → "
                "«Расширение для Chrome…», и чтобы Chrome был открыт.")

    def _on_conn(self):
        s = self.server.nextPendingConnection()
        if not s.origin().startswith("chrome-extension://"):
            s.close()
            return
        if self.sock:
            self.sock.close()
        self.sock = s
        s.textMessageReceived.connect(self._on_msg)
        s.disconnected.connect(lambda s=s: self._on_close(s))

    def _on_close(self, s):
        if self.sock is s:
            self.sock = None
            for cb in list(self.pending.values()):
                cb(None)
            self.pending.clear()

    def _on_msg(self, text):
        try:
            m = json.loads(text)
        except ValueError:
            return
        if m.get("event") == "tab":            # расширение сообщает, что вкладка открыла адрес
            self.w.on_tab(m.get("url", ""), m.get("tabId"))
            return
        cb = self.pending.pop(m.get("id"), None)
        if cb:
            cb(m)

    def request(self, cmd, payload, callback, timeout_ms=6000):
        """callback(ответ) или callback(None), если расширение не подключено/не ответило."""
        if not self.sock:
            QTimer.singleShot(0, lambda: callback(None))
            return
        rid = next(self.ids)
        self.pending[rid] = callback
        self.sock.sendTextMessage(json.dumps(dict(payload, id=rid, cmd=cmd)))

        def expire():
            cb = self.pending.pop(rid, None)
            if cb:
                cb(None)
        QTimer.singleShot(timeout_ms, expire)
