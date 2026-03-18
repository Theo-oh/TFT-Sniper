"""ROI、点击点位与拇指模板校准工具

使用方法:
1. 打开游戏，进入有商店的界面
2. 运行此脚本: .venv/bin/python calibrate.py
3. 将鼠标移到商店卡牌行的【左上角】，按空格键记录
4. 将鼠标移到商店卡牌行的【右下角】，按空格键记录
5. 依次将鼠标移到 5 张卡牌的【点击中心】，每次按空格键记录
6. 脚本会输出 ROI 坐标和点击点位，并自动写入 config.toml

如需校准拇指标记模板与检测区域:
- .venv/bin/python calibrate.py --thumb
"""

import os
import re
import sys
import tomllib

print("⏳ 加载模块...", end="", flush=True)
from pynput import keyboard, mouse
import capture
import window
print(" ✅")

_mouse_ctrl = mouse.Controller()
_points = []
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.toml")
_TOTAL_POINTS = 0
_STEP_HINTS = []
_POINT_LABELS = []
_THUMB_TEMPLATE_NAME = "thumb_template.png"

_LAYOUT_STEP_HINTS = [
    "👉 将鼠标移到商店卡牌行的【左上角】，按空格键",
    "👉 现在将鼠标移到商店卡牌行的【右下角】，按空格键",
    "👉 现在将鼠标移到【第1张卡】点击中心，按空格键",
    "👉 现在将鼠标移到【第2张卡】点击中心，按空格键",
    "👉 现在将鼠标移到【第3张卡】点击中心，按空格键",
    "👉 现在将鼠标移到【第4张卡】点击中心，按空格键",
    "👉 现在将鼠标移到【第5张卡】点击中心，按空格键",
]
_LAYOUT_POINT_LABELS = [
    "左上角",
    "右下角",
    "卡槽1",
    "卡槽2",
    "卡槽3",
    "卡槽4",
    "卡槽5",
]

_THUMB_STEP_HINTS = [
    "👉 先保证屏幕上至少有一张带拇指标记的卡，再将鼠标移到该拇指模板的【左上角】，按空格键",
    "👉 现在将鼠标移到同一个拇指模板的【右下角】，按空格键",
    "👉 现在将鼠标移到【第1张卡】拇指标记中心，按空格键",
    "👉 现在将鼠标移到【第2张卡】拇指标记中心，按空格键",
    "👉 现在将鼠标移到【第3张卡】拇指标记中心，按空格键",
    "👉 现在将鼠标移到【第4张卡】拇指标记中心，按空格键",
    "👉 现在将鼠标移到【第5张卡】拇指标记中心，按空格键",
]
_THUMB_POINT_LABELS = [
    "模板左上角",
    "模板右下角",
    "卡槽1拇指中心",
    "卡槽2拇指中心",
    "卡槽3拇指中心",
    "卡槽4拇指中心",
    "卡槽5拇指中心",
]


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


def _replace_top_level_scalar(content: str, key: str, value) -> str:
    """替换顶层 key = value。"""
    pattern = re.compile(rf'^({re.escape(key)}\s*=\s*).*$', flags=re.MULTILINE)
    return pattern.sub(rf'\g<1>{value}', content, count=1)


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
        label = _POINT_LABELS[idx - 1]
        print(f"  ✅ {label}: ({pos[0]:.0f}, {pos[1]:.0f})")
        if idx >= _TOTAL_POINTS:
            return False  # 停止监听
        _print_next_hint()

        if idx >= _TOTAL_POINTS:
            return False  # 停止监听

    elif key == keyboard.Key.esc:
        print("已取消")
        sys.exit(0)


def _parse_mode():
    args = sys.argv[1:]
    if not args:
        return "layout"
    if args == ["--thumb"]:
        return "thumb"
    print("用法:")
    print("  .venv/bin/python calibrate.py")
    print("  .venv/bin/python calibrate.py --thumb")
    sys.exit(1)


def _run_listener():
    print()
    _print_next_hint()
    print("   (按 Esc 取消)")
    print()

    with keyboard.Listener(on_press=_on_press) as listener:
        listener.join()


def _resolve_target_window(config: dict):
    window_cfg = config.get("window", {})
    if not window_cfg.get("enabled", False):
        return None
    target_window = window.find_window(window_cfg)
    if target_window is None:
        print("⚠️ 未找到目标窗口，将按屏幕绝对坐标写入")
    return target_window


