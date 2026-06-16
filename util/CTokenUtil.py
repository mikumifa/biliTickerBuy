import base64
from dataclasses import asdict, dataclass, field
import random
import struct
import time
from typing import TypedDict
from loguru import logger

from util.TimeUtil import current_time_ms


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

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)

    def kwargs(self) -> dict[str, int | float]:
        return self.to_dict()

    @staticmethod
    def _js_uint8(value: int | float) -> int:
        v = int(float(value))
        if v > 255:
            v = 255
        return v & 0xFF

    @staticmethod
    def _js_uint16(value: int | float) -> int:
        v = int(float(value))
        if v > 65535:
            v = 65535
        return v & 0xFFFF

    def generate_ctoken(self) -> str:
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
            js_uint8(self.m1),  # 0
            js_uint8(self.touchend),  # 1
            js_uint8(self.m2),  # 2
            js_uint8(self.visibilitychange),  # 3
            js_uint8(self.m3),  # 4
            js_uint8(self.m4),  # 5
            js_uint8(self.openWindow),  # 6
            js_uint8(self.m5),  # 7
            js_uint16(self.timer),  # 8-9
            js_uint16(self.timediff),  # 10-11
            js_uint8(self.m6),  # 12
            js_uint8(self.m7),  # 13
            js_uint8(self.m8),  # 14
            js_uint8(self.m9),  # 15
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


@dataclass(slots=True)
class CTokenRuntimeState:
    """
    timer / timediff 随时间变化。
    """

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
    base_timer: int = field(default_factory=lambda: random.randint(10, 100))
    base_timediff: float = random.randint(10, 30)
    created_at: float = field(default_factory=time.time)
    timeoffet: float = 0
    ticket_collection_t: int = 0

    def elapsed_seconds(self) -> float:
        return current_time_ms(timeoffset=self.timeoffet) / 1000 - self.created_at

    def current_timer(self) -> int:
        return self.base_timer + int(self.elapsed_seconds())

    def snapshot(self) -> CTokenSnapshot:
        return CTokenSnapshot(
            m1=self.m1,
            touchend=self.touchend,
            m2=self.m2,
            visibilitychange=self.visibilitychange,
            m3=self.m3,
            m4=self.m4,
            openWindow=self.openWindow,
            m5=self.m5,
            timer=self.current_timer(),
            timediff=self.base_timediff
            + int(
                (current_time_ms(timeoffset=self.timeoffet) - self.ticket_collection_t)
                / 1000
            ),
            m6=self.m6,
            m7=self.m7,
            m8=self.m8,
            m9=self.m9,
        )

    def to_dict(self) -> dict[str, int | float]:
        return self.snapshot().to_dict()

    def kwargs(self) -> dict[str, int | float]:
        return self.to_dict()

    def touch(
        self,
        count: int | None = None,
        *,
        min_count: int = 1,
        max_count: int = 5,
    ) -> int:
        if count is not None:
            if count < 0:
                raise ValueError("count 不能小于 0")

            self.touchend += count
            return count

        if min_count < 0:
            raise ValueError("min_count 不能小于 0")

        if max_count < min_count:
            raise ValueError("max_count 不能小于 min_count")

        added = random.randint(min_count, max_count)
        self.touchend += added
        return added

    def visibility_change(
        self,
        *,
        probability: float = 0.1,
        count: int | None = None,
        min_count: int = 1,
        max_count: int = 1,
    ) -> int:
        """
        pre_state.visibility_change()
            # 10% 概率 visibilitychange += 1
        pre_state.visibility_change(probability=0.3)
            # 30% 概率 visibilitychange += 1
        pre_state.visibility_change(probability=0.3, count=2)
            # 30% 概率 visibilitychange += 2
        pre_state.visibility_change(probability=0.3, min_count=1, max_count=3)
            # 30% 概率 visibilitychange += 随机 1~3
        """
        if not 0 <= probability <= 1:
            raise ValueError("probability 必须在 0 到 1 之间")

        if random.random() > probability:
            return 0

        if count is not None:
            if count < 0:
                raise ValueError("count 不能小于 0")

            self.visibilitychange += count
            return count

        if min_count < 0:
            raise ValueError("min_count 不能小于 0")

        if max_count < min_count:
            raise ValueError("max_count 不能小于 min_count")

        added = random.randint(min_count, max_count)
        self.visibilitychange += added
        return added


def init_ctoken_state(
    *,
    timeoffet: float = 0.0,
    ticket_collection_t: int = 0,
    browser_window_state: BrowserWindowState | None = None,
    history_length: int = random.randint(2, 10),
    user_agent_length: int = 140,
    href_length: int = 76,
    device_pixel_ratio: float = 4.0,
) -> CTokenRuntimeState:
    """
    初始化 ctoken 状态。

    对应字段：
    - m1
    - touchend
    - m2
    - visibilitychange
    - m3
    - m4
    - openWindow
    - m5
    - timer
    - timediff
    - m6
    - m7
    - m8
    - m9
    """

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
        openWindow=1,
        m5=derive_d(5),
        base_timer=0,
        m6=derive_d(6),
        m7=derive_d(7),
        m8=derive_d(8),
        m9=derive_d(9),
        created_at=current_time_ms(timeoffset=timeoffet) / 1000,
        timeoffet=timeoffet,
        ticket_collection_t=ticket_collection_t,
    )

    logger.info(state.to_dict())
    return state


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
