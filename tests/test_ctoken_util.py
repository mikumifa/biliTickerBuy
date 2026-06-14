import base64

from util.CTokenUtil import CTokenGenerator


def test_derive_mask_matches_v3_formula():
    env_data = list(range(16))

    assert [
        CTokenGenerator._derive_mask(index, env_data) for index in range(1, 10)
    ] == [21, 42, 63, 84, 105, 110, 131, 152, 173]


def test_prepare_ctoken_uses_v3_layout(monkeypatch):
    monkeypatch.setattr(
        CTokenGenerator, "_get_env_data", staticmethod(lambda: list(range(16)))
    )
    generator = CTokenGenerator(ticket_collection_t=0, time_offset=0, stay_time=0x1234)

    token = base64.b64decode(
        generator.generate_ctoken(
            touchend=3,
            visibilitychange=17,
            beforeunload=2,
            timer=0,
            ticket_collection_t=0,
        )
    )

    assert token == bytes(
        [
            21,
            0,
            3,
            0,
            42,
            0,
            17,
            0,
            63,
            0,
            84,
            0,
            2,
            0,
            105,
            0,
            0x00,
            0,
            0x00,
            0,
            0x00,
            0,
            0x00,
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
    monkeypatch.setattr(
        CTokenGenerator, "_get_env_data", staticmethod(lambda: list(range(16)))
    )
    generator = CTokenGenerator(ticket_collection_t=100, time_offset=0, stay_time=10)

    token = base64.b64decode(
        generator.generate_ctoken(
            touchend=35,
            visibilitychange=25,
            beforeunload=15,
            timer=70000,
            ticket_collection_t=70000,
        )
    )

    assert len(token) == 32
    assert token[2] == 35
    assert token[6] == 25
    assert token[12] == 15
    assert token[20:24] == bytes([0xFF, 0, 0xFF, 0])