def _write_layout_calibration(config: dict):
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
    target_window = _resolve_target_window(config)

    if target_window:
        roi["top"] -= target_window["top"]
        roi["left"] -= target_window["left"]
        click_y -= target_window["top"]
        for point in slot_points:
            point["x"] -= target_window["left"]
            point["y"] -= target_window["top"]

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
    print(f"   click_y = {click_y}  (建议值，卡牌中部)")
    print()
    print("🎯 点击点位:")
    for i, point in enumerate(slot_points, start=1):
        print(f"   卡槽{i}: x = {point['x']}, y = {point['y']}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    content = _replace_in_section(content, "roi", "top", roi["top"])
    content = _replace_in_section(content, "roi", "left", roi["left"])
    content = _replace_in_section(content, "roi", "width", roi["width"])
    content = _replace_in_section(content, "roi", "height", roi["height"])
    content = _replace_top_level_scalar(content, "click_y", click_y)
    content = _replace_in_section(content, "click", "use_slot_points", "true")
    slot_points_block = "slot_points = [\n" + "\n".join(
        f"  {{ x = {point['x']}, y = {point['y']} }}," for point in slot_points
    ) + "\n]"
    content = _replace_block_in_section(
        content, "click", r"^slot_points\s*=\s*\[(?:.|\n)*?\]", slot_points_block
    )

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


def _write_thumb_calibration(config: dict):
    x1, y1 = _points[0]
    x2, y2 = _points[1]
    template_roi_abs = {
        "top": int(min(y1, y2)),
        "left": int(min(x1, x2)),
        "width": max(1, int(abs(x2 - x1))),
        "height": max(1, int(abs(y2 - y1))),
    }
    slot_regions = []
    for x, y in _points[2:7]:
        slot_regions.append(
            {
                "left": int(round(x - template_roi_abs["width"] / 2)),
                "top": int(round(y - template_roi_abs["height"] / 2)),
                "width": template_roi_abs["width"],
                "height": template_roi_abs["height"],
            }
        )

    target_window = _resolve_target_window(config)
    if target_window:
        for region in slot_regions:
            region["left"] -= target_window["left"]
            region["top"] -= target_window["top"]

    template_path = os.path.join(os.path.dirname(CONFIG_PATH), _THUMB_TEMPLATE_NAME)
    template_image = capture.grab(template_roi_abs)
    template_saved = template_image is not None
    if template_saved:
        capture.save(template_image, template_path)

    print()
    if target_window:
        print("👍 拇指检测区域 (相对窗口 Point):")
        print(
            f"   window = {target_window['owner_name']} / {target_window['name']} "
            f"({target_window['width']}x{target_window['height']})"
        )
    else:
        print("👍 拇指检测区域 (Point):")
    print(
        f"   模板大小: width = {template_roi_abs['width']}, "
        f"height = {template_roi_abs['height']}"
    )
    for i, region in enumerate(slot_regions, start=1):
        print(
            f"   卡槽{i}: left = {region['left']}, top = {region['top']}, "
            f"width = {region['width']}, height = {region['height']}"
        )
    if template_saved:
        print(f"   模板已保存: {template_path}")
    else:
        print("⚠️ 模板截图失败，请确认拇指标记未被遮挡后重试")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    content = _replace_in_section(
        content, "thumb", "template_path", f'"{_THUMB_TEMPLATE_NAME}"'
    )
    slot_regions_block = "slot_regions = [\n" + "\n".join(
        (
            f"  {{ left = {region['left']}, top = {region['top']}, "
            f"width = {region['width']}, height = {region['height']} }},"
        )
        for region in slot_regions
    ) + "\n]"
    content = _replace_block_in_section(
        content, "thumb", r"^slot_regions\s*=\s*\[(?:.|\n)*?\]", slot_regions_block
    )

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
    print("   如需启用拇指模式，请把 match_mode 改成 \"thumb\" 后按 Cmd+Shift+R 重载")


def main():
    global _TOTAL_POINTS, _STEP_HINTS, _POINT_LABELS

    mode = _parse_mode()
    with open(CONFIG_PATH, "rb") as f:
        config = tomllib.load(f)

    if mode == "thumb":
        _STEP_HINTS = _THUMB_STEP_HINTS
        _POINT_LABELS = _THUMB_POINT_LABELS
        title = "拇指模板与检测区域校准工具"
    else:
        _STEP_HINTS = _LAYOUT_STEP_HINTS
        _POINT_LABELS = _LAYOUT_POINT_LABELS
        title = "ROI 与点击点位校准工具"
    _TOTAL_POINTS = len(_STEP_HINTS)

    print()
    print("=" * 40)
    print(f"  {title}")
    print("=" * 40)

    _run_listener()
    if len(_points) < _TOTAL_POINTS:
        return

    if mode == "thumb":
        _write_thumb_calibration(config)
    else:
        _write_layout_calibration(config)


if __name__ == "__main__":
    main()
