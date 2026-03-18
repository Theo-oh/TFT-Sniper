"""匹配逻辑 — 仅按英雄名匹配"""


def match(slots: list, target_heroes: list) -> list:
    """返回命中卡槽索引（从右到左排序，用于点击顺序）

    仅当英雄名命中 target_heroes 时购买。
    """
    if not target_heroes:
        return []

    hits = []
    for i, slot in enumerate(slots):
        if slot.get("name", "") in target_heroes:
            hits.append(i)

    hits.sort(reverse=True)  # 从右到左
    return hits
