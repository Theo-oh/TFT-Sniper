"""日志与调试输出"""

import time

_debug = False


def init(debug: bool):
    global _debug
    _debug = debug


def info(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def debug(msg: str):
    if _debug:
        print(f"[{time.strftime('%H:%M:%S')}] [DEBUG] {msg}")


def hit(name: str, idx: int):
    info(f"🎯 卡槽{idx + 1}: {name} → 已点击")
