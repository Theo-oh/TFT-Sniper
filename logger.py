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


def hit(name: str, cost: int, idx: int):
    cost_text = f"{cost}金币" if cost > 0 else "?金币"
    info(f"🎯 卡槽{idx + 1}: {name} ({cost_text}) → 已点击")
