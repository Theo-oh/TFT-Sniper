"""截图模块 — 直接使用 Quartz，返回 CGImage，零格式转换"""

import time

import Quartz
from Foundation import NSURL


def grab(roi: dict):
    """截取 ROI 区域，返回 CGImage（坐标为 Point）"""
    rect = Quartz.CGRectMake(roi["left"], roi["top"], roi["width"], roi["height"])
    return Quartz.CGWindowListCreateImage(
        rect,
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
        Quartz.kCGWindowImageDefault,
    )


def make_probe_roi(roi: dict):
    """生成等待刷新的探针区域。

    只取名字行附近的一条细带，用更低开销判断画面是否已经变化。
    """
    top = roi["top"] + int(round(roi["height"] * 0.12))
    height = max(12, int(round(roi["height"] * 0.42)))
    left = roi["left"] + int(round(roi["width"] * 0.04))
    width = max(40, int(round(roi["width"] * 0.92)))
    return {"left": left, "top": top, "width": width, "height": height}


def _signature(cgimage, grid_x: int = 40, grid_y: int = 6):
    """提取轻量图像指纹，用于判断商店是否已经刷新。"""
    provider = Quartz.CGImageGetDataProvider(cgimage)
    if provider is None:
        return []

    data = bytes(Quartz.CGDataProviderCopyData(provider))
    width = Quartz.CGImageGetWidth(cgimage)
    height = Quartz.CGImageGetHeight(cgimage)
    if width <= 0 or height <= 0:
        return []

    bytes_per_row = Quartz.CGImageGetBytesPerRow(cgimage)
    signature = []
    for gy in range(grid_y):
        y = min((gy * height) // grid_y + height // (grid_y * 2), height - 1)
        row = y * bytes_per_row
        for gx in range(grid_x):
            x = min((gx * width) // grid_x + width // (grid_x * 2), width - 1)
            offset = row + x * 4
            r = data[offset]
            g = data[offset + 1]
            b = data[offset + 2]
            signature.append((r * 30 + g * 59 + b * 11) // 100)
    return signature


def _signature_diff(sig_a, sig_b) -> float:
    if not sig_a or not sig_b or len(sig_a) != len(sig_b):
        return 999.0
    return sum(abs(a - b) for a, b in zip(sig_a, sig_b)) / len(sig_a)


def wait_for_refresh(
    roi: dict,
    probe_roi: dict | None = None,
    min_wait: float = 0.0,
    max_wait: float = 0.45,
    poll_interval: float = 0.02,
    change_threshold: float = 8.0,
    stable_threshold: float = 2.0,
    stable_frames: int = 2,
):
    """等待商店从旧画面切到新画面并稳定下来。"""
    started_at = time.perf_counter()
    active_probe_roi = probe_roi or make_probe_roi(roi)
    stats = {
        "elapsed_ms": 0.0,
        "probe_capture_ms": 0.0,
        "final_capture_ms": 0.0,
        "polls": 0,
        "change_detected": False,
        "stable_detected": False,
        "max_diff": 0.0,
    }

    t0 = time.perf_counter()
    baseline_probe = grab(active_probe_roi)
    stats["probe_capture_ms"] += (time.perf_counter() - t0) * 1000
    if baseline_probe is None:
        stats["elapsed_ms"] = (time.perf_counter() - started_at) * 1000
        return None, stats

    baseline_sig = _signature(baseline_probe)
    prev_sig = baseline_sig
    stable_hits = 0

    if min_wait > 0:
        time.sleep(min_wait)

    while time.perf_counter() - started_at < max_wait:
        if poll_interval > 0:
            time.sleep(poll_interval)

        t1 = time.perf_counter()
        current_probe = grab(active_probe_roi)
        stats["probe_capture_ms"] += (time.perf_counter() - t1) * 1000
        stats["polls"] += 1
        if current_probe is None:
            break

        current_sig = _signature(current_probe)
        diff_from_baseline = _signature_diff(current_sig, baseline_sig)
        diff_from_prev = _signature_diff(current_sig, prev_sig)
        stats["max_diff"] = max(stats["max_diff"], diff_from_baseline, diff_from_prev)

        if not stats["change_detected"]:
            if diff_from_baseline >= change_threshold:
                stats["change_detected"] = True
                stable_hits = 0
        else:
            if diff_from_prev <= stable_threshold:
                stable_hits += 1
                if stable_hits >= stable_frames:
                    stats["stable_detected"] = True
                    break
            else:
                stable_hits = 0

        prev_sig = current_sig

    t2 = time.perf_counter()
    final_image = grab(roi)
    stats["final_capture_ms"] += (time.perf_counter() - t2) * 1000
    stats["elapsed_ms"] = (time.perf_counter() - started_at) * 1000
    return final_image, stats


def save(cgimage, path: str):
    """保存 CGImage 为 PNG（调试用）"""
    url = NSURL.fileURLWithPath_(path)
    dest = Quartz.CGImageDestinationCreateWithURL(url, "public.png", 1, None)
    if dest:
        Quartz.CGImageDestinationAddImage(dest, cgimage, None)
        Quartz.CGImageDestinationFinalize(dest)
