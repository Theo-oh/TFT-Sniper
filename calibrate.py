"""ROI 与点击点位校准工具

使用方法:
1. 打开游戏，进入有商店的界面
2. 运行此脚本: .venv/bin/python calibrate.py
3. 将鼠标移到商店卡牌行的【左上角】，按空格键记录
4. 将鼠标移到商店卡牌行的【右下角】，按空格键记录
5. 依次将鼠标移到 5 张卡牌的【点击中心】，每次按空格键记录
6. 脚本会输出 ROI 坐标和点击点位，并自动写入 config.toml
"""

import os
import re
import sys
import tomllib

print("⏳ 加载模块...", end="", flush=True)
from pynput import keyboard, mouse
import window
print(" ✅")

_mouse_ctrl = mouse.Controller()
_points = []
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.toml")
_TOTAL_POINTS = 7
_STEP_HINTS = {
    0: "👉 将鼠标移到商店卡牌行的【左上角】，按空格键",
    1: "👉 现在将鼠标移到商店卡牌行的【右下角】，按空格键",
    2: "👉 现在将鼠标移到【第1张卡】点击中心，按空格键",
    3: "👉 现在将鼠标移到【第2张卡】点击中心，按空格键",
    4: "👉 现在将鼠标移到【第3张卡】点击中心，按空格键",
    5: "👉 现在将鼠标移到【第4张卡】点击中心，按空格键",
    6: "👉 现在将鼠标移到【第5张卡】点击中心，按空格键",
}


def _section_range(content: str, section: str):
    """返回 TOML section 的文本范围 (start, end)。"""
    header = re.search(
        rf'^\[{re.escape(section)}\]\s*$', content, flags=re.MULTILINE
    )
    if header is None:
        return None, None
    start = header.end()
    # section 到下一个 [xxx] 或 EOF 结束
    nxt = re.search(r'^\[', content[start:], flags=re.MULTILINE)
    end = start + nxt.start() if nxt else len(content)
    return start, end


def _replace_in_section(content: str, section: str, key: str, value) -> str:
    """在指定 TOML section 内替换 key = value（仅标量值）。"""
    start, end = _section_range(content, section)
    if start is None:
        return content
    segment = content[start:end]
    pattern = re.compile(rf'^({re.escape(key)}\s*=\s*).*$', flags=re.MULTILINE)
    new_seg = pattern.sub(rf'\g<1>{value}', segment, count=1)
    return content[:start] + new_seg + content[end:]


def _replace_block_in_section(
    content: str, section: str, pattern: str, replacement: str
) -> str:
    """在指定 TOML section 内替换一个多行块（如 slot_points = [...]）。"""
    start, end = _section_range(content, section)
    if start is None:
        return content
    segment = content[start:end]
    new_seg = re.sub(pattern, replacement, segment, count=1, flags=re.MULTILINE)
    return content[:start] + new_seg + content[end:]


def _print_next_hint():
    idx = len(_points)
    if idx < _TOTAL_POINTS:
        print(_STEP_HINTS[idx])


def _on_press(key):
    if key == keyboard.Key.space:
        pos = _mouse_ctrl.position
        _points.append(pos)
        idx = len(_points)

        if idx == 1:
            print(f"  ✅ 左上角: ({pos[0]:.0f}, {pos[1]:.0f})")
            _print_next_hint()
        elif idx == 2:
            print(f"  ✅ 右下角: ({pos[0]:.0f}, {pos[1]:.0f})")
            _print_next_hint()
        elif 3 <= idx <= 7:
            print(f"  ✅ 卡槽{idx - 2}: ({pos[0]:.0f}, {pos[1]:.0f})")
            if idx >= _TOTAL_POINTS:
                return False  # 停止监听
            _print_next_hint()

        if idx >= _TOTAL_POINTS:
            return False  # 停止监听

    elif key == keyboard.Key.esc:
        print("已取消")
        sys.exit(0)


def main():
    with open(CONFIG_PATH, "rb") as f:
        config = tomllib.load(f)

    print()
    print("=" * 40)
    print("  ROI 与点击点位校准工具")
    print("=" * 40)
    print()
    _print_next_hint()
    print("   (按 Esc 取消)")
    print()

    with keyboard.Listener(on_press=_on_press) as listener:
        listener.join()

    if len(_points) < _TOTAL_POINTS:
        return

    x1, y1 = _points[0]
    x2, y2 = _points[1]

    roi = {
        "top": int(min(y1, y2)),
        "left": int(min(x1, x2)),
        "width": int(abs(x2 - x1)),
        "height": int(abs(y2 - y1)),
    }
    click_y = roi["top"] - roi["height"]
    slot_points = [{"x": int(x), "y": int(y)} for x, y in _points[2:7]]
    window_cfg = config.get("window", {})
    target_window = None

    if window_cfg.get("enabled", False):
        target_window = window.find_window(window_cfg)
        if target_window:
            roi["top"] -= target_window["top"]
            roi["left"] -= target_window["left"]
            click_y -= target_window["top"]
            for point in slot_points:
                point["x"] -= target_window["left"]
                point["y"] -= target_window["top"]
        else:
            print("⚠️ 未找到目标窗口，将按屏幕绝对坐标写入")

    print()
    if target_window:
        print("📐 ROI 坐标 (相对窗口 Point):")
        print(
            f"   window = {target_window['owner_name']} / {target_window['name']} "
            f"({target_window['width']}x{target_window['height']})"
        )
    else:
        print("📐 ROI 坐标 (Point):")
    print(f"   top    = {roi['top']}")
    print(f"   left   = {roi['left']}")
    print(f"   width  = {roi['width']}")
    print(f"   height = {roi['height']}")

    # 建议 click_y（ROI 上方偏移，卡牌中部）
    print(f"   click_y = {click_y}  (建议值，卡牌中部)")
    print()
    print("🎯 点击点位:")
    for i, point in enumerate(slot_points, start=1):
        print(f"   卡槽{i}: x = {point['x']}, y = {point['y']}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # [roi] section
    content = _replace_in_section(content, "roi", "top", roi["top"])
    content = _replace_in_section(content, "roi", "left", roi["left"])
    content = _replace_in_section(content, "roi", "width", roi["width"])
    content = _replace_in_section(content, "roi", "height", roi["height"])
    content = _replace_in_section(content, "roi", "click_y", click_y)

    # [click] section
    content = _replace_in_section(content, "click", "use_slot_points", "true")
    slot_points_block = "slot_points = [\n" + "\n".join(
        f"  {{ x = {point['x']}, y = {point['y']} }}," for point in slot_points
    ) + "\n]"
    content = _replace_block_in_section(
        content, "click", r"^slot_points\s*=\s*\[(?:.|\n)*?\]", slot_points_block
    )

    # [window] section
    if target_window:
        content = _replace_in_section(
            content, "window", "reference_width", target_window["width"]
        )
        content = _replace_in_section(
            content, "window", "reference_height", target_window["height"]
        )

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print()
    print("✅ 已自动写入 config.toml")
    print("   现在可以运行: .venv/bin/python main.py")


if __name__ == "__main__":
    main()
