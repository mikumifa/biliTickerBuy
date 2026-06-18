import base64
import time


_BASE64_STD_ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789/+="
)
_BASE64_TOKEN_ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-."
)


def generate_token(
    project_id: int,
    screen_id: int,
    order_type: int,
    count: int,
    sku_id: int,
    ts: int | None = None,
) -> str:
    """
    生成 Token。

    Layout:
    - 1 byte header: 0xC0
    - 4 bytes timestamp
    - 4 bytes project_id
    - 4 bytes screen_id
    - 1 byte order_type
    - 2 bytes count
    - 4 bytes sku_id
    - base64, then remap /+= -> _-.
    """

    timestamp = int(time.time()) if ts is None else int(ts)
    token = bytes([0xC0])
    token += timestamp.to_bytes(4, "big")
    token += int(project_id).to_bytes(4, "big")
    token += int(screen_id).to_bytes(4, "big")
    token += int(order_type).to_bytes(1, "big")
    token += int(count).to_bytes(2, "big")
    token += int(sku_id).to_bytes(4, "big")

    encoded = base64.b64encode(token).decode("ascii")
    return encoded.translate(
        str.maketrans(_BASE64_STD_ALPHABET, _BASE64_TOKEN_ALPHABET)
    )
