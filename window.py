"""窗口定位与窗口内 ROI 解算"""

from AppKit import NSRunningApplication
import Quartz

_BUNDLE_CACHE = {}


def _get(info, key, default=None):
    """兼容 PyObjC 返回的 CFDictionary 键访问"""
    if info is None:
        return default
    if key in info:
        return info[key]
    return info.get(str(key), default)


def _normalize_window(info):
    """提取窗口的常用字段"""
    bounds = dict(_get(info, Quartz.kCGWindowBounds, {}) or {})
    width = int(bounds.get("Width", 0) or 0)
    height = int(bounds.get("Height", 0) or 0)
    if width <= 0 or height <= 0:
        return None

    pid = int(_get(info, Quartz.kCGWindowOwnerPID, 0) or 0)
    return {
        "id": int(_get(info, Quartz.kCGWindowNumber, 0) or 0),
        "pid": pid,
        "owner_name": str(_get(info, Quartz.kCGWindowOwnerName, "") or ""),
        "name": str(_get(info, Quartz.kCGWindowName, "") or ""),
        "bundle_id": _bundle_id_for_pid(pid),
        "left": int(bounds.get("X", 0) or 0),
        "top": int(bounds.get("Y", 0) or 0),
        "width": width,
        "height": height,
        "layer": int(_get(info, Quartz.kCGWindowLayer, 0) or 0),
        "alpha": float(_get(info, Quartz.kCGWindowAlpha, 1.0) or 1.0),
        "onscreen": bool(_get(info, Quartz.kCGWindowIsOnscreen, True)),
    }


def _contains_any(text, keywords):
    if not keywords:
        return True
    normalized = text.lower()
    return any(keyword.lower() in normalized for keyword in keywords if keyword)


def _bundle_id_for_pid(pid: int) -> str:
    if pid <= 0:
        return ""
    cached = _BUNDLE_CACHE.get(pid)
    if cached is not None:
        return cached

    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    bundle_id = ""
    if app is not None:
        bundle_id = str(app.bundleIdentifier() or "")

    _BUNDLE_CACHE[pid] = bundle_id
    return bundle_id


def _owner_keywords(window_cfg):
    keywords = list(window_cfg.get("owner_keywords", []) or [])
    owner_name = str(window_cfg.get("owner_name", "") or "").strip()
    if owner_name:
        keywords.insert(0, owner_name)
    return [keyword for keyword in keywords if keyword]


def find_window(window_cfg: dict):
    """查找目标窗口，优先返回面积最大的匹配结果"""
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID
    )
    if not windows:
        return None

    bundle_id = str(window_cfg.get("bundle_id", "") or "").strip()
    owner_keywords = _owner_keywords(window_cfg)
    title_keywords = list(window_cfg.get("title_keywords", []) or [])
    require_title = bool(window_cfg.get("require_title_match", False))
    if not bundle_id and not owner_keywords and not title_keywords:
        return None

    candidates = []
    for raw in windows:
        info = _normalize_window(raw)
        if info is None:
            continue
        if not info["onscreen"] or info["alpha"] <= 0:
            continue
        if info["layer"] != 0:
            continue
        if bundle_id and info["bundle_id"] != bundle_id:
            continue
        if not _contains_any(info["owner_name"], owner_keywords):
            continue
        if require_title and not _contains_any(info["name"], title_keywords):
            continue
        if title_keywords and not require_title:
            if not _contains_any(info["name"], title_keywords):
                info["title_match"] = False
            else:
                info["title_match"] = True
        else:
            info["title_match"] = True
        candidates.append(info)

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            item["title_match"],
            item["width"] * item["height"],
            item["alpha"],
        ),
        reverse=True,
    )
    return candidates[0]


def resolve_geometry(config: dict):
    """返回 (roi, click_y, window_info, scale_x, scale_y)"""
    roi = dict(config["roi"])
    click_y = int(config.get("click_y", roi.get("click_y", 0)) or 0)
    window_cfg = config.get("window", {})

    if not window_cfg.get("enabled", False):
        return roi, click_y, None, 1.0, 1.0

    target = find_window(window_cfg)
    if target is None:
        return None, click_y, None, 1.0, 1.0

    ref_width = int(window_cfg.get("reference_width", 0) or 0)
    ref_height = int(window_cfg.get("reference_height", 0) or 0)
    scale_with_window = bool(window_cfg.get("scale_with_window", False))
    scale_x = target["width"] / ref_width if scale_with_window and ref_width > 0 else 1.0
    scale_y = target["height"] / ref_height if scale_with_window and ref_height > 0 else 1.0
    target["reference_width"] = ref_width
    target["reference_height"] = ref_height
    target["scale_with_window"] = scale_with_window
    target["size_warning"] = ""
    if not scale_with_window and ref_width > 0 and ref_height > 0:
        if target["width"] != ref_width or target["height"] != ref_height:
            target["size_warning"] = (
                f"窗口尺寸已变为 {target['width']}x{target['height']}，"
                f"参考尺寸是 {ref_width}x{ref_height}"
            )

    resolved_roi = {
        "left": int(round(target["left"] + roi["left"] * scale_x)),
        "top": int(round(target["top"] + roi["top"] * scale_y)),
        "width": max(1, int(round(roi["width"] * scale_x))),
        "height": max(1, int(round(roi["height"] * scale_y))),
    }

    resolved_click_y = 0
    if click_y > 0:
        resolved_click_y = int(round(target["top"] + click_y * scale_y))

    return resolved_roi, resolved_click_y, target, scale_x, scale_y


def resolve_click_targets(config: dict, target_window=None, scale_x=1.0, scale_y=1.0):
    """解算手工标注的点击点位。

    返回 (points, jitter, warning)
    - points: None 或 5 个绝对坐标 [(x, y), ...]
    - jitter: {"x": int, "y": int}
    - warning: 配置无效时的提示文本
    """
    click_cfg = config.get("click", {})
    jitter = {
        "x": max(0, int(round((click_cfg.get("jitter_x", 0) or 0) * scale_x))),
        "y": max(0, int(round((click_cfg.get("jitter_y", 0) or 0) * scale_y))),
    }

    if not click_cfg.get("use_slot_points", False):
        return None, jitter, None

    raw_points = list(click_cfg.get("slot_points", []) or [])
    if len(raw_points) != 5:
        return None, jitter, "手动点击已启用，但 [click].slot_points 不是 5 个点位"

    points = []
    for i, point in enumerate(raw_points):
        if not isinstance(point, dict):
            return None, jitter, f"手动点击点位 slot_points[{i}] 不是合法对象"

        x = int(point.get("x", 0) or 0)
        y = int(point.get("y", 0) or 0)
        if x <= 0 or y <= 0:
            return None, jitter, f"手动点击点位 slot_points[{i}] 未配置有效坐标"

        resolved_x = int(round(x * scale_x))
        resolved_y = int(round(y * scale_y))
        if target_window is not None:
            resolved_x += target_window["left"]
            resolved_y += target_window["top"]

        points.append((resolved_x, resolved_y))

    return points, jitter, None
