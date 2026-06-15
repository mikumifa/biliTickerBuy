import base64
import struct


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


def test_generate_ctoken_matches_real_sample():
    token = generate_ctoken(
        m1=245,
        touchend=0,
        m2=58,
        visibilitychange=0,
        m3=183,
        m4=189,
        openWindow=1,
        m5=228,
        timer=4,
        timediff=226.112,
        m6=126,
        m7=129,
        m8=136,
        m9=62,
    )

    assert token == "9QAAADoAAAC3AL0AAQDkAAAABAAAAOIAfgCBAIgAPgA="


def test_generate_ctoken_matches_second_real_sample():
    token = generate_ctoken(
        m1=245,
        touchend=0,
        m2=58,
        visibilitychange=0,
        m3=183,
        m4=189,
        openWindow=1,
        m5=228,
        timer=5,
        timediff=713.802,
        m6=126,
        m7=129,
        m8=136,
        m9=62,
    )

    assert token == "9QAAADoAAAC3AL0AAQDkAAAABQACAMkAfgCBAIgAPgA="


def test_generate_ctoken_matches_third_real_sample():
    token = generate_ctoken(
        m1=245,
        touchend=0,
        m2=58,
        visibilitychange=0,
        m3=183,
        m4=189,
        openWindow=1,
        m5=228,
        timer=8,
        timediff=766.034,
        m6=126,
        m7=129,
        m8=136,
        m9=62,
    )

    assert token == "9QAAADoAAAC3AL0AAQDkAAAACAACAP4AfgCBAIgAPgA="
