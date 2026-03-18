"""拇指标记识别 — 基于固定小 ROI 的模板相似度匹配

该模块与名字 OCR 主链路保持隔离：
- main.py 只在 match_mode == "thumb" 时调用这里
- 删除 thumb 模式时，可优先移除本文件和 main.py 里的对应分支
"""

import math
import os

from Foundation import NSURL
import Quartz

import capture

SLOT_COUNT = 5
DEFAULT_THRESHOLD = 0.45
DEFAULT_MIN_WHITE_SCORE = 0.30
DEFAULT_MIN_GRAY_SCORE = 0.90
DEFAULT_SEARCH_PADDING = 6
DEFAULT_EDGE_TOLERANCE = 1
_TEMPLATE_CACHE = {"path": "", "mtime": None, "signature": None}


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


def _load_cgimage(path: str):
    url = NSURL.fileURLWithPath_(path)
    source = Quartz.CGImageSourceCreateWithURL(url, None)
    if source is None:
        return None
    return Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)


def _read_pixels(cgimage):
    if cgimage is None:
        return None

    width = int(Quartz.CGImageGetWidth(cgimage) or 0)
    height = int(Quartz.CGImageGetHeight(cgimage) or 0)
    bytes_per_row = int(Quartz.CGImageGetBytesPerRow(cgimage) or 0)
    provider = Quartz.CGImageGetDataProvider(cgimage)
    if width <= 0 or height <= 0 or bytes_per_row <= 0 or provider is None:
        return None

    data = Quartz.CGDataProviderCopyData(provider)
    if data is None:
        return None

    return width, height, bytes_per_row, bytes(data)


def _pixel_features(r: int, g: int, b: int):
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    is_white = lum >= 0.82 and (max_c - min_c) <= 32
    is_gold = (
        r >= 140
        and g >= 95
        and r > g > b
        and (r - b) >= 48
        and lum >= 0.45
    )
    return lum, 1 if is_gold else 0, 1 if is_white else 0


def _build_signature(cgimage):
    feature_maps = _extract_feature_maps(cgimage)
    if feature_maps is None:
        return None
    return _signature_from_maps(
        feature_maps, 0, 0, feature_maps["width"], feature_maps["height"]
    )


def _extract_feature_maps(cgimage):
    image_data = _read_pixels(cgimage)
    if image_data is None:
        return None

    width, height, bytes_per_row, buf = image_data
    gray_values = []
    gold_mask = []
    white_mask = []

    for y in range(height):
        row_start = y * bytes_per_row
        for x in range(width):
            offset = row_start + x * 4
            b = buf[offset]
            g = buf[offset + 1]
            r = buf[offset + 2]
            lum, is_gold, is_white = _pixel_features(r, g, b)
            gray_values.append(lum)
            gold_mask.append(is_gold)
            white_mask.append(is_white)

    return {
        "width": width,
        "height": height,
        "gray": gray_values,
        "gold": gold_mask,
        "white": white_mask,
    }


def _signature_from_maps(feature_maps, left: int, top: int, width: int, height: int):
    if (
        left < 0
        or top < 0
        or width <= 0
        or height <= 0
        or left + width > feature_maps["width"]
        or top + height > feature_maps["height"]
    ):
        return None

    gray_values = []
    gold_mask = []
    white_mask = []
    image_width = feature_maps["width"]

    for y in range(top, top + height):
        row_start = y * image_width + left
        row_end = row_start + width
        gray_values.extend(feature_maps["gray"][row_start:row_end])
        gold_mask.extend(feature_maps["gold"][row_start:row_end])
        white_mask.extend(feature_maps["white"][row_start:row_end])

    gray_mean = sum(gray_values) / len(gray_values)
    gray_centered = [value - gray_mean for value in gray_values]
    gray_norm = math.sqrt(sum(value * value for value in gray_centered))

    return {
        "width": width,
        "height": height,
        "gray": gray_centered,
        "gray_norm": gray_norm,
        "gold": gold_mask,
        "gold_count": sum(gold_mask),
        "white": white_mask,
        "white_count": sum(white_mask),
    }


def _load_template_signature(path: str):
    if not path:
        return None, "拇指模式已启用，但 [thumb].template_path 为空"
    if not os.path.exists(path):
        return None, f"未找到拇指模板: {path}"

    mtime = os.path.getmtime(path)
    if (
        _TEMPLATE_CACHE["path"] == path
        and _TEMPLATE_CACHE["mtime"] == mtime
        and _TEMPLATE_CACHE["signature"] is not None
    ):
        return _TEMPLATE_CACHE["signature"], None

    cgimage = _load_cgimage(path)
    if cgimage is None:
        return None, f"无法读取拇指模板: {path}"

    signature = _build_signature(cgimage)
    if signature is None:
        return None, f"无法解析拇指模板像素: {path}"

    _TEMPLATE_CACHE["path"] = path
    _TEMPLATE_CACHE["mtime"] = mtime
    _TEMPLATE_CACHE["signature"] = signature
    return signature, None


def _cosine_score(values_a, norm_a, values_b, norm_b):
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    dot = sum(a * b for a, b in zip(values_a, values_b))
    cosine = dot / (norm_a * norm_b)
    return max(0.0, min(1.0, (cosine + 1.0) / 2.0))


