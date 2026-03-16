"""TFT-Sniper 入口 — 权限检测 → 加载配置 → 监听 → 识别 → 购买"""

import os
import sys
import time
import tomllib

import logger

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.toml")

_config = {}


def load_config() -> dict:
    """加载配置文件"""
    global _config
    with open(CONFIG_PATH, "rb") as f:
        _config = tomllib.load(f)
    logger.init(_config.get("debug", False))
    return _config


def reload_config():
    """热重载配置"""
    try:
        load_config()
        logger.info("✅ 配置已重载")
        _print_config()
    except Exception as e:
        logger.info(f"❌ 配置重载失败: {e}")


def _print_config():
    heroes = _config.get("target_heroes", [])
    costs = _config.get("target_costs", [])
    logger.info(f"   目标英雄: {heroes if heroes else '(未配置)'}")
    logger.info(f"   目标价格: {costs if costs else '(未配置)'}")


def process():
    """核心流程：等待动画 → 截图 → OCR → 匹配 → 点击购买"""
    import capture, ocr, matcher, action

    t0 = time.perf_counter()
    roi = _config["roi"]
    debug = _config.get("debug", False)

    # 1. 等待卡牌翻转动画
    delay = _config.get("animation_delay", 0.18)
    time.sleep(delay)

    # 2. 截图
    t1 = time.perf_counter()
    cgimage = capture.grab(roi)
    if cgimage is None:
        logger.info("⚠️ 截图失败，请检查屏幕录制权限")
        return
    t_capture = time.perf_counter() - t1

    # 调试：保存截图
    if debug:
        debug_path = os.path.join(os.path.dirname(CONFIG_PATH), "debug_capture.png")
        capture.save(cgimage, debug_path)
        logger.debug(f"截图已保存: {debug_path}")

    # 3. OCR 识别
    t2 = time.perf_counter()
    level = _config.get("recognition_level", "fast")
    slots, raw_texts = ocr.recognize(cgimage, level=level)
    t_ocr = time.perf_counter() - t2

    if debug:
        logger.debug(f"OCR 原始结果: {raw_texts}")
        for i, s in enumerate(slots):
            logger.debug(f"  卡槽{i + 1}: {s}")

    # 4. 匹配
    heroes = _config.get("target_heroes", [])
    costs = _config.get("target_costs", [])
    hits = matcher.match(slots, heroes, costs)

    # 5. 点击购买（从右到左）
    click_y = _config.get("click_y", 0)
    for idx in hits:
        action.click_card(idx, roi, click_y=click_y)
        logger.hit(slots[idx]["name"], slots[idx]["cost"], idx)

    t_total = time.perf_counter() - t0
    if debug:
        logger.debug(
            f"耗时: 截图={t_capture * 1000:.1f}ms "
            f"OCR={t_ocr * 1000:.1f}ms "
            f"总计={t_total * 1000:.1f}ms"
        )
    elif not hits:
        logger.info(f"未命中 ({t_total * 1000:.0f}ms)")


def main():
    print("=" * 40)
    print("  TFT-Sniper v0.1")
    print("=" * 40)

    # 加载模块（pyobjc 首次导入较慢）
    print("⏳ 加载模块...", end="", flush=True)
    import logger, permissions, trigger
    print(" ✅")

    # 权限检测
    print("⏳ 检测权限...", end="", flush=True)
    if not permissions.check_all():
        sys.exit(1)

    # 加载配置
    load_config()
    _print_config()

    # 校验 ROI
    roi = _config["roi"]
    if roi["width"] <= 0 or roi["height"] <= 0:
        logger.info("❌ 请先在 config.toml 中配置 roi 坐标")
        sys.exit(1)

    # 启动键盘监听
    trigger.init(_config.get("debounce_cooldown", 0.05), reload_config)
    task_queue = trigger.start()

    logger.info("🎮 已启动，按 d 刷新识别，Cmd+Shift+R 重载配置，Ctrl+C 退出")
    print()

    try:
        while True:
            task_queue.get()  # 阻塞等待 d 键触发
            process()
    except KeyboardInterrupt:
        logger.info("👋 已退出")


if __name__ == "__main__":
    main()
