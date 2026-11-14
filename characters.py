"""Персонаж этой программы: Хуа Чен.
Здесь его характер, позы, реплики и набор умений. Другие персонажи — отдельные программы;
если они установлены на этом компьютере, Хуа Чен находит их сам (см. ipc.py)."""
from types import SimpleNamespace

ME = "hua"

PERSONA = None   # характер Хуа Чена записан в agent.py (SYSTEM)

PHRASES = None   # реплики Хуа Чена лежат в phrases.py

THEME = {'bg': (40, 8, 14, 238), 'border': (200, 210, 225), 'text': '#f3e9e9', 'input_bg': '#2a0a10', 'input_border': '#b9c3d3', 'accent': '#7d1020', 'accent_hover': '#a3172b', 'btn_border': '#c9d2e0', 'title': '#d9e2f0', 'status': '#aab4c4', 'me_color': '#e9b8c0', 'name_color': '#dfe7f4', 'bubble_bg': (45, 10, 16, 232), 'bubble_border': (205, 215, 230), 'bubble_text': (248, 238, 238)}   # цвета чата, карточек и облачков

CHARS = {ME: dict(
    theme=THEME, module=None, menu_hide=(), daily=True, teleport=True,
    name='Хуа Чен', gen='Хуа Чена', port=0, butterflies=True, eming=True,
    persona=PERSONA, phrases=PHRASES,
    poses={'idle': 'idle', 'walk': 'walk', 'dice': 'dice', 'umbrella': 'umbrella', 'sleep': 'sleep', 'pet': 'pet', 'scold': 'scold', 'drink': 'drink', 'swing': 'swing'},
    state_pose={'sleep': 'sleep', 'pet': 'pet', 'dice': 'dice', 'rain': 'umbrella', 'scold': 'scold'},
    exclude=['make_presentation'],   # умения, которых у него нет (это дело других)
    greet=('{Addr}. Наконец-то. Теперь я буду рядом.', 'Вот и ты, {addr}. Мы вместе уже {days}.'),
)}
CHARS[ME]["exclude"] = set(CHARS[ME]["exclude"])

NAMES = {'hua': 'Хуа Чен', 'wwx': 'Вэй Усянь', 'lz': 'Лань Чжань'}

# Перебранки с друзьями, когда оба запущены: кому → [(моя реплика, его ответ)]
BANTER_ALL = {ME: {
    "wwx": [
        [
            "Вэй Усянь, кувшин ещё не пуст?",
            "Обижаешь! Уже второй."
        ],
        [
            "Сыграем в кости вечером?",
            "Только если ты не будешь жульничать. Хотя будешь."
        ],
        [
            "Не шуми. {Addr} работает.",
            "Я тихо! Я вообще сама тишина."
        ]
    ],
    "lz": [
        [
            "Ханьгуан-цзюнь, улыбнись хоть раз.",
            "…"
        ],
        [
            "Твои кролики опять на моей половине экрана.",
            "Они сами выбирают."
        ],
        [
            "{Addr} сегодня хорошо потрудилась. Скажи ей.",
            "Мгм. Хорошо."
        ]
    ]
}}

GUEST = [False]


def detect(argv):
    return ME


def set_current(cid=ME, guest=False):
    GUEST[0] = guest


def me():
    return SimpleNamespace(id=ME, guest=GUEST[0], **CHARS[ME])
