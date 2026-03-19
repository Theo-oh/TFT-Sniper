"""拇指标记识别 — 基于 OpenCV NCC (归一化互相关) 的模板匹配

显著替换了原有手工像素遍历的低效与易受颜色干扰的逻辑，
直接进行 C++ 底层驱动的归一化互相关（ZNCC）模板对比。
"""

import os
import cv2
import numpy as np
import Quartz

import capture

SLOT_COUNT = 5
DEFAULT_THRESHOLD = 0.60
DEFAULT_SEARCH_PADDING = 6
BINARY_THRESHOLD = 200
_TEMPLATE_CACHE = {"path": "", "mtime": None, "image": None}


def _empty_slots():
    return [{"thumb": False, "thumb_score": 0.0} for _ in range(SLOT_COUNT)]


def _resolve_template_path(config: dict) -> str:
    thumb_cfg = config.get("thumb", {})
    template_path = str(thumb_cfg.get("template_path", "thumb_template.png") or "").strip()
    if not template_path:
        return ""
    if os.path.isabs(template_path):
        return template_path
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), template_path)


def _resolve_regions(config: dict, target_window=None):
    thumb_cfg = config.get("thumb", {})
    raw_regions = list(thumb_cfg.get("slot_regions", []) or [])
    if len(raw_regions) != SLOT_COUNT:
        return None, "拇指模式已启用，但 [thumb].slot_regions 不是 5 个区域"

    regions = []
    for i, region in enumerate(raw_regions):
        if not isinstance(region, dict):
            return None, f"拇指检测区域 slot_regions[{i}] 不是合法对象"

        left = int(region.get("left", 0) or 0)
        top = int(region.get("top", 0) or 0)
        width = int(region.get("width", 0) or 0)
        height = int(region.get("height", 0) or 0)
        if left < 0 or top < 0 or width <= 0 or height <= 0:
            return None, f"拇指检测区域 slot_regions[{i}] 未配置有效坐标"

        if target_window is not None:
            left += target_window["left"]
            top += target_window["top"]

        regions.append(
            {
                "left": left,
                "top": top,
                "width": width,
                "height": height,
            }
        )

    return regions, None


