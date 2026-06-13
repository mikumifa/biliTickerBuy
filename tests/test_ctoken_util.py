import base64

from util.CTokenUtil import CTokenGenerator


def test_derive_mask_matches_v3_formula():
    env_data = list(range(16))

    assert [
        CTokenGenerator._derive_mask(index, env_data) for index in range(1, 10)
    ] == [21, 42, 63, 84, 105, 110, 131, 152, 173]


def test_prepare_ctoken_uses_v3_layout(monkeypatch):
    generator = CTokenGenerator(ticket_collection_t=0, time_offset=0, stay_time=0x1234)
    monkeypatch.setattr(generator, "_get_env_data", lambda: list(range(16)))
    values = iter([3, 2, 17])
    monkeypatch.setattr("util.CTokenUtil.random.randint", lambda _a, _b: next(values))

    token = base64.b64decode(generator.generate_ctoken(is_create_v2=False))

    assert token == bytes(
        [
            21,
            0,
            3,
            0,
            255,
            0,
            42,
            0,
            17,
            0,
            255,
            0,
            63,
            0,
            84,
            0,
            2,
            0,
            105,
            0,
            0x12,
            0,
            0x34,
            0,
            110,
            0,
            131,
            0,
            152,
            0,
            173,
            0,
        ]
    )


def test_create_ctoken_caps_timer_and_uses_create_event_ranges(monkeypatch):
    generator = CTokenGenerator(ticket_collection_t=100, time_offset=5, stay_time=10)
    monkeypatch.setattr(generator, "_get_env_data", lambda: list(range(16)))
    monkeypatch.setattr("util.CTokenUtil.time.time", lambda: 100_000)
    values = iter([35, 25, 15])
    monkeypatch.setattr("util.CTokenUtil.random.randint", lambda _a, _b: next(values))

    token = base64.b64decode(generator.generate_ctoken(is_create_v2=True))

    assert len(token) == 32
    assert token[2] == 35
    assert token[8] == 15
    assert token[16] == 25
    assert token[20:24] == bytes([0xFF, 0, 0xFF, 0])
