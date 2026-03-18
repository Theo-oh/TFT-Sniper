"""键盘监听 — Shift+D 触发识别，Cmd+Shift+R 热重载，Cmd+Option+1/2/3 切预设"""

import queue
import time

from pynput.keyboard import Key, KeyCode, Listener

# macOS virtual key codes
VK_D = 0x02
VK_R = 0x0F
VK_1 = 0x12
VK_2 = 0x13
VK_3 = 0x14

_task_queue = queue.Queue()
_last_trigger = 0.0
_debounce = 0.05
_modifiers = set()
_reload_cb = None
_preset_cb = None
_enabled = True
_listener = None


def init(debounce: float, reload_callback, preset_callback=None):
    """初始化防抖参数、热重载回调和预设切换回调。"""
    global _debounce, _reload_cb, _preset_cb
    _debounce = debounce
    _reload_cb = reload_callback
    _preset_cb = preset_callback


def set_enabled(enabled: bool):
    """启用或暂停 Shift+D 热键。"""
    global _enabled
    _enabled = bool(enabled)


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
    if key in (Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr):
        _modifiers.add("alt")
        return

    vk = _get_vk(key)

    # Cmd+Shift+R → 热重载
    if "cmd" in _modifiers and "shift" in _modifiers and vk == VK_R:
        if _reload_cb:
            _reload_cb()
        return

    # Cmd+Option+1/2/3 → 切换阵容预设
    if _modifiers == {"cmd", "alt"} and _preset_cb:
        preset_slot = {VK_1: 1, VK_2: 2, VK_3: 3}.get(vk)
        if preset_slot is not None:
            _preset_cb(preset_slot)
            return

    if not _enabled:
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
    if key in (Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr):
        _modifiers.discard("alt")


def start():
    """启动监听（守护线程），返回任务队列"""
    global _listener
    if _listener is None:
        _listener = Listener(on_press=_on_press, on_release=_on_release)
        _listener.daemon = True
        _listener.start()
    return _task_queue
