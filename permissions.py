"""macOS 权限检测"""

import ctypes
import ctypes.util

import Quartz


def check_accessibility() -> bool:
    """检测辅助功能权限"""
    lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))
    lib.AXIsProcessTrusted.restype = ctypes.c_bool
    return lib.AXIsProcessTrusted()


def check_screen_recording() -> bool:
    """检测屏幕录制权限（截取 1x1 区域，无权限时返回 None）"""
    img = Quartz.CGWindowListCreateImage(
        Quartz.CGRectMake(0, 0, 1, 1),
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
        Quartz.kCGWindowImageDefault,
    )
    return img is not None and Quartz.CGImageGetWidth(img) > 0


def check_all() -> bool:
    """检测所有权限，缺失时打印引导"""
    ok = True
    if not check_accessibility():
        print("❌ 缺少「辅助功能」权限")
        print("   → 系统设置 → 隐私与安全性 → 辅助功能 → 添加终端/Python")
        ok = False
    if not check_screen_recording():
        print("❌ 缺少「屏幕录制」权限")
        print("   → 系统设置 → 隐私与安全性 → 屏幕录制 → 添加终端/Python")
        ok = False
    if ok:
        print("✅ 权限检测通过")
    return ok
