"""截图模块 — 直接使用 Quartz，返回 CGImage，零格式转换"""

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


def save(cgimage, path: str):
    """保存 CGImage 为 PNG（调试用）"""
    url = NSURL.fileURLWithPath_(path)
    dest = Quartz.CGImageDestinationCreateWithURL(url, "public.png", 1, None)
    if dest:
        Quartz.CGImageDestinationAddImage(dest, cgimage, None)
        Quartz.CGImageDestinationFinalize(dest)
