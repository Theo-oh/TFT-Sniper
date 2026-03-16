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
    window_cfg = _config.get("window", {})
    click_cfg = _config.get("click", {})
    wait_mode = _config.get("wait_mode", "adaptive")
    logger.info(f"   目标英雄: {heroes if heroes else '(未配置)'}")
    logger.info(f"   目标价格: {costs if costs else '(未配置)'}")
    if window_cfg.get("enabled", False):
        logger.info("   ROI 模式: 跟随金铲铲窗口")
    else:
        logger.info("   ROI 模式: 屏幕绝对坐标")
    logger.info(f"   等待模式: {wait_mode}")
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


def process():
    """核心流程：等待动画 → 截图 → OCR → 匹配 → 点击购买"""
    import capture, ocr, matcher, action, window

    t0 = time.perf_counter()
    debug = _config.get("debug", False)
    wait_mode = _config.get("wait_mode", "adaptive")

    # 1. 解算窗口内 ROI
    roi, click_y, target_window, scale_x, scale_y = window.resolve_geometry(_config)
    if roi is None:
        logger.info("⚠️ 未找到目标窗口，请检查 config.toml 的 [window] 配置")
        return
    click_targets, jitter, click_warning = window.resolve_click_targets(
        _config, target_window, scale_x, scale_y
    )

    if debug and target_window:
        logger.debug(
            f"窗口: {target_window['owner_name']} / {target_window['name']} "
            f"[{target_window['bundle_id']}] "
            f"@ ({target_window['left']}, {target_window['top']}) "
            f"{target_window['width']}x{target_window['height']} "
            f"缩放=({scale_x:.3f}, {scale_y:.3f})"
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

    # 2. 等待商店刷新并拿到最终截图
    wait_stats = None
    probe_roi = capture.make_probe_roi(roi) if wait_mode == "adaptive" else None
    if debug and probe_roi is not None:
        logger.debug(f"等待探针 ROI: {probe_roi}")
    if wait_mode == "adaptive":
        cgimage, wait_stats = capture.wait_for_refresh(
            roi,
            probe_roi=probe_roi,
            min_wait=_config.get("min_wait", 0.18),
            max_wait=_config.get("max_wait", 0.45),
            poll_interval=_config.get("poll_interval", 0.02),
        )
        if cgimage is None:
            logger.info("⚠️ 截图失败，请检查屏幕录制权限")
            return
        t_wait = wait_stats["elapsed_ms"] / 1000
        t_probe_capture = wait_stats["probe_capture_ms"] / 1000
        t_capture = wait_stats["final_capture_ms"] / 1000
    else:
        delay = _config.get("animation_delay", 0.18)
        time.sleep(delay)
        t_wait = delay
        t_probe_capture = 0.0

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
        logger.hit(slots[idx]["name"], slots[idx]["cost"], idx)

    t_total = time.perf_counter() - t0
    if debug:
        if wait_mode == "adaptive" and wait_stats is not None:
            logger.debug(
                f"耗时: 等待={t_wait * 1000:.1f}ms "
                f"探针截图={t_probe_capture * 1000:.1f}ms "
                f"最终截图={t_capture * 1000:.1f}ms "
                f"OCR={t_ocr * 1000:.1f}ms "
                f"总计={t_total * 1000:.1f}ms"
            )
            logger.debug(
                f"等待详情: polls={wait_stats['polls']} "
                f"changed={wait_stats['change_detected']} "
                f"stable={wait_stats['stable_detected']} "
                f"max_diff={wait_stats['max_diff']:.1f}"
            )
        else:
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

    logger.info("🎮 已启动，按 Shift+D 刷新识别，Cmd+Shift+R 重载配置，Ctrl+C 退出")
    print()

    try:
        while True:
            task_queue.get()  # 阻塞等待 d 键触发
            process()
    except KeyboardInterrupt:
        logger.info("👋 已退出")


if __name__ == "__main__":
    main()
