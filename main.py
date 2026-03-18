"""TFT-Sniper 入口 — 权限检测 → 加载配置 → 监听 → 识别 → 点击"""

import os
import queue
import re
import sys
import time
import tomllib

import logger

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.toml")
PRESET_NAMES = ("preset1", "preset2", "preset3")
MATCH_MODES = {"name", "thumb"}

_config = {}


def _normalize_config(config: dict) -> dict:
    """兼容误写到 [presets] 下的顶层标量配置。"""
    presets = config.get("presets", {})
    if not isinstance(presets, dict):
        return config

    hoist_keys = ("animation_delay", "debounce_cooldown", "debug")
    for key in hoist_keys:
        if key in config:
            continue
        if key not in presets:
            continue
        config[key] = presets.pop(key)

    return config


def load_config() -> dict:
    """加载配置文件"""
    global _config
    with open(CONFIG_PATH, "rb") as f:
        _config = tomllib.load(f)
    _config = _normalize_config(_config)
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


def _resolve_target_heroes():
    """解析当前生效的阵容预设，兼容旧 target_heroes 配置。"""
    presets = _config.get("presets", {})
    if not isinstance(presets, dict) or not presets:
        heroes = [str(hero).strip() for hero in _config.get("target_heroes", []) or []]
        heroes = [hero for hero in heroes if hero]
        return "", heroes, None

    active_preset = str(_config.get("active_preset", "") or "").strip()
    if active_preset not in presets:
        fallback = next((name for name in PRESET_NAMES if name in presets), None)
        if fallback is None:
            fallback = next(iter(presets.keys()), "")
        if not fallback:
            return "", [], "⚠️ presets 已配置，但没有可用预设"
        warning = (
            f"⚠️ active_preset={active_preset or '(未配置)'} 无效，"
            f"本次临时回退到 {fallback}"
        )
        active_preset = fallback
    else:
        warning = None

    raw_heroes = presets.get(active_preset, [])
    if not isinstance(raw_heroes, list):
        raw_heroes = []
    heroes = [str(hero).strip() for hero in raw_heroes if str(hero).strip()]
    return active_preset, heroes, warning


def _print_config():
    active_preset, heroes, warning = _resolve_target_heroes()
    match_mode, mode_warning = _resolve_match_mode()
    window_cfg = _config.get("window", {})
    click_cfg = _config.get("click", {})
    delay = float(_config.get("animation_delay", 0.42) or 0.42)
    if warning:
        logger.info(warning)
    if mode_warning:
        logger.info(mode_warning)
    logger.info(f"   匹配模式: {'英雄名 OCR' if match_mode == 'name' else '拇指标记'}")
    if match_mode == "name":
        if active_preset:
            logger.info(f"   当前预设: {active_preset}")
        logger.info(f"   目标英雄: {heroes if heroes else '(未配置)'}")
    else:
        logger.info("   目标英雄: (当前模式忽略预设，按拇指标记购买)")
        logger.info(
            f"   拇指阈值: {float(_config.get('thumb', {}).get('threshold', 0.70) or 0.70):.2f}"
        )
        logger.info(
            f"   搜索余量: {int(_config.get('thumb', {}).get('search_padding', 6) or 6)}pt"
        )
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


def _resolve_match_mode():
    mode = str(_config.get("match_mode", "name") or "name").strip().lower()
    if mode in MATCH_MODES:
        return mode, None
    fallback = "name"
    warning = f"⚠️ match_mode={mode or '(未配置)'} 无效，本次回退到 {fallback}"
    return fallback, warning


