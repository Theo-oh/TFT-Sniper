"""键盘监听 — Shift+D 触发识别，Cmd+Shift+R 热重载"""

import queue
import time

from pynput.keyboard import Key, KeyCode, Listener

# macOS virtual key codes
VK_D = 0x02
VK_R = 0x0F

_task_queue = queue.Queue()
_last_trigger = 0.0
_debounce = 0.05
_modifiers = set()
_reload_cb = None


def init(debounce: float, reload_callback):
    """初始化防抖参数和热重载回调"""
    global _debounce, _reload_cb
    _debounce = debounce
    _reload_cb = reload_callback


def _get_vk(key):
    """获取虚拟键码"""
    if isinstance(key, KeyCode):
        return getattr(key, "vk", None)
    return None


def _on_press(key):
    global _last_trigger

    # 跟踪修饰键
    if key in (Key.cmd, Key.cmd_l, Key.cmd_r):
        _modifiers.add("cmd")
        return
    if key in (Key.shift, Key.shift_l, Key.shift_r):
        _modifiers.add("shift")
        return

    vk = _get_vk(key)

    # Cmd+Shift+R → 热重载
    if "cmd" in _modifiers and "shift" in _modifiers and vk == VK_R:
        if _reload_cb:
            _reload_cb()
        return

    # Shift+D → 触发识别；其他带修饰组合不处理
    if vk == VK_D and _modifiers == {"shift"}:
        now = time.monotonic()
        if now - _last_trigger >= _debounce:
            _last_trigger = now
            _task_queue.put("trigger")


def _on_release(key):
    if key in (Key.cmd, Key.cmd_l, Key.cmd_r):
        _modifiers.discard("cmd")
    if key in (Key.shift, Key.shift_l, Key.shift_r):
        _modifiers.discard("shift")


def start():
    """启动监听（守护线程），返回任务队列"""
    listener = Listener(on_press=_on_press, on_release=_on_release)
    listener.daemon = True
    listener.start()
    return _task_queue
