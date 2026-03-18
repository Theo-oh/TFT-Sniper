"""Vision OCR 模块 — 调用 Apple Vision 框架识别中文文本"""

import re
import unicodedata

import Vision
from Foundation import NSDictionary

SLOT_COUNT = 5


def _empty_slots():
    return [{"name": ""} for _ in range(SLOT_COUNT)]


def _normalize_text(text: str) -> str:
    """统一 OCR 文本形态，处理全角/圈号数字等 Unicode 兼容字符"""
    return unicodedata.normalize("NFKC", text).strip()


def _recognize_items(cgimage, languages, min_text_height: float):
    """对给定图像执行 OCR，返回 [{text, confidence, cx}, ...]。"""
    if cgimage is None:
        return []

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        cgimage, NSDictionary.dictionary()
    )
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLanguages_(languages)
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(False)
    request.setMinimumTextHeight_(min_text_height)

    success, error = handler.performRequests_error_([request], None)
    if not success or error is not None:
        return []

    items = []
    for obs in request.results() or []:
        candidates = obs.topCandidates_(1)
        if not candidates or candidates.count() == 0:
            continue

        text = str(candidates[0].string() or "").strip()
        if not text:
            continue

        items.append(
            {
                "text": text,
                "confidence": float(candidates[0].confidence()),
                "cx": float(obs.boundingBox().origin.x + obs.boundingBox().size.width / 2),
            }
        )
    return items


def _cjk_count(text: str) -> int:
    """统计文本里的 CJK 汉字数量。"""
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def _extract_name(text: str) -> str:
    """去掉 OCR 末尾可能粘上的价格数字，只保留英雄名。"""
    text = _normalize_text(text)
    if text.isdigit():
        return ""
    text = re.sub(r"\s*[0-9]+\s*$", "", text).strip()
    if _cjk_count(text) <= 0:
        return ""
    return text


def _name_score(name: str, confidence: float):
    """给候选英雄名打分，优先保留更像名字的结果。"""
    return (_cjk_count(name), len(name), confidence)


def recognize(cgimage):
    """对 CGImage 执行 OCR，返回 (slots, raw_texts)

    slots:     5 个卡槽 [{"name": str}, ...]
    raw_texts: 原始识别文本列表（调试用）
    """
    if cgimage is None:
        return _empty_slots(), []

    items = _recognize_items(cgimage, ["zh-Hans"], 0.01)
    if not items:
        return _empty_slots(), []

    return _parse(items)


def _parse(items):
    """按 boundingBox.x 分配到 5 个卡槽，仅保留英雄名"""
    raw_texts = []

    # 按 x 均分到 5 个卡槽
    slot_w = 1.0 / SLOT_COUNT
    slots = [{"name": ""} for _ in range(SLOT_COUNT)]
    slot_scores = [(-1, -1, -1.0) for _ in range(SLOT_COUNT)]

    for item in items:
        text = item["text"]
        confidence = item["confidence"]
        cx = item["cx"]
        raw_texts.append(f"{text} (x={cx:.3f}, conf={confidence:.2f})")

        name = _extract_name(text)
        if not name:
            continue

        idx = min(int(item["cx"] / slot_w), SLOT_COUNT - 1)
        score = _name_score(name, confidence)
        if score >= slot_scores[idx]:
            slots[idx]["name"] = name
            slot_scores[idx] = score

    return slots, raw_texts
