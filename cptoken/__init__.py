import base64
import random
import struct
import time


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
    ticket_collection_t: int = 0,
    m6: int = -1,
    m7: int = -1,
    m8: int = -1,
    m9: int = -1,
) -> str:
    def normalize_int(value: object) -> int:
        if value is None:
            return 0
        return int(value)

    def clamp8(value: object) -> int:
        normalized = normalize_int(value)
        return 255 if normalized > 255 else max(0, normalized)

    def clamp16(value: object) -> int:
        normalized = normalize_int(value)
        return 65535 if normalized > 65535 else max(0, normalized)

    semantic_bytes = struct.pack(
        ">8B2H4B",
        clamp8(m1),
        clamp8(touchend),
        clamp8(m2),
        clamp8(visibilitychange),
        clamp8(m3),
        clamp8(m4),
        clamp8(openWindow),
        clamp8(m5),
        clamp16(timer),
        clamp16(ticket_collection_t),
        clamp8(m6),
        clamp8(m7),
        clamp8(m8),
        clamp8(m9),
    )

    transport_bytes = bytearray()
    for value in semantic_bytes:
        transport_bytes.extend((value, 0))

    return base64.b64encode(bytes(transport_bytes)).decode("utf-8")


def init_ctoken_state(
    *,
    scroll_x: int = 0,
    scroll_y: int = 0,
    inner_width: int = 1280,
    inner_height: int = 720,
    outer_width: int = 1280,
    outer_height: int = 800,
    screen_x: int = 0,
    screen_y: int = 0,
    screen_width: int = 1920,
    screen_height: int = 1080,
    screen_avail_width: int = 1920,
    history_length: int = 2,
    user_agent_length: int = 111,
    href_length: int = 80,
    device_pixel_ratio: float = 1.0,
    random_events: bool = True,
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

    if random_events:
        touchend = random.randint(0, 5)
        visibilitychange = random.randint(0, 1)
        open_window = random.randint(0, 1)
        timer = random.randint(1, 10)
        elapsed_seconds = timer
    else:
        touchend = 0
        visibilitychange = 0
        open_window = 0
        timer = 0
        elapsed_seconds = 0

    return {
        "m1": derive_d(1),
        "touchend": touchend,
        "m2": derive_d(2),
        "visibilitychange": visibilitychange,
        "m3": derive_d(3),
        "m4": derive_d(4),
        "openWindow": open_window,
        "m5": derive_d(5),
        "timer": timer,
        "ticket_collection_t": elapsed_seconds,
        "m6": derive_d(6),
        "m7": derive_d(7),
        "m8": derive_d(8),
        "m9": derive_d(9),
    }


def sim_ctoken_state(before_state: dict[str, int], started_ms: int) -> dict[str, int]:
    now_ms = int(time.time() * 1000)
    elapsed_seconds = max(0, int((now_ms - started_ms) / 1000))
    timer_add = random.choice([0, 0, 0, 1])
    touchend_add = random.choice([0, 0, 1, 2])
    open_window_add = random.choices([0, 0, 1], weights=[60, 20, 20], k=1)[0]
    visibilitychange_add = random.choices([0, 0, 1], weights=[60, 20, 20], k=1)[0]
    return {
        "m1": before_state["m1"],
        "touchend": before_state["touchend"] + touchend_add,
        "m2": before_state["m2"],
        "visibilitychange": before_state["visibilitychange"] + visibilitychange_add,
        "m3": before_state["m3"],
        "m4": before_state["m4"],
        "openWindow": before_state["openWindow"] + open_window_add,
        "m5": before_state["m5"],
        "timer": before_state["timer"] + timer_add,
        "ticket_collection_t": elapsed_seconds,
        "m6": before_state["m6"],
        "m7": before_state["m7"],
        "m8": before_state["m8"],
        "m9": before_state["m9"],
    }


__all__ = [
    "generate_ctoken",
    "init_ctoken_state",
    "sim_ctoken_state",
]
