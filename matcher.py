"""匹配逻辑 — 支持英雄名或拇指标记"""


def match(slots: list, target_heroes: list, mode: str = "name") -> list:
    """返回命中卡槽索引（从右到左排序，用于点击顺序）

    - mode=name: 仅当英雄名命中 target_heroes 时购买
    - mode=thumb: 仅当卡槽识别到拇指标记时购买
    """
    hits = []
    if mode == "thumb":
        for i, slot in enumerate(slots):
            if slot.get("thumb", False):
                hits.append(i)
    else:
        if not target_heroes:
            return []

        for i, slot in enumerate(slots):
            if slot.get("name", "") in target_heroes:
                hits.append(i)

    hits.sort(reverse=True)  # 从右到左
    return hits
