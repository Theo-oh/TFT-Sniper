"""匹配逻辑 — 名字/价格 OR 匹配"""


def match(slots: list, target_heroes: list, target_costs: list) -> list:
    """返回命中卡槽索引（从右到左排序，用于点击顺序）

    OR 逻辑：名字命中 或 价格命中，即购买。
    两项可单独配置或同时配置，空列表表示不启用该匹配维度。
    """
    hits = []
    for i, slot in enumerate(slots):
        if not slot["name"] and slot["cost"] <= 0:
            continue

        name_hit = bool(target_heroes) and slot["name"] in target_heroes
        cost_hit = bool(target_costs) and slot["cost"] in target_costs

        if name_hit or cost_hit:
            hits.append(i)

    hits.sort(reverse=True)  # 从右到左
    return hits
