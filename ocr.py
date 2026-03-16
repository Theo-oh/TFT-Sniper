"""Vision OCR 模块 — 调用 Apple Vision 框架识别中文文本"""

import re
import unicodedata

import Vision
from Foundation import NSDictionary

UNKNOWN_COST = 0
VALID_COST_DIGITS = "1234567"


def _empty_slots():
    return [{"name": "", "cost": UNKNOWN_COST} for _ in range(5)]


def _normalize_text(text: str) -> str:
    """统一 OCR 文本形态，处理全角/圈号数字等 Unicode 兼容字符"""
    return unicodedata.normalize("NFKC", text).strip()


def _extract_cost(text: str):
    """从 OCR 文本中提取价格。

    金铲铲商店价格固定为 1~7。Vision 常把金币图标误识别成前缀数字，
    例如 "93"、"02"、"51"，这里按领域规则取最右侧的有效价格数字。
    """
    for ch in reversed(text):
        if ch in VALID_COST_DIGITS:
            return int(ch)
    return None


def recognize(cgimage):
    """对 CGImage 执行 OCR，返回 (slots, raw_texts)

    slots:     5 个卡槽 [{"name": str, "cost": int}, ...]
    raw_texts: 原始识别文本列表（调试用）
    """
    if cgimage is None:
        return _empty_slots(), []

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        cgimage, NSDictionary.dictionary()
    )
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLanguages_(["zh-Hans"])
    # 中文必须用 accurate，fast 不支持 CJK
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    # 英雄名是专有名词，语言纠错收益有限，关闭可减少额外开销
    request.setUsesLanguageCorrection_(False)
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
    slots = [{"name": "", "cost": UNKNOWN_COST} for _ in range(5)]

    for item in items:
        idx = min(int(item["cx"] / slot_w), 4)
        text = _normalize_text(item["text"])
        cost = _extract_cost(text)

        if text.isdigit():
            slots[idx]["cost"] = cost if cost is not None else UNKNOWN_COST
        else:
            # 可能是 "英雄名 数字" 混合，价格固定 1~7，因此优先取尾部有效数字
            m = re.match(r"^(.+?)\s*([0-9]+)\s*$", text)
            if m:
                slots[idx]["name"] = m.group(1)
                if cost is not None:
                    slots[idx]["cost"] = cost
            else:
                slots[idx]["name"] = text

    return slots, raw_texts