def _set_active_preset_in_config(preset_name: str):
    """把 active_preset 写回 config.toml。"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    new_line = f'active_preset = "{preset_name}"'
    if re.search(r'^active_preset\s*=', content, flags=re.MULTILINE):
        # 兼容双引号、单引号和无引号写法
        content = re.sub(
            r'^active_preset\s*=\s*["\']?.*["\']?\s*$',
            new_line,
            content,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        content = new_line + "\n\n" + content

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def switch_preset(slot: int):
    """切换到 preset1/2/3，并写回 config.toml。"""
    preset_name = f"preset{slot}"
    presets = _config.get("presets", {})
    if not isinstance(presets, dict) or not presets:
        logger.info("⚠️ 当前未配置 [presets]，无法切换阵容预设")
        return

    if preset_name not in presets:
        logger.info(f"⚠️ 当前未配置 {preset_name}")
        return

    current_preset, current_heroes, _ = _resolve_target_heroes()
    if current_preset == preset_name:
        logger.info(f"🎛 当前已是 {preset_name}: {current_heroes if current_heroes else '(空预设)'}")
        return

    try:
        _set_active_preset_in_config(preset_name)
        load_config()
        _, heroes, warning = _resolve_target_heroes()
        if warning:
            logger.info(warning)
        logger.info(f"🎛 已切换到 {preset_name}: {heroes if heroes else '(空预设)'}")
    except Exception as e:
        logger.info(f"❌ 阵容切换失败: {e}")


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
    """核心流程：等待动画 → 识别 → 匹配 → 点击"""
    import capture, ocr, matcher, action, thumb, window

    t0 = time.perf_counter()
    debug = _config.get("debug", False)
    match_mode, mode_warning = _resolve_match_mode()

    # 1. 解算窗口内 ROI
    roi, click_y, target_window = window.resolve_geometry(_config)
    if roi is None:
        logger.info("⚠️ 未找到目标窗口，请检查 config.toml 的 [window] 配置")
        return
    click_targets, jitter, click_warning = window.resolve_click_targets(_config, target_window)
    if mode_warning:
        logger.info(mode_warning)

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

    active_preset, heroes, _ = _resolve_target_heroes()
    t_capture = 0.0
    t_recognize = 0.0
    slots = []
    raw_items = []

    # thumb 模式刻意收敛在这一个分支里，便于后续整段移除或单独优化。
    if match_mode == "thumb":
        t1 = time.perf_counter()
        slots, raw_items, thumb_warning = thumb.recognize(_config, target_window)
        t_recognize = time.perf_counter() - t1
        if thumb_warning:
            logger.info(f"⚠️ {thumb_warning}")
            return
        hits = matcher.match(slots, heroes, mode=match_mode)
    else:
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

        t2 = time.perf_counter()
        slots, raw_items = ocr.recognize(cgimage)
        t_recognize = time.perf_counter() - t2
        hits = matcher.match(slots, heroes, mode=match_mode)

    if debug:
        hit_set = set(hits)
        if match_mode == "thumb":
            logger.debug(f"拇指原始结果: {raw_items}")
            for i, s in enumerate(slots):
                action_text = "购买" if i in hit_set else "跳过"
                logger.debug(
                    f"  卡槽{i + 1}: thumb={'是' if s.get('thumb', False) else '否'} "
                    f"score={s.get('thumb_score', 0.0):.3f} -> {action_text}"
                )
        else:
            logger.debug(f"OCR 原始结果: {raw_items}")
            if active_preset:
                logger.debug(f"当前预设: {active_preset} -> {heroes if heroes else '(空预设)'}")
            else:
                logger.debug(f"当前目标: {heroes if heroes else '(未配置)'}")
            for i, s in enumerate(slots):
                name = s["name"] or "(空)"
                if not s["name"]:
                    action_text = "空槽"
                elif i in hit_set:
                    action_text = "购买"
                else:
                    action_text = "跳过"
                logger.debug(f"  卡槽{i + 1}: {name} -> {action_text}")
        logger.debug(f"命中卡槽: {[idx + 1 for idx in hits] if hits else '(无)'}")

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
        repeat_count=_config.get("click", {}).get("repeat_count", 2),
        repeat_gap_ms=_config.get("click", {}).get("repeat_gap_ms", 25),
    )
    for idx in hits:
        label = slots[idx].get("name", "") or "拇指标记"
        logger.hit(label, idx)

    t_total = time.perf_counter() - t0
    if debug:
        if match_mode == "thumb":
            logger.debug(
                f"耗时: 等待={t_wait * 1000:.1f}ms "
                f"Thumb={t_recognize * 1000:.1f}ms "
                f"总计={t_total * 1000:.1f}ms"
            )
        else:
            logger.debug(
                f"耗时: 等待={t_wait * 1000:.1f}ms "
                f"截图={t_capture * 1000:.1f}ms "
                f"OCR={t_recognize * 1000:.1f}ms "
                f"总计={t_total * 1000:.1f}ms"
            )
    elif not hits:
        logger.info(f"未命中 ({t_total * 1000:.0f}ms)")


def main():
    print("=" * 40)
    print("  TFT-Sniper v0.1")
    print("=" * 40)

    # 设置进程名，便于后台运行时识别
    try:
        import setproctitle
        setproctitle.setproctitle("TFT-Sniper")
    except ImportError:
        pass

    # 加载模块（pyobjc 首次导入较慢）
    print("⏳ 加载模块...", end="", flush=True)
    import permissions, trigger
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
    trigger.init(_config.get("debounce_cooldown", 0.05), reload_config, switch_preset)
    task_queue = trigger.start()

    bundle_id = ""
    game_running = True

    logger.info(
        "🎮 已启动，Shift+D 刷新识别，Cmd+Option+1/2/3 切换预设，"
        "Cmd+Shift+R 重载配置，Ctrl+C 退出"
    )
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
