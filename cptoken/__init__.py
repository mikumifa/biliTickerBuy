import base64
import struct


def _normalize_int(value: object) -> int:
    if value is None:
        return 0
    return int(value)


def _clamp8(value: object) -> int:
    normalized = _normalize_int(value)
    return 255 if normalized > 255 else max(0, normalized)


def _clamp16(value: object) -> int:
    normalized = _normalize_int(value)
    return 65535 if normalized > 65535 else max(0, normalized)


def _unsupported(name: str) -> None:
    raise NotImplementedError(
        f"{name} is not available in the public simplified cptoken package"
    )


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
    semantic_bytes = struct.pack(
        ">8B2H4B",
        _clamp8(m1),
        _clamp8(touchend),
        _clamp8(m2),
        _clamp8(visibilitychange),
        _clamp8(m3),
        _clamp8(m4),
        _clamp8(openWindow),
        _clamp8(m5),
        _clamp16(timer),
        _clamp16(ticket_collection_t),
        _clamp8(m6),
        _clamp8(m7),
        _clamp8(m8),
        _clamp8(m9),
    )

    transport_bytes = bytearray()
    for value in semantic_bytes:
        transport_bytes.extend((value, 0))
    return base64.b64encode(bytes(transport_bytes)).decode("utf-8")


def init_ctoken_state(
    *,
    scroll_x: int = 0,
    scroll_y: int = 0,
    inner_width: int = 0,
    inner_height: int = 0,
    outer_width: int = 0,
    outer_height: int = 0,
    screen_x: int = 0,
    screen_y: int = 0,
    screen_width: int = 0,
    screen_height: int = 0,
    screen_avail_width: int = 0,
    history_length: int = 0,
    user_agent_length: int = 0,
    href_length: int = 0,
    device_pixel_ratio: float = 0,
    random_events: bool = True,
) -> dict[str, int]:
    del (
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
        device_pixel_ratio,
        random_events,
    )
    return {
        "m1": 39,
        "touchend": 39,
        "m2": 39,
        "visibilitychange": 39,
        "m3": 39,
        "m4": 39,
        "openWindow": 39,
        "m5": 39,
        "timer": 39,
        "ticket_collection_t": 39,
        "m6": 39,
        "m7": 39,
        "m8": 39,
        "m9": 39,
    }


def sim_ctoken_state(before_state: dict[str, int], started_ms: int) -> dict[str, int]:
    del started_ms
    return dict(before_state)


def decode_ctoken_u8(ctoken: str) -> list[int]:
    del ctoken
    _unsupported("decode_ctoken_u8")


def decode_ptoken_u8(ptoken: str) -> list[int]:
    del ptoken
    _unsupported("decode_ptoken_u8")


def generate_inferred_prepare_ctoken(
    *,
    collection_second: int | None = None,
    time_offset: int = 0,
    stay_time: int = 3000,
) -> tuple[str, int]:
    del collection_second, time_offset, stay_time
    _unsupported("generate_inferred_prepare_ctoken")


def generate_inferred_ptoken(
    prepare_ctoken: str,
    *,
    collection_second: int | None = None,
    current_second: int | None = None,
) -> str:
    del prepare_ctoken, collection_second, current_second
    _unsupported("generate_inferred_ptoken")


def generate_inferred_ptoken_without_prepare(
    *,
    collection_second: int | None = None,
    current_second: int | None = None,
    time_offset: int = 0,
    stay_time: int = 3000,
) -> dict:
    del collection_second, current_second, time_offset, stay_time
    _unsupported("generate_inferred_ptoken_without_prepare")


def generate_ptoken(
    ctoken: str,
    uid: int | str | None,
    timestamp: int,
    *,
    collection_second: int | None = None,
) -> str:
    del ctoken, uid, timestamp, collection_second
    _unsupported("generate_ptoken")


def infer_ptoken_prefix_from_ctoken(prepare_ctoken: str) -> list[int]:
    del prepare_ctoken
    _unsupported("infer_ptoken_prefix_from_ctoken")


__all__ = [
    "decode_ctoken_u8",
    "decode_ptoken_u8",
    "generate_ctoken",
    "generate_inferred_prepare_ctoken",
    "generate_inferred_ptoken",
    "generate_inferred_ptoken_without_prepare",
    "generate_ptoken",
    "infer_ptoken_prefix_from_ctoken",
    "init_ctoken_state",
    "sim_ctoken_state",
]
