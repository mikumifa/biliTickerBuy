from __future__ import annotations

import random
import secrets
from typing import Literal, NotRequired, TypedDict
from typing import Any, Mapping


# =========================
# TypedDict 定义
# =========================


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


class BrowserDisplayState(TypedDict):
    devicePixelRatio: float
    colorDepth: int
    pixelDepth: int


class BrowserNavigatorState(TypedDict):
    userAgent: str
    appCodeName: str
    appName: str
    appVersion: str
    platform: str
    product: str
    productSub: str
    vendor: str
    vendorSub: str
    language: str
    languages: list[str]
    cookieEnabled: bool
    hardwareConcurrency: int
    deviceMemory: int
    maxTouchPoints: int
    webdriver: bool


class BrowserLocaleState(TypedDict):
    locale: str
    timezone: str
    timezoneOffset: int


class BrowserLocationState(TypedDict):
    href: str
    origin: str
    protocol: str
    host: str
    hostname: str
    port: str
    pathname: str
    search: str
    hash: str
    hrefLength: int
    historyLength: int


class BrowserWebGLState(TypedDict):
    vendor: str
    renderer: str
    unmaskedVendor: str
    unmaskedRenderer: str


class BrowserCanvasState(TypedDict):
    winding: Literal["yes", "no"]
    x64hash128: str
    dataUrlHash: NotRequired[str]


class BrowserStorageState(TypedDict):
    localStorage: dict[str, str]
    sessionStorage: dict[str, str]
    cookies: dict[str, str]


class BrowserFingerprintState(TypedDict):
    window: BrowserWindowState
    display: BrowserDisplayState
    navigator: BrowserNavigatorState
    locale: BrowserLocaleState
    location: BrowserLocationState
    webgl: BrowserWebGLState
    canvas: BrowserCanvasState
    storage: BrowserStorageState


# =========================
# 工具函数
# =========================


