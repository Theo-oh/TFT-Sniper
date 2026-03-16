"""鼠标控制模块 — 坐标计算 + 点击购买"""

import random
import time

from pynput.mouse import Button, Controller

_mouse = Controller()


def _sleep_ms(delay_ms: int, jitter_ms: int = 0):
    if delay_ms <= 0 and jitter_ms <= 0:
        return
    actual_ms = delay_ms
    if jitter_ms > 0:
        actual_ms += random.randint(-jitter_ms, jitter_ms)
    if actual_ms > 0:
        time.sleep(actual_ms / 1000)


def _resolve_card_point(
    slot_idx: int,
    roi: dict,
    click_y: int = 0,
    click_point=None,
    jitter_x: int = 0,
    jitter_y: int = 0,
):
    """计算指定卡槽的点击坐标。"""
    if click_point is not None:
        card_x, card_y = click_point
    else:
        card_x = roi["left"] + (slot_idx + 0.5) * roi["width"] / 5
        card_y = click_y if click_y > 0 else roi["top"] + roi["height"] / 2

    if jitter_x > 0:
        card_x += random.randint(-jitter_x, jitter_x)
    if jitter_y > 0:
        card_y += random.randint(-jitter_y, jitter_y)

    return int(round(card_x)), int(round(card_y))


def _click_at(
    card_x: int,
    card_y: int,
    move_settle_ms: int,
    hold_ms: int,
    timing_jitter_ms: int,
):
    _mouse.position = (card_x, card_y)
    _sleep_ms(move_settle_ms, timing_jitter_ms)
    _mouse.press(Button.left)
    _sleep_ms(hold_ms, timing_jitter_ms)
    _mouse.release(Button.left)


def click_cards(
    hits: list,
    roi: dict,
    click_y: int = 0,
    click_points=None,
    jitter_x: int = 0,
    jitter_y: int = 0,
    move_settle_ms: int = 16,
    hold_ms: int = 18,
    inter_click_ms: int = 70,
    post_batch_ms: int = 18,
    timing_jitter_ms: int = 4,
):
    """批量点击多个卡槽，优先保证多张连买稳定注册。"""
    if not hits:
        return

    targets = []
    for idx in hits:
        click_point = click_points[idx] if click_points else None
        targets.append(
            _resolve_card_point(
                idx,
                roi,
                click_y=click_y,
                click_point=click_point,
                jitter_x=jitter_x,
                jitter_y=jitter_y,
            )
        )

    original = _mouse.position
    for i, (card_x, card_y) in enumerate(targets):
        _click_at(card_x, card_y, move_settle_ms, hold_ms, timing_jitter_ms)
        if i < len(targets) - 1:
            _sleep_ms(inter_click_ms, timing_jitter_ms)

    _sleep_ms(post_batch_ms, timing_jitter_ms)
    _mouse.position = original
