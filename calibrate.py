"""ROI 坐标校准工具

使用方法:
1. 打开游戏，进入有商店的界面
2. 运行此脚本: .venv/bin/python calibrate.py
3. 将鼠标移到商店卡牌行的【左上角】，按空格键记录
4. 将鼠标移到商店卡牌行的【右下角】，按空格键记录
5. 脚本会输出 ROI 坐标并自动写入 config.toml
"""

import sys

print("⏳ 加载模块...", end="", flush=True)
from pynput import keyboard, mouse
print(" ✅")

_mouse_ctrl = mouse.Controller()
_points = []


def _on_press(key):
    if key == keyboard.Key.space:
        pos = _mouse_ctrl.position
        _points.append(pos)

        if len(_points) == 1:
            print(f"  ✅ 左上角: ({pos[0]:.0f}, {pos[1]:.0f})")
            print("👉 现在将鼠标移到商店卡牌行的【右下角】，按空格键")
        elif len(_points) == 2:
            print(f"  ✅ 右下角: ({pos[0]:.0f}, {pos[1]:.0f})")
            return False  # 停止监听

    elif key == keyboard.Key.esc:
        print("已取消")
        sys.exit(0)


def main():
    print()
    print("=" * 40)
    print("  ROI 坐标校准工具")
    print("=" * 40)
    print()
    print("👉 将鼠标移到商店卡牌行的【左上角】，按空格键")
    print("   (按 Esc 取消)")
    print()

    with keyboard.Listener(on_press=_on_press) as listener:
        listener.join()

    if len(_points) < 2:
        return

    x1, y1 = _points[0]
    x2, y2 = _points[1]

    roi = {
        "top": int(min(y1, y2)),
        "left": int(min(x1, x2)),
        "width": int(abs(x2 - x1)),
        "height": int(abs(y2 - y1)),
    }

    print()
    print("📐 ROI 坐标 (Point):")
    print(f"   top    = {roi['top']}")
    print(f"   left   = {roi['left']}")
    print(f"   width  = {roi['width']}")
    print(f"   height = {roi['height']}")

    # 建议 click_y（ROI 上方偏移，卡牌中部）
    click_y = roi["top"] - roi["height"]
    print(f"   click_y = {click_y}  (建议值，卡牌中部)")

    # 写入 config.toml
    import os
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.toml")

    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    import re
    content = re.sub(r"^top\s*=\s*\d+", f"top = {roi['top']}", content, flags=re.MULTILINE)
    content = re.sub(r"^left\s*=\s*\d+", f"left = {roi['left']}", content, flags=re.MULTILINE)
    content = re.sub(r"^width\s*=\s*\d+", f"width = {roi['width']}", content, flags=re.MULTILINE)
    content = re.sub(r"^height\s*=\s*\d+", f"height = {roi['height']}", content, flags=re.MULTILINE)
    content = re.sub(r"^click_y\s*=\s*\d+", f"click_y = {click_y}", content, flags=re.MULTILINE)

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(content)

    print()
    print("✅ 已自动写入 config.toml")
    print("   现在可以运行: .venv/bin/python main.py")


if __name__ == "__main__":
    main()