def _cgimage_to_cv2(cgimage):
    if cgimage is None:
        return None

    width = int(Quartz.CGImageGetWidth(cgimage) or 0)
    height = int(Quartz.CGImageGetHeight(cgimage) or 0)
    bytes_per_row = int(Quartz.CGImageGetBytesPerRow(cgimage) or 0)
    provider = Quartz.CGImageGetDataProvider(cgimage)
    if not provider:
        return None

    data = Quartz.CGDataProviderCopyData(provider)
    if not data:
        return None

    # 从 CGData 转 numpy 数组并去掉 padding
    buf = np.frombuffer(data, dtype=np.uint8)
    image_2d = buf.reshape((height, bytes_per_row // 4, 4))
    image_2d = image_2d[:, :width, :]

    # 转由 CGImage 产出的原生 BGRA 到单通道灰度
    gray = cv2.cvtColor(image_2d, cv2.COLOR_BGRA2GRAY)
    # 全局二值化：抛弃金色/杂色背景，只保留亮度>200的纯白高亮标记体
    _, binary = cv2.threshold(gray, BINARY_THRESHOLD, 255, cv2.THRESH_BINARY)
    return binary


def _is_degenerate_binary(image) -> bool:
    """常量模板会让 TM_CCOEFF_NORMED 退化成满分误判，必须提前拦截。"""
    white_pixels = int(cv2.countNonZero(image))
    total_pixels = int(image.size)
    return white_pixels == 0 or white_pixels == total_pixels


def _load_template_cv2(path: str):
    if not path:
        return None, "拇指模式已启用，但 [thumb].template_path 为空"
    if not os.path.exists(path):
        return None, f"未找到拇指模板: {path}"

    mtime = os.path.getmtime(path)
    if (
        _TEMPLATE_CACHE["path"] == path
        and _TEMPLATE_CACHE["mtime"] == mtime
        and _TEMPLATE_CACHE["image"] is not None
    ):
        return _TEMPLATE_CACHE["image"], None

    # 直接读取灰度图
    tpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if tpl is None:
        return None, f"无法读取拇指模板: {path}"

    # 同样对模板进行二值化处理
    _, tpl_binary = cv2.threshold(tpl, BINARY_THRESHOLD, 255, cv2.THRESH_BINARY)
    if _is_degenerate_binary(tpl_binary):
        return None, "拇指模板二值化后变成纯黑/纯白，无法安全匹配，请重新运行 calibrate.py --thumb"

    _TEMPLATE_CACHE["path"] = path
    _TEMPLATE_CACHE["mtime"] = mtime
    _TEMPLATE_CACHE["image"] = tpl_binary
    return tpl_binary, None


def _expand_region(region: dict, padding: int):
    if padding <= 0:
        return dict(region)

    left = max(0, region["left"] - padding)
    top = max(0, region["top"] - padding)
    right = region["left"] + region["width"] + padding
    bottom = region["top"] + region["height"] + padding
    return {
        "left": left,
        "top": top,
        "width": max(1, right - left),
        "height": max(1, bottom - top),
    }


def _union_regions(regions):
    left = min(region["left"] for region in regions)
    top = min(region["top"] for region in regions)
    right = max(region["left"] + region["width"] for region in regions)
    bottom = max(region["top"] + region["height"] for region in regions)
    return {
        "left": left,
        "top": top,
        "width": max(1, right - left),
        "height": max(1, bottom - top),
    }


def _slice_binary_region(binary_image, source_region: dict, target_region: dict):
    image_height, image_width = binary_image.shape[:2]
    scale_x = image_width / max(1, source_region["width"])
    scale_y = image_height / max(1, source_region["height"])

    x0 = int(round((target_region["left"] - source_region["left"]) * scale_x))
    y0 = int(round((target_region["top"] - source_region["top"]) * scale_y))
    x1 = int(
        round(
            (target_region["left"] + target_region["width"] - source_region["left"])
            * scale_x
        )
    )
    y1 = int(
        round(
            (target_region["top"] + target_region["height"] - source_region["top"])
            * scale_y
        )
    )

    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(image_width, x1)
    y1 = min(image_height, y1)
    if x0 >= x1 or y0 >= y1:
        return None
    return binary_image[y0:y1, x0:x1]


def recognize(config: dict, target_window=None):
    """识别 5 个卡槽是否带拇指标记，返回 (slots, raw_items, warning)。"""
    regions, warning = _resolve_regions(config, target_window)
    if warning:
        return _empty_slots(), [], warning

    template_path = _resolve_template_path(config)
    tpl_img, warning = _load_template_cv2(template_path)
    if warning:
        return _empty_slots(), [], warning

    threshold = float(
        config.get("thumb", {}).get("threshold", DEFAULT_THRESHOLD)
        or DEFAULT_THRESHOLD
    )
    search_padding = max(
        0,
        int(
            config.get("thumb", {}).get("search_padding", DEFAULT_SEARCH_PADDING)
            or DEFAULT_SEARCH_PADDING
        ),
    )

    slots = _empty_slots()
    raw_items = []
    expanded_regions = [_expand_region(region, search_padding) for region in regions]
    capture_region = _union_regions(expanded_regions)
    capture_binary = _cgimage_to_cv2(capture.grab(capture_region))

    for idx, sample_region in enumerate(expanded_regions):
        if capture_binary is None:
            raw_items.append(f"slot{idx + 1}: capture_failed")
            continue
        sample_img = _slice_binary_region(capture_binary, capture_region, sample_region)
        if sample_img is None:
            raw_items.append(f"slot{idx + 1}: capture_failed")
            continue

        if (
            sample_img.shape[0] < tpl_img.shape[0]
            or sample_img.shape[1] < tpl_img.shape[1]
        ):
            raw_items.append(f"slot{idx + 1}: region too small for template")
            continue

        res = cv2.matchTemplate(sample_img, tpl_img, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        hit = max_val >= threshold
        slots[idx]["thumb"] = hit
        slots[idx]["thumb_score"] = float(max_val)
        raw_items.append(f"slot{idx + 1}: score={max_val:.3f}, loc={max_loc}, hit={hit}")

    return slots, raw_items, None
