"""Связь между персонажами: у каждого процесса локальный сервер «HuaChengPartner-<id>».
Сообщения — строки JSON. Хозяин сцены шлёт гостю его позу и место, гость их показывает."""
import json
import os
import subprocess
import sys

from PySide6.QtNetwork import QLocalServer, QLocalSocket


def name(cid):
    return "HuaChengPartner-" + cid


class Link:
    def __init__(self, world, cid):
        self.w = world
        QLocalServer.removeServer(name(cid))
        self.server = QLocalServer()
        self.server.listen(name(cid))
        self.server.newConnection.connect(self._conn)
        self.socks = []

    def _conn(self):
        s = self.server.nextPendingConnection()
        self.socks.append(s)
        s.readyRead.connect(lambda s=s: self._read(s))
        s.disconnected.connect(lambda s=s: self.socks.remove(s) if s in self.socks else None)

    def _read(self, s):
        while s.canReadLine():
            try:
                self.w.on_remote(json.loads(bytes(s.readLine()).decode("utf-8")))
            except ValueError:
                pass


def connect(cid, timeout=150):
    s = QLocalSocket()
    s.connectToServer(name(cid))
    return s if s.waitForConnected(timeout) else None


def send(sock, msg):
    if sock and sock.state() == QLocalSocket.ConnectedState:
        sock.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        sock.flush()
        return True
    return False


def is_running(cid):
    s = connect(cid, 120)
    if s:
        s.disconnectFromServer()
        return True
    return False


def _registry():
    from config import _dir
    return os.path.join(_dir(), "friends.json")


def _load():
    try:
        with open(_registry(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def register(cid):
    """Каждый персонаж при запуске записывает, как его запустить, в общий список."""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--as", cid]
    else:
        cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"), "--as", cid]
    data = _load()
    if data.get(cid) != cmd:
        data[cid] = cmd
        try:
            with open(_registry(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
        except OSError:
            pass


def installed(cid):
    """Есть ли такой персонаж на этом компьютере (запускался хоть раз, и его файл на месте)."""
    cmd = _load().get(cid)
    return bool(cmd) and os.path.exists(cmd[0]) and (not cmd[1].endswith(".py") or os.path.exists(cmd[1]))


def launch(cid, guest=False):
    """Запускает другого персонажа — отдельную программу."""
    cmd = list(_load().get(cid) or [])
    if not cmd:
        raise OSError("не установлен")
    cmd += ["--guest"] if guest else []
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    subprocess.Popen(cmd, env=env, close_fds=True)
