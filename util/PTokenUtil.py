import base64
import random
import time

from util.CTokenUtil import CTokenGenerator


DEFAULT_PTOKEN_TAIL_TAG_1 = 4
DEFAULT_PTOKEN_TAIL_TAG_2 = 1


def _decode_interleaved_even_u8(token: str) -> list[int]:
    raw = base64.b64decode(token)
    if len(raw) % 2 != 0:
        raise ValueError(f"token length must be divisible by 2: {len(raw)}")
    return [raw[index] for index in range(0, len(raw), 2)]


def _encode_u8_as_u16_base64(values: list[int]) -> str:
    raw = bytearray()
    for value in values:
        if value < 0 or value > 0xFF:
            raise ValueError(f"u8 value out of range: {value}")
        raw.extend((0, value))
    return base64.b64encode(raw).decode("ascii")


def decode_ptoken_u8(ptoken: str) -> list[int]:
    raw = base64.b64decode(ptoken)
    if len(raw) % 2 != 0:
        raise ValueError(f"ptoken length must be divisible by 2: {len(raw)}")
    return [raw[index + 1] for index in range(0, len(raw), 2)]


def decode_ctoken_u8(ctoken: str) -> list[int]:
    return _decode_interleaved_even_u8(ctoken)


def infer_ptoken_prefix_from_ctoken(prepare_ctoken: str) -> list[int]:
    prepare_ctoken_u8 = _decode_interleaved_even_u8(prepare_ctoken)
    if len(prepare_ctoken_u8) < 12:
        raise ValueError("prepare ctoken is too short")
    return [
        17,
        prepare_ctoken_u8[1],
        8,
        prepare_ctoken_u8[3],
        1,
        99,
        prepare_ctoken_u8[6],
        4,
        prepare_ctoken_u8[8],
        prepare_ctoken_u8[9],
        prepare_ctoken_u8[10],
        prepare_ctoken_u8[11],
    ]


def generate_inferred_ptoken(
    prepare_ctoken: str,
    *,
    collection_second: int | None = None,
    current_second: int | None = None,
) -> str:
    if collection_second is None:
        collection_second = int(time.time())
    if current_second is None:
        current_second = int(time.time())

    elapsed = max(0, current_second - collection_second)
    if elapsed > 0xFFFF:
        elapsed = 0xFFFF

    prefix = infer_ptoken_prefix_from_ctoken(prepare_ctoken)
    values = prefix + [
        DEFAULT_PTOKEN_TAIL_TAG_1,
        DEFAULT_PTOKEN_TAIL_TAG_2,
        (elapsed >> 8) & 0xFF,
        elapsed & 0xFF,
    ]
    return _encode_u8_as_u16_base64(values)


def generate_ptoken(
    ctoken: str,
    uid: int | str | None,
    timestamp: int,
    *,
    collection_second: int | None = None,
) -> str:
    """Best-effort OSS approximation of BHYG's hidden generate_ptoken API.

    BHYG's public repository exposes the function signature but not the body.
    Current observable samples indicate the public ptoken structure is derived
    from prepare-stage ctoken fields plus an elapsed-seconds tail.
    """

    del uid

    if collection_second is None:
        collection_second = timestamp
    return generate_inferred_ptoken(
        ctoken,
        collection_second=collection_second,
        current_second=timestamp,
    )


def generate_inferred_prepare_ctoken(
    *,
    collection_second: int | None = None,
    time_offset: int = 0,
    stay_time: int = 3000,
) -> tuple[str, int]:
    if collection_second is None:
        collection_second = int(time.time())
    generator = CTokenGenerator(collection_second, time_offset, stay_time)
    return (
        generator.generate_ctoken(
            touchend=random.randint(1, 5),
            beforeunload=random.randint(1, 3),
            openWindow=random.randint(1, 3),
        ),
        collection_second,
    )


def generate_inferred_ptoken_without_prepare(
    *,
    collection_second: int | None = None,
    current_second: int | None = None,
    time_offset: int = 0,
    stay_time: int = 3000,
) -> dict:
    prepare_ctoken, used_collection_second = generate_inferred_prepare_ctoken(
        collection_second=collection_second,
        time_offset=time_offset,
        stay_time=stay_time,
    )
    current_second = (
        int(time.time())
        if current_second is None
        else current_second
    )
    ptoken = generate_ptoken(
        prepare_ctoken,
        uid=None,
        timestamp=current_second,
        collection_second=used_collection_second,
    )
    return {
        "collection_second": used_collection_second,
        "current_second": current_second,
        "prepare_ctoken": prepare_ctoken,
        "ptoken": ptoken,
        "ptoken_prefix_u8": infer_ptoken_prefix_from_ctoken(prepare_ctoken),
        "ptoken_u8": decode_ptoken_u8(ptoken),
    }
