"""TFT-Sniper 入口 — 权限检测 → 加载配置 → 监听 → 识别 → 点击"""

import os
import queue
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
    window_cfg = _config.get("window", {})
    click_cfg = _config.get("click", {})
    delay = float(_config.get("animation_delay", 0.42) or 0.42)
    logger.info(f"   目标英雄: {heroes if heroes else '(未配置)'}")
    if window_cfg.get("enabled", False):
        logger.info("   ROI 模式: 跟随金铲铲窗口")
    else:
        logger.info("   ROI 模式: 屏幕绝对坐标")
    logger.info(f"   固定等待: {delay:.2f}s")
    if click_cfg.get("use_slot_points", False):
        logger.info("   点击模式: 手工卡槽点位")
    else:
        logger.info("   点击模式: ROI 五等分推算")
    logger.info(
        "   点击时序: "
        f"settle={click_cfg.get('move_settle_ms', 16)}ms "
        f"hold={click_cfg.get('hold_ms', 18)}ms "
        f"gap={click_cfg.get('inter_click_ms', 70)}ms"
    )


def _target_bundle_id() -> str:
    """读取当前配置中的目标 bundle id。"""
    window_cfg = _config.get("window", {})
    return str(window_cfg.get("bundle_id", "") or "").strip()


def sync_runtime_state(previous_bundle_id: str, previous_running: bool):
    """同步金铲铲运行状态，并按需切换热键启用状态。"""
    import trigger, window

    bundle_id = _target_bundle_id()
    if not bundle_id:
        trigger.set_enabled(True)
        if previous_bundle_id:
            return bundle_id, True, "ℹ️ 未配置 bundle_id，Shift+D 将始终可用"
        return bundle_id, True, None

    running = window.is_app_running(bundle_id)
    trigger.set_enabled(running)

    if bundle_id != previous_bundle_id:
        if running:
            return bundle_id, running, f"🎮 已检测到 {bundle_id}，热键已激活"
        return bundle_id, running, f"⏳ 等待 {bundle_id} 启动，热键暂未激活"

    if running != previous_running:
        if running:
            return bundle_id, running, "🎮 检测到金铲铲已启动，热键已激活"
        return bundle_id, running, "⏸ 金铲铲已退出，热键已暂停"

    return bundle_id, running, None


def process():
    """核心流程：等待动画 → 截图 → OCR → 匹配 → 点击"""
    import capture, ocr, matcher, action, window

    t0 = time.perf_counter()
    debug = _config.get("debug", False)

    # 1. 解算窗口内 ROI
    roi, click_y, target_window = window.resolve_geometry(_config)
    if roi is None:
        logger.info("⚠️ 未找到目标窗口，请检查 config.toml 的 [window] 配置")
        return
    click_targets, jitter, click_warning = window.resolve_click_targets(_config, target_window)

    if debug and target_window:
        logger.debug(
            f"窗口: {target_window['owner_name']} / {target_window['name']} "
            f"[{target_window['bundle_id']}] "
            f"@ ({target_window['left']}, {target_window['top']}) "
            f"{target_window['width']}x{target_window['height']}"
        )
        logger.debug(f"本次 ROI: {roi}, click_y={click_y}")
        if click_targets:
            logger.debug(
                f"手动点击点位: {click_targets}, "
                f"jitter=({jitter['x']}, {jitter['y']})"
            )
    if target_window and target_window.get("size_warning"):
        logger.info(f"⚠️ {target_window['size_warning']}")
    if click_warning:
        logger.info(f"⚠️ {click_warning}，已回退到 ROI 五等分点击")

    # 2. 固定等待后截图
    delay = float(_config.get("animation_delay", 0.42) or 0.42)
    time.sleep(delay)
    t_wait = delay

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
    slots, raw_texts = ocr.recognize(cgimage)
    t_ocr = time.perf_counter() - t2

    if debug:
        logger.debug(f"OCR 原始结果: {raw_texts}")
        for i, s in enumerate(slots):
            logger.debug(f"  卡槽{i + 1}: {{'name': {s['name']!r}}}")

    # 4. 匹配
    heroes = _config.get("target_heroes", [])
    hits = matcher.match(slots, heroes)

    # 5. 点击（从右到左）
    action.click_cards(
        hits,
        roi,
        click_y=click_y,
        click_points=click_targets,
        jitter_x=jitter["x"],
        jitter_y=jitter["y"],
        move_settle_ms=_config.get("click", {}).get("move_settle_ms", 16),
        hold_ms=_config.get("click", {}).get("hold_ms", 18),
        inter_click_ms=_config.get("click", {}).get("inter_click_ms", 70),
        post_batch_ms=_config.get("click", {}).get("post_batch_ms", 18),
        timing_jitter_ms=_config.get("click", {}).get("timing_jitter_ms", 4),
    )
    for idx in hits:
        logger.hit(slots[idx]["name"], idx)

    t_total = time.perf_counter() - t0
    if debug:
        logger.debug(
            f"耗时: 等待={t_wait * 1000:.1f}ms "
            f"截图={t_capture * 1000:.1f}ms "
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

    bundle_id = ""
    game_running = True

    logger.info("🎮 已启动，按 Shift+D 刷新识别，Cmd+Shift+R 重载配置，Ctrl+C 退出")
    bundle_id, game_running, state_message = sync_runtime_state(bundle_id, game_running)
    if state_message:
        logger.info(state_message)
    print()

    try:
        while True:
            bundle_id, game_running, state_message = sync_runtime_state(bundle_id, game_running)
            if state_message:
                logger.info(state_message)

            try:
                task_queue.get(timeout=0.5)  # 等待 Shift+D，同时周期性同步游戏状态
            except queue.Empty:
                continue

            if bundle_id and not game_running:
                logger.info("⚠️ 金铲铲未运行，本次触发已忽略")
                continue
            process()
    except KeyboardInterrupt:
        logger.info("👋 已退出")


if __name__ == "__main__":
    main()
