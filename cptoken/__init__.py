import base64
from dataclasses import asdict, dataclass, field
import logging
import random
import struct
import time
from typing import TypedDict

try:
    from loguru import logger
except ImportError:  # pragma: no cover - test/runtime fallback
    logger = logging.getLogger(__name__)  # type:ignore


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
    def _js_uint8(value: int | float) -> int:
        v = int(float(value))
        if v > 255:
            v = 255
        return v & 0xFF

    def _js_uint16(value: int | float) -> int:
        v = int(float(value))
        if v > 65535:
            v = 65535
        return v & 0xFFFF

    semantic_bytes = struct.pack(
        ">8B2H4B",
        _js_uint8(m1),
        _js_uint8(touchend),
        _js_uint8(m2),
        _js_uint8(visibilitychange),
        _js_uint8(m3),
        _js_uint8(m4),
        _js_uint8(openWindow),
        _js_uint8(m5),
        _js_uint16(timer),
        _js_uint16(timediff),
        _js_uint8(m6),
        _js_uint8(m7),
        _js_uint8(m8),
        _js_uint8(m9),
    )
    transport_bytes = semantic_bytes.decode("latin1").encode("utf-16le")
    return base64.b64encode(transport_bytes).decode("utf-8")


@dataclass(slots=True)
class CTokenSnapshot:
    m1: int
    touchend: int
    m2: int
    visibilitychange: int
    m3: int
    m4: int
    openWindow: int
    m5: int
    timer: int
    timediff: float
    m6: int
    m7: int
    m8: int
    m9: int
    base_timer: int = 0

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)

    def kwargs(self) -> dict[str, int | float]:
        return {
            "m1": self.m1,
            "touchend": self.touchend,
            "m2": self.m2,
            "visibilitychange": self.visibilitychange,
            "m3": self.m3,
            "m4": self.m4,
            "openWindow": self.openWindow,
            "m5": self.m5,
            "timer": self.timer,
            "timediff": self.timediff,
            "m6": self.m6,
            "m7": self.m7,
            "m8": self.m8,
            "m9": self.m9,
        }

    def generate_ctoken(self) -> str:
        return self.generate_prepare_ctoken()

    def generate_prepare_ctoken(self) -> str:
        return generate_ctoken(**self.kwargs())  # type:ignore

    def generate_create_ctoken(self) -> str:
        return generate_ctoken(**self.kwargs())  # type:ignore


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
    common_screens = [
        (375, 667),
        (414, 896),
        (412, 715),
        (820, 1180),
        (375, 667),
        (390, 844),
        (360, 740),
    ]

    if screen_width is None or screen_height is None:
        screen_width, screen_height = random.choice(common_screens)

    taskbar_height = random.choice([40, 48, 56, 64])
    screen_avail_width = screen_width
    screen_avail_height = screen_height - taskbar_height

    if maximized is None:
        maximized = random.random() < 0.65

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


@dataclass(slots=True)
class CTokenRuntimeState:
    m1: int
    touchend: int
    m2: int
    visibilitychange: int
    m3: int
    m4: int
    openWindow: int
    m5: int
    m6: int
    m7: int
    m8: int
    m9: int
    ticket_collection_t: int = 0
    base_timer: int = field(default_factory=lambda: random.randint(10, 100))
    base_timediff: float = 0
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def snapshot(self, now_ms: int | None = None) -> CTokenSnapshot:
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        elapsed_seconds = max(0.0, (now_ms - self.created_at_ms) / 1000)
        timediff = self.base_timediff
        if self.ticket_collection_t > 0:
            timediff += max(0.0, (now_ms - self.ticket_collection_t) / 1000)
        return CTokenSnapshot(
            m1=self.m1,
            touchend=self.touchend,
            m2=self.m2,
            visibilitychange=self.visibilitychange,
            m3=self.m3,
            m4=self.m4,
            openWindow=self.openWindow,
            m5=self.m5,
            timer=self.base_timer + int(elapsed_seconds),
            timediff=timediff,
            m6=self.m6,
            m7=self.m7,
            m8=self.m8,
            m9=self.m9,
            base_timer=self.base_timer,
        )

    def kwargs(self, now_ms: int | None = None) -> dict[str, int | float]:
        return self.snapshot(now_ms=now_ms).kwargs()


def init_ctoken_state(
    browser_window_state: BrowserWindowState | None = None,
    history_length: int = random.randint(2, 10),
    user_agent_length: int = 140,
    href_length: int = 76,
    device_pixel_ratio: float = 4.0,
    ticket_collection_t: int = 0,
) -> CTokenRuntimeState:
    if browser_window_state is None:
        browser_window_state = generate_browser_window_state()

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

    state = CTokenRuntimeState(
        m1=derive_d(1),
        touchend=0,
        m2=derive_d(2),
        visibilitychange=0,
        m3=derive_d(3),
        m4=derive_d(4),
        openWindow=random.randint(1, 3),
        m5=derive_d(5),
        m6=derive_d(6),
        m7=derive_d(7),
        m8=derive_d(8),
        m9=derive_d(9),
        ticket_collection_t=ticket_collection_t,
        created_at_ms=ticket_collection_t or int(time.time() * 1000),
    )
    logger.info(state.snapshot().to_dict())
    return state


def sim_ctoken_state(
    before_state: CTokenRuntimeState,
    now_ms: int | None = None,
) -> CTokenSnapshot:
    if now_ms is None:
        now_ms = int(time.time() * 1000)

    source = before_state.snapshot(now_ms=before_state.created_at_ms)
    ticket_collection_t = before_state.ticket_collection_t
    base_timer = source.base_timer or source.timer
    touchend_add = random.choice([0, 0, 1, 2])
    open_window_add = random.choices([0, 0, 1], weights=[60, 20, 20], k=1)[0]
    visibilitychange_add = random.choices([0, 0, 1], weights=[60, 20, 20], k=1)[0]

    snapshot = CTokenSnapshot(
        m1=source.m1,
        touchend=source.touchend + touchend_add,
        m2=source.m2,
        visibilitychange=source.visibilitychange + visibilitychange_add,
        m3=source.m3,
        m4=source.m4,
        openWindow=source.openWindow + open_window_add,
        m5=source.m5,
        timer=base_timer + int((now_ms - ticket_collection_t) / 1000),
        timediff=max(0.0, (now_ms - ticket_collection_t) / 1000),
        m6=source.m6,
        m7=source.m7,
        m8=source.m8,
        m9=source.m9,
        base_timer=base_timer,
    )
    return snapshot


__all__ = [
    "CTokenRuntimeState",
    "CTokenSnapshot",
    "generate_ctoken",
    "generate_browser_window_state",
    "init_ctoken_state",
    "sim_ctoken_state",
]
