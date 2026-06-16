import base64
import random
import struct
import time
from typing import TypedDict
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


class BrowserWindowState(TypedDict):
    scrollX: int
    scrollY: int
    innerWidth: int
    innerHeight: int
    outerWidth: int
    outerHeight: int
    screenX: int
    screenY: int
    screenWidth: int
    screenHeight: int
    screenAvailWidth: int
    screenAvailHeight: int


def generate_browser_window_state(
    *,
    screen_width: int | None = None,
    screen_height: int | None = None,
    maximized: bool | None = None,
    scroll: bool = False,
) -> BrowserWindowState:
    """
    生成一组自洽的浏览器窗口尺寸参数。

    对应 JS 字段：
    - window.scrollX
    - window.scrollY
    - window.innerWidth
    - window.innerHeight
    - window.outerWidth
    - window.outerHeight
    - window.screenX
    - window.screenY
    - window.screen.width
    - window.screen.height
    - window.screen.availWidth
    - window.screen.availHeight
    """

    # 常见桌面分辨率
    common_screens = [
        (1920, 1080),
        (2560, 1440),
        (1366, 768),
        (1440, 900),
        (1536, 864),
        (1600, 900),
        (1280, 720),
    ]

    if screen_width is None or screen_height is None:
        screen_width, screen_height = random.choice(common_screens)

    # 任务栏 / Dock 占用高度
    taskbar_height = random.choice([40, 48, 56, 64])
    screen_avail_width = screen_width
    screen_avail_height = screen_height - taskbar_height

    if maximized is None:
        maximized = random.random() < 0.65

    # 浏览器外框与内容区的差值
    # Chrome/Edge/Firefox 桌面端大概会有顶部工具栏、标签栏、边框等
    chrome_width_delta = random.choice([0, 8, 12, 16])
    chrome_height_delta = random.choice([80, 88, 96, 104, 112, 120])

    if maximized:
        outer_width = screen_avail_width
        outer_height = screen_avail_height

        screen_x = 0
        screen_y = 0

        inner_width = outer_width - chrome_width_delta
        inner_height = outer_height - chrome_height_delta

    else:
        # 非最大化窗口，一般占屏幕的 60% ~ 90%
        outer_width = random.randint(
            int(screen_avail_width * 0.60),
            int(screen_avail_width * 0.90),
        )
        outer_height = random.randint(
            int(screen_avail_height * 0.60),
            int(screen_avail_height * 0.90),
        )

        max_x = max(0, screen_avail_width - outer_width)
        max_y = max(0, screen_avail_height - outer_height)

        screen_x = random.randint(0, max_x)
        screen_y = random.randint(0, max_y)

        inner_width = outer_width - chrome_width_delta
        inner_height = outer_height - chrome_height_delta

    # 防止极端小值
    inner_width = max(320, inner_width)
    inner_height = max(240, inner_height)

    if scroll:
        scroll_x = random.choice([0, 0, 0, random.randint(1, 200)])
        scroll_y = random.choice([0, random.randint(50, 2000)])
    else:
        scroll_x = 0
        scroll_y = 0

    return {
        "scrollX": scroll_x,
        "scrollY": scroll_y,
        "innerWidth": inner_width,
        "innerHeight": inner_height,
        "outerWidth": outer_width,
        "outerHeight": outer_height,
        "screenX": screen_x,
        "screenY": screen_y,
        "screenWidth": screen_width,
        "screenHeight": screen_height,
        "screenAvailWidth": screen_avail_width,
        "screenAvailHeight": screen_avail_height,
    }


def init_ctoken_state(
    ## BrowserWindowState
    browser_window_state: BrowserWindowState | None = generate_browser_window_state(),
    ## Other
    history_length: int = random.randint(2, 10),
    user_agent_length: int = 140,
    href_length: int = 76,
    device_pixel_ratio: float = 4.0,
) -> dict[str, int]:
    def derive_d(index: int) -> int:
        now_mod_256 = int(time.time() * 1000) % 256
        values = [
            browser_window_state["scrollX"],
            browser_window_state["scrollY"],
            browser_window_state["innerWidth"],
            browser_window_state["innerHeight"],
            browser_window_state["outerWidth"],
            browser_window_state["outerHeight"],
            browser_window_state["screenX"],
            browser_window_state["screenY"],
            browser_window_state["screenWidth"],
            browser_window_state["screenHeight"],
            browser_window_state["screenAvailWidth"],
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
