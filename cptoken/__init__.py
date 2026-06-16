import base64
import random
import struct
import time
from loguru import logger


def generate_ctoken(
    m1: int = -1,
    touchend: int = -1,
    m2: int = -1,
    visibilitychange: int = -1,
    m3: int = -1,
    m4: int = -1,
    openWindow: int = -1,
    m5: int = -1,
    timer: int = -1,
    timediff: float = 0,
    m6: int = -1,
    m7: int = -1,
    m8: int = -1,
    m9: int = -1,
) -> str:
    def js_uint8(value: int | float) -> int:
        v = int(float(value))
        if v > 255:
            v = 255
        return v & 0xFF

    def js_uint16(value: int | float) -> int:
        v = int(float(value))
        if v > 65535:
            v = 65535
        return v & 0xFFFF

    semantic_bytes = struct.pack(
        ">8B2H4B",
        js_uint8(m1),  # 0
        js_uint8(touchend),  # 1
        js_uint8(m2),  # 2
        js_uint8(visibilitychange),  # 3
        js_uint8(m3),  # 4
        js_uint8(m4),  # 5
        js_uint8(openWindow),  # 6
        js_uint8(m5),  # 7
        js_uint16(timer),  # 8-9
        js_uint16(timediff),  # 10-11
        js_uint8(m6),  # 12
        js_uint8(m7),  # 13
        js_uint8(m8),  # 14
        js_uint8(m9),  # 15
    )
    transport_bytes = semantic_bytes.decode("latin1").encode("utf-16le")
    return base64.b64encode(transport_bytes).decode("utf-8")


def init_ctoken_state(
    scroll_x: int = 0,
    scroll_y: int = 0,
    inner_width: int = random.randint(1000, 3000),
    inner_height: int = random.randint(1000, 3000),
    outer_width: int = random.randint(1000, 3000),
    outer_height: int = random.randint(1000, 3000),
    screen_x: int = 0,
    screen_y: int = 0,
    screen_width: int = random.randint(1000, 3000),
    screen_height: int = random.randint(1000, 3000),
    screen_avail_width: int = random.randint(1, 100),
    history_length: int = random.randint(2, 10),
    user_agent_length: int = 140,
    href_length: int = 140,
    device_pixel_ratio: float = 1.0,
) -> dict[str, int]:
    def derive_d(index: int) -> int:
        now_mod_256 = int(time.time() * 1000) % 256
        values = [
            scroll_x,
            scroll_y,
            inner_width,
            inner_height,
            outer_width,
            outer_height,
            screen_x,
            screen_y,
            screen_width,
            screen_height,
            screen_avail_width,
            history_length,
            user_agent_length,
            href_length,
            round(10 * (device_pixel_ratio or 1)),
            now_mod_256,
        ]
        return (values[index % 16] + values[(3 * index) % 16] + 17 * index) & 255

    touchend = 0
    visibilitychange = 0
    open_window = 1

    ret = {
        "m1": derive_d(1),
        "touchend": touchend,
        "m2": derive_d(2),
        "visibilitychange": visibilitychange,
        "m3": derive_d(3),
        "m4": derive_d(4),
        "openWindow": open_window,
        "m5": derive_d(5),
        "timer": random.randint(10, 100),
        "timediff": 0,
        "m6": derive_d(6),
        "m7": derive_d(7),
        "m8": derive_d(8),
        "m9": derive_d(9),
    }
    logger.info(ret)
    return ret


def sim_ctoken_state(
    before_state: dict[str, int],
    ticket_collection_t: int,
    now_ms: int | None = None,
    base_timer: int = 0,
    add_action: bool = True,
) -> dict[str, int]:
    # randome update timer,touchend,visibilitychange,openWindow
    if add_action:
        touchend_add = random.choice([0, 0, 1, 2])
        open_window_add = random.choices([0, 0, 1], weights=[60, 20, 20], k=1)[0]
        visibilitychange_add = random.choices([0, 0, 1], weights=[60, 20, 20], k=1)[0]
    else:
        touchend_add = 0
        open_window_add = 0
        visibilitychange_add = 0
    ret = {
        "m1": before_state["m1"],
        "touchend": before_state["touchend"] + touchend_add,
        "m2": before_state["m2"],
        "visibilitychange": before_state["visibilitychange"] + visibilitychange_add,
        "m3": before_state["m3"],
        "m4": before_state["m4"],
        "openWindow": before_state["openWindow"] + open_window_add,
        "m5": before_state["m5"],
        "timer": base_timer + int((now_ms - ticket_collection_t) / 1000),
        "timediff": (now_ms - ticket_collection_t)
        / 1000,  # payload.timestamp-ticket_collection_t
        "m6": before_state["m6"],
        "m7": before_state["m7"],
        "m8": before_state["m8"],
        "m9": before_state["m9"],
    }
    logger.info(ret)
    return ret


__all__ = [
    "generate_ctoken",
    "init_ctoken_state",
    "sim_ctoken_state",
]
