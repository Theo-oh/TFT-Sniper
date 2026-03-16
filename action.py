"""鼠标控制模块 — 坐标计算 + 点击购买"""

from pynput.mouse import Button, Controller

_mouse = Controller()


def click_card(slot_idx: int, roi: dict, click_y: int = 0):
    """点击指定卡槽购买

    slot_idx: 卡槽索引 0-4（左到右）
    roi:      截图 ROI（Point 坐标）
    click_y:  购买点击 y 坐标（Point），0 则用 ROI 中心
    """
    card_x = roi["left"] + (slot_idx + 0.5) * roi["width"] / 5
    card_y = click_y if click_y > 0 else roi["top"] + roi["height"] / 2

    original = _mouse.position
    _mouse.position = (card_x, card_y)
    _mouse.click(Button.left, 1)
    _mouse.position = original
