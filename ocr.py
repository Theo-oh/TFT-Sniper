"""Vision OCR 模块 — 调用 Apple Vision 框架识别中文文本"""

import re

import Quartz
import Vision
from Foundation import NSDictionary


def _empty_slots():
    return [{"name": "", "cost": -1} for _ in range(5)]


def recognize(cgimage, level="accurate"):
    """对 CGImage 执行 OCR，返回 (slots, raw_texts)

    slots:     5 个卡槽 [{"name": str, "cost": int}, ...]
    raw_texts: 原始识别文本列表（调试用）
    注意: 中文识别必须用 accurate，fast 模式不支持 CJK
    """
    if cgimage is None:
        return _empty_slots(), []

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        cgimage, NSDictionary.dictionary()
    )
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLanguages_(["zh-Hans", "zh-Hant", "en-US"])
    # 中文必须用 accurate，fast 不支持 CJK
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    # 小文字适配（归一化高度比例，0.0 ~ 1.0）
    request.setMinimumTextHeight_(0.01)

    success, error = handler.performRequests_error_([request], None)
    if not success:
        return _empty_slots(), []

    observations = request.results()
    if not observations:
        return _empty_slots(), []

    return _parse(observations)


def _parse(observations):
    """按 boundingBox.x 分配到 5 个卡槽，区分英雄名和价格"""
    raw_texts = []
    items = []

    for obs in observations:
        candidates = obs.topCandidates_(1)
        if not candidates or candidates.count() == 0:
            continue

        text = candidates[0].string().strip()
        confidence = candidates[0].confidence()
        bbox = obs.boundingBox()
        cx = bbox.origin.x + bbox.size.width / 2

        raw_texts.append(f"{text} (x={cx:.3f}, conf={confidence:.2f})")
        items.append({"text": text, "cx": cx, "confidence": confidence})

    # 按 x 均分到 5 个卡槽
    slot_w = 1.0 / 5
    slots = [{"name": "", "cost": -1} for _ in range(5)]

    for item in items:
        idx = min(int(item["cx"] / slot_w), 4)
        text = item["text"]

        if text.isdigit():
            slots[idx]["cost"] = int(text)
        else:
            # 可能是 "英雄名 数字" 混合
            m = re.match(r"^(.+?)\s*(\d+)\s*$", text)
            if m:
                slots[idx]["name"] = m.group(1)
                slots[idx]["cost"] = int(m.group(2))
            else:
                slots[idx]["name"] = text

    return slots, raw_texts