def _mask_score(mask_a, count_a, mask_b, count_b):
    if count_a <= 0 and count_b <= 0:
        return 1.0
    if count_a <= 0 or count_b <= 0:
        return 0.0

    overlap = sum(1 for a, b in zip(mask_a, mask_b) if a and b)
    if overlap <= 0:
        return 0.0

    precision = overlap / count_b
    recall = overlap / count_a
    return (2.0 * precision * recall) / (precision + recall)


def _score(template_signature, sample_signature):
    if (
        template_signature["width"] != sample_signature["width"]
        or template_signature["height"] != sample_signature["height"]
    ):
        return 0.0, {
            "gray": 0.0,
            "gold": 0.0,
            "white": 0.0,
        }

    gray_score = _cosine_score(
        template_signature["gray"],
        template_signature["gray_norm"],
        sample_signature["gray"],
        sample_signature["gray_norm"],
    )
    gold_score = _mask_score(
        template_signature["gold"],
        template_signature["gold_count"],
        sample_signature["gold"],
        sample_signature["gold_count"],
    )
    white_score = _mask_score(
        template_signature["white"],
        template_signature["white_count"],
        sample_signature["white"],
        sample_signature["white_count"],
    )

    # 白色手型比金色底板更能区分“真拇指”和金色背景干扰
    final_score = gray_score * 0.35 + gold_score * 0.15 + white_score * 0.50
    return final_score, {
        "gray": gray_score,
        "gold": gold_score,
        "white": white_score,
    }


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


def _best_match(template_signature, cgimage):
    feature_maps = _extract_feature_maps(cgimage)
    if feature_maps is None:
        return 0.0, {"gray": 0.0, "gold": 0.0, "white": 0.0}, (0, 0), (0, 0)

    crop_width = template_signature["width"]
    crop_height = template_signature["height"]
    max_left = feature_maps["width"] - crop_width
    max_top = feature_maps["height"] - crop_height
    if max_left < 0 or max_top < 0:
        return 0.0, {"gray": 0.0, "gold": 0.0, "white": 0.0}, (0, 0), (0, 0)

    best_score = -1.0
    best_parts = {"gray": 0.0, "gold": 0.0, "white": 0.0}
    best_offset = (0, 0)

    for top in range(max_top + 1):
        for left in range(max_left + 1):
            sample_signature = _signature_from_maps(
                feature_maps, left, top, crop_width, crop_height
            )
            if sample_signature is None:
                continue

            score, parts = _score(template_signature, sample_signature)
            if score > best_score:
                best_score = score
                best_parts = parts
                best_offset = (left, top)

    if best_score < 0.0:
        return 0.0, {"gray": 0.0, "gold": 0.0, "white": 0.0}, (0, 0), (max_left, max_top)
    return best_score, best_parts, best_offset, (max_left, max_top)


def _is_edge_offset(offset, max_offset, tolerance: int):
    max_left, max_top = max_offset
    left, top = offset
    return (
        left <= tolerance
        or top <= tolerance
        or left >= max_left - tolerance
        or top >= max_top - tolerance
    )


def recognize(config: dict, target_window=None):
    """识别 5 个卡槽是否带拇指标记，返回 (slots, raw_items, warning)。"""
    regions, warning = _resolve_regions(config, target_window)
    if warning:
        return _empty_slots(), [], warning

    template_path = _resolve_template_path(config)
    template_signature, warning = _load_template_signature(template_path)
    if warning:
        return _empty_slots(), [], warning

    threshold = float(config.get("thumb", {}).get("threshold", DEFAULT_THRESHOLD) or DEFAULT_THRESHOLD)
    threshold = max(0.0, min(1.0, threshold))
    min_white_score = float(
        config.get("thumb", {}).get("min_white_score", DEFAULT_MIN_WHITE_SCORE)
        or DEFAULT_MIN_WHITE_SCORE
    )
    min_white_score = max(0.0, min(1.0, min_white_score))
    min_gray_score = float(
        config.get("thumb", {}).get("min_gray_score", DEFAULT_MIN_GRAY_SCORE)
        or DEFAULT_MIN_GRAY_SCORE
    )
    min_gray_score = max(0.0, min(1.0, min_gray_score))
    search_padding = max(
        0,
        int(
            config.get("thumb", {}).get(
                "search_padding", DEFAULT_SEARCH_PADDING
            )
            or DEFAULT_SEARCH_PADDING
        ),
    )
    edge_tolerance = max(
        0,
        int(
            config.get("thumb", {}).get(
                "edge_tolerance", DEFAULT_EDGE_TOLERANCE
            )
            or DEFAULT_EDGE_TOLERANCE
        ),
    )

    slots = _empty_slots()
    raw_items = []

    for idx, region in enumerate(regions):
        cgimage = capture.grab(_expand_region(region, search_padding))
        if cgimage is None:
            raw_items.append(f"slot{idx + 1}: capture_failed")
            continue

        score, parts, offset, max_offset = _best_match(template_signature, cgimage)
        at_edge = _is_edge_offset(offset, max_offset, edge_tolerance)
        white_hit = score >= threshold and parts["white"] >= min_white_score
        gray_fallback_hit = parts["gray"] >= min_gray_score and not at_edge
        has_thumb = white_hit or gray_fallback_hit
        slots[idx]["thumb"] = has_thumb
        slots[idx]["thumb_score"] = score
        raw_items.append(
            f"slot{idx + 1}: score={score:.3f}, gray={parts['gray']:.3f}, "
            f"gold={parts['gold']:.3f}, white={parts['white']:.3f}, "
            f"offset=({offset[0]},{offset[1]}), edge={'yes' if at_edge else 'no'}"
        )

    return slots, raw_items, None