def random_hex(length: int) -> str:
    """
    生成 length 位 hex 字符串。
    例如 x64hash128 通常是 32 位 hex。
    """
    return secrets.token_hex((length + 1) // 2)[:length]


def build_chrome_user_agent(
    *,
    os_name: Literal["windows", "macos", "linux"] = "windows",
    chrome_major: int | None = None,
) -> str:
    """
    构造一个常见桌面 Chrome UA。
    """
    if chrome_major is None:
        chrome_major = random.choice([124, 125, 126, 127, 128, 129, 130, 131])

    chrome_version = (
        f"{chrome_major}.0.{random.randint(6000, 6900)}.{random.randint(80, 180)}"
    )

    if os_name == "windows":
        system = "Windows NT 10.0; Win64; x64"
    elif os_name == "macos":
        system = random.choice(
            [
                "Macintosh; Intel Mac OS X 10_15_7",
                "Macintosh; Intel Mac OS X 13_6_1",
                "Macintosh; Intel Mac OS X 14_5_0",
            ]
        )
    else:
        system = "X11; Linux x86_64"

    return (
        f"Mozilla/5.0 ({system}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_version} Safari/537.36"
    )


def extract_app_version_from_ua(user_agent: str) -> str:
    """
    navigator.appVersion 常见表现：UA 去掉开头的 Mozilla/
    """
    prefix = "Mozilla/"
    if user_agent.startswith(prefix):
        return user_agent[len(prefix) :]
    return user_agent


# =========================
# Window / Screen
# =========================


def generate_browser_window_state(
    *,
    screen_width: int | None = None,
    screen_height: int | None = None,
    maximized: bool | None = None,
    scroll: bool = False,
    os_name: Literal["windows", "macos", "linux"] = "windows",
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

    common_screens = [
        (1920, 1080),
        (2560, 1440),
        (1366, 768),
        (1440, 900),
        (1536, 864),
        (1600, 900),
        (1280, 720),
        (3840, 2160),
    ]

    if screen_width is None or screen_height is None:
        screen_width, screen_height = random.choice(common_screens)

    # Windows / Linux 常见底部任务栏；macOS 常见顶部菜单栏 + Dock
    if os_name == "macos":
        reserved_height = random.choice([64, 74, 84, 96])
    else:
        reserved_height = random.choice([40, 48, 56, 64])

    screen_avail_width = screen_width
    screen_avail_height = max(480, screen_height - reserved_height)

    if maximized is None:
        maximized = random.random() < 0.65

    # 浏览器外框与内容区差值
    chrome_width_delta = random.choice([0, 8, 12, 16])
    chrome_height_delta = random.choice([80, 88, 96, 104, 112, 120])

    if maximized:
        outer_width = screen_avail_width
        outer_height = screen_avail_height
        screen_x = 0
        screen_y = 0
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

    inner_width = max(320, outer_width - chrome_width_delta)
    inner_height = max(240, outer_height - chrome_height_delta)

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


# =========================
# Display
# =========================


def generate_browser_display_state(
    *,
    screen_width: int,
    screen_height: int,
    device_pixel_ratio: float | None = None,
) -> BrowserDisplayState:
    """
    对应：
    - window.devicePixelRatio
    - screen.colorDepth
    - screen.pixelDepth
    """

    if device_pixel_ratio is None:
        if screen_width >= 3840:
            device_pixel_ratio = random.choice([1.0, 1.25, 1.5, 2.0])
        elif screen_width >= 2560:
            device_pixel_ratio = random.choice([1.0, 1.25, 1.5])
        else:
            device_pixel_ratio = random.choice([1.0, 1.0, 1.0, 1.25, 1.5])

    return {
        "devicePixelRatio": device_pixel_ratio,
        "colorDepth": random.choice([24, 24, 24, 30]),
        "pixelDepth": 24,
    }


# =========================
# Navigator
# =========================


def generate_browser_navigator_state(
    *,
    os_name: Literal["windows", "macos", "linux"] = "windows",
    locale: str = "zh-CN",
    user_agent: str | None = None,
) -> BrowserNavigatorState:
    """
    对应常见 navigator 字段。
    """

    if user_agent is None:
        user_agent = build_chrome_user_agent(os_name=os_name)

    if os_name == "windows":
        platform = "Win32"
    elif os_name == "macos":
        platform = "MacIntel"
    else:
        platform = "Linux x86_64"

    if locale == "zh-CN":
        languages = random.choice(
            [
                ["zh-CN", "zh"],
                ["zh-CN", "zh", "en"],
                ["zh-CN", "zh", "en-US", "en"],
            ]
        )
    elif locale == "ja-JP":
        languages = random.choice(
            [
                ["ja-JP", "ja"],
                ["ja-JP", "ja", "en-US", "en"],
            ]
        )
    else:
        languages = [locale, locale.split("-")[0], "en-US", "en"]

    hardware_concurrency = random.choice([4, 6, 8, 8, 12, 16])
    device_memory = random.choice([4, 8, 8, 16])

    return {
        "userAgent": user_agent,
        "appCodeName": "Mozilla",
        "appName": "Netscape",
        "appVersion": extract_app_version_from_ua(user_agent),
        "platform": platform,
        "product": "Gecko",
        "productSub": "20030107",
        "vendor": "Google Inc.",
        "vendorSub": "",
        "language": languages[0],
        "languages": languages,
        "cookieEnabled": True,
        "hardwareConcurrency": hardware_concurrency,
        "deviceMemory": device_memory,
        "maxTouchPoints": 0,
        "webdriver": False,
    }


# =========================
# Locale / Timezone
# =========================


def generate_browser_locale_state(
    *,
    locale: str = "zh-CN",
    timezone: str | None = None,
) -> BrowserLocaleState:
    """
    对应：
    - Intl.DateTimeFormat().resolvedOptions().locale
    - Intl.DateTimeFormat().resolvedOptions().timeZone
    - new Date().getTimezoneOffset()

    注意：
    中国是 -480，日本是 -540。
    """

    timezone_map = {
        "zh-CN": ("Asia/Shanghai", -480),
        "zh-TW": ("Asia/Taipei", -480),
        "ja-JP": ("Asia/Tokyo", -540),
        "en-US": ("America/Los_Angeles", 480),
        "en-GB": ("Europe/London", 0),
    }

    default_timezone, default_offset = timezone_map.get(locale, ("Asia/Shanghai", -480))

    if timezone is None:
        timezone = default_timezone

    offset_map = {
        "Asia/Shanghai": -480,
        "Asia/Taipei": -480,
        "Asia/Tokyo": -540,
        "America/Los_Angeles": 480,
        "America/New_York": 300,
        "Europe/London": 0,
        "Europe/Berlin": -60,
    }

    timezone_offset = offset_map.get(timezone, default_offset)

    return {
        "locale": locale,
        "timezone": timezone,
        "timezoneOffset": timezone_offset,
    }


# =========================
# Location / History
# =========================


def generate_browser_location_state(
    *,
    href: str | None = None,
    history_length: int | None = None,
) -> BrowserLocationState:
    """
    对应：
    - window.location.href
    - window.location.origin
    - window.location.protocol
    - window.location.host
    - window.location.hostname
    - window.location.port
    - window.location.pathname
    - window.location.search
    - window.location.hash
    - history.length
    """

    if href is None:
        href = random.choice(
            [
                "https://show.bilibili.com/platform/detail.html?id=1001581",
                "https://show.bilibili.com/platform/detail.html?id=1001581&from=pc",
                "https://show.bilibili.com/platform/home.html",
            ]
        )

    from urllib.parse import urlparse

    parsed = urlparse(href)

    protocol = f"{parsed.scheme}:"
    hostname = parsed.hostname or ""
    port = str(parsed.port or "")
    host = hostname if not port else f"{hostname}:{port}"
    origin = f"{parsed.scheme}://{host}"

    pathname = parsed.path or "/"
    search = f"?{parsed.query}" if parsed.query else ""
    hash_value = f"#{parsed.fragment}" if parsed.fragment else ""

    if history_length is None:
        history_length = random.randint(2, 10)

    return {
        "href": href,
        "origin": origin,
        "protocol": protocol,
        "host": host,
        "hostname": hostname,
        "port": port,
        "pathname": pathname,
        "search": search,
        "hash": hash_value,
        "hrefLength": len(href),
        "historyLength": history_length,
    }


# =========================
# WebGL
# =========================


def generate_browser_webgl_state(
    *,
    os_name: Literal["windows", "macos", "linux"] = "windows",
    gpu_profile: Literal["intel", "nvidia", "amd", "apple", "swiftshader"]
    | None = None,
) -> BrowserWebGLState:
    """
    生成 WebGL 相关字段。

    对应常见：
    - gl.getParameter(gl.VENDOR)
    - gl.getParameter(gl.RENDERER)
    - WEBGL_debug_renderer_info.UNMASKED_VENDOR_WEBGL
    - WEBGL_debug_renderer_info.UNMASKED_RENDERER_WEBGL
    """

    if gpu_profile is None:
        if os_name == "macos":
            gpu_profile = random.choice(["apple", "intel"])
        elif os_name == "linux":
            gpu_profile = random.choice(["intel", "nvidia", "amd", "swiftshader"])
        else:
            gpu_profile = random.choice(["intel", "nvidia", "amd"])

    if gpu_profile == "nvidia":
        unmasked_vendor = "Google Inc. (NVIDIA)"
        unmasked_renderer = random.choice(
            [
                "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)",
            ]
        )
    elif gpu_profile == "amd":
        unmasked_vendor = "Google Inc. (AMD)"
        unmasked_renderer = random.choice(
            [
                "ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "ANGLE (AMD, AMD Radeon Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
            ]
        )
    elif gpu_profile == "apple":
        unmasked_vendor = "Google Inc. (Apple)"
        unmasked_renderer = random.choice(
            [
                "ANGLE (Apple, Apple M1, OpenGL 4.1)",
                "ANGLE (Apple, Apple M2, OpenGL 4.1)",
                "ANGLE (Apple, Apple M3, OpenGL 4.1)",
            ]
        )
    elif gpu_profile == "swiftshader":
        unmasked_vendor = "Google Inc. (Google)"
        unmasked_renderer = "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)"
    else:
        unmasked_vendor = "Google Inc. (Intel)"
        unmasked_renderer = random.choice(
            [
                "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
                "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
            ]
        )

    return {
        "vendor": "WebKit",
        "renderer": "WebKit WebGL",
        "unmaskedVendor": unmasked_vendor,
        "unmaskedRenderer": unmasked_renderer,
    }


# =========================
# Canvas
# =========================


def generate_browser_canvas_state(
    *,
    x64hash128: str | None = None,
    data_url_hash: str | None = None,
) -> BrowserCanvasState:
    """
    Canvas 指纹字段。

    如果你已经从真实浏览器拿到了 x64hash128，建议直接传入固定值。
    如果没传，这里只生成一个格式正确的 32 位 hex。
    """

    if x64hash128 is None:
        x64hash128 = random_hex(32)

    result: BrowserCanvasState = {
        "winding": "yes",
        "x64hash128": x64hash128,
    }

    if data_url_hash is not None:
        result["dataUrlHash"] = data_url_hash

    return result


# =========================
# Storage
# =========================


def generate_browser_storage_state(
    *,
    local_storage: dict[str, str] | None = None,
    session_storage: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> BrowserStorageState:
    """
    localStorage / sessionStorage / cookies。

    这里默认不给具体业务 cookie，避免和真实账号状态混在一起。
    """

    return {
        "localStorage": dict(local_storage or {}),
        "sessionStorage": dict(session_storage or {}),
        "cookies": dict(cookies or {}),
    }


# =========================
# 总入口
# =========================


def generate_browser_fingerprint_state(
    *,
    os_name: Literal["windows", "macos", "linux"] = "windows",
    locale: str = "zh-CN",
    timezone: str | None = None,
    screen_width: int | None = None,
    screen_height: int | None = None,
    maximized: bool | None = None,
    scroll: bool = False,
    href: str | None = None,
    history_length: int | None = None,
    user_agent: str | None = None,
    device_pixel_ratio: float | None = None,
    gpu_profile: Literal["intel", "nvidia", "amd", "apple", "swiftshader"]
    | None = None,
    canvas_hash: str | None = None,
    local_storage: dict[str, str] | None = None,
    session_storage: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> BrowserFingerprintState:
    """
    生成完整浏览器指纹状态。

    注意：
    - 同一套状态应该缓存复用；
    - 不建议每次请求都重新生成；
    - canvasHash / webgl / UA / platform / locale 最好保持自洽。
    """

    window = generate_browser_window_state(
        screen_width=screen_width,
        screen_height=screen_height,
        maximized=maximized,
        scroll=scroll,
        os_name=os_name,
    )

    display = generate_browser_display_state(
        screen_width=window["screenWidth"],
        screen_height=window["screenHeight"],
        device_pixel_ratio=device_pixel_ratio,
    )

    navigator = generate_browser_navigator_state(
        os_name=os_name,
        locale=locale,
        user_agent=user_agent,
    )

    locale_state = generate_browser_locale_state(
        locale=locale,
        timezone=timezone,
    )

    location = generate_browser_location_state(
        href=href,
        history_length=history_length,
    )

    webgl = generate_browser_webgl_state(
        os_name=os_name,
        gpu_profile=gpu_profile,
    )

    canvas = generate_browser_canvas_state(
        x64hash128=canvas_hash,
    )

    storage = generate_browser_storage_state(
        local_storage=local_storage,
        session_storage=session_storage,
        cookies=cookies,
    )
    return {
        "window": window,
        "display": display,
        "navigator": navigator,
        "locale": locale_state,
        "location": location,
        "webgl": webgl,
        "canvas": canvas,
        "storage": storage,
    }


def finalize_device_id(raw_device_id: str) -> str:
    if not isinstance(raw_device_id, str):
        raise TypeError("raw_device_id must be a string")

    if len(raw_device_id) != 32:
        raise ValueError("raw_device_id must be a 32-character hex string")

    try:
        hex_digits = [int(char, 16) for char in raw_device_id]
    except ValueError as exc:
        raise ValueError("raw_device_id must only contain hex characters") from exc

    def calculate_position_or_value(
        digits: list[int],
        source_index: int,
    ) -> int:
        """
        对应 JS 里的 i(e, t)
        """

        total_length = len(digits)
        half_length = total_length // 2

        target_index = source_index - digits[source_index]

        if target_index < half_length:
            target_index = total_length - (half_length - target_index)

        step_count = digits[target_index]
        cursor_index = target_index

        for _ in range(step_count):
            cursor_index -= 1

            if cursor_index < half_length:
                cursor_index = total_length - 1

        return (step_count + digits[cursor_index]) % half_length

    replace_index = calculate_position_or_value(
        digits=hex_digits,
        source_index=len(hex_digits) - 1,
    )

    replacement_value = calculate_position_or_value(
        digits=hex_digits,
        source_index=len(hex_digits) - 2,
    )

    replacement_hex = format(replacement_value, "x")

    return (
        raw_device_id[:replace_index]
        + replacement_hex
        + raw_device_id[replace_index + 1 :]
    )


def _cookie_dict_to_header(cookies: Mapping[str, str] | None) -> str:
    if not cookies:
        return ""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def _build_sec_ch_ua(user_agent: str) -> str:
    """
    根据 UA 粗略生成 sec-ch-ua。
    这里只做常见 Chrome / Edge 桌面端格式。
    """
    if "Edg/" in user_agent:
        return '"Microsoft Edge";v="126", "Chromium";v="126", "Not/A)Brand";v="8"'

    if "Chrome/" in user_agent:
        try:
            major = user_agent.split("Chrome/")[1].split(".")[0]
        except Exception:
            major = "126"
        return (
            f'"Google Chrome";v="{major}", "Chromium";v="{major}", "Not/A)Brand";v="8"'
        )

    return '"Chromium";v="126", "Not/A)Brand";v="8"'


def _build_sec_ch_ua_platform(platform: str) -> str:
    if platform == "Win32":
        return '"Windows"'
    if platform == "MacIntel":
        return '"macOS"'
    if platform.startswith("Linux"):
        return '"Linux"'
    return '"Windows"'


def build_headers_from_browser_state(
    state: dict[str, Any] | None = None,
    *,
    base_headers: dict[str, str] | None = None,
    referer: str | None = None,
    content_type: str = "application/x-www-form-urlencoded",
) -> dict[str, str]:
    """
    根据 BrowserFingerprintState 构造请求 headers。

    支持你之前这种结构：

    state = {
        "navigator": {...},
        "locale": {...},
        "location": {...},
        "storage": {
            "cookies": {...}
        }
    }
    """

    headers = dict(base_headers or {})

    navigator = (state or {}).get("navigator", {})
    location = (state or {}).get("location", {})
    storage = (state or {}).get("storage", {})

    user_agent = navigator.get(
        "userAgent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36",
    )

    languages = navigator.get("languages")
    if isinstance(languages, list) and languages:
        accept_language = ",".join(
            f"{lang};q={max(1.0 - idx * 0.1, 0.1):.1f}" if idx else lang
            for idx, lang in enumerate(languages)
        )
    else:
        accept_language = "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7"

    platform = navigator.get("platform", "Win32")

    if referer is None:
        referer = location.get("origin") or "https://show.bilibili.com/"

    if not referer.endswith("/"):
        referer = referer + "/"

    cookie_header = _cookie_dict_to_header(storage.get("cookies"))

    default_headers = {
        "accept": "*/*",
        "accept-language": accept_language,
        "content-type": content_type,
        "referer": referer,
        "origin": "https://show.bilibili.com",
        "priority": "u=1, i",
        "user-agent": user_agent,
        # 浏览器常见 fetch 相关字段
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        # Client Hints
        "sec-ch-ua": _build_sec_ch_ua(user_agent),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": _build_sec_ch_ua_platform(platform),
    }

    if cookie_header:
        default_headers["cookie"] = cookie_header

    # 用户传入 base_headers 时优先级更高
    default_headers.update(headers)

    return default_headers
