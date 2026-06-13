import base64
import random
import time


class CTokenGenerator:
    """Generate the risk-control ctoken used by hot-project order requests."""

    def __init__(self, ticket_collection_t, time_offset, stay_time):
        self.ticket_collection_t = ticket_collection_t
        self.time_offset = time_offset
        self.stay_time = stay_time

    @staticmethod
    def _get_env_data() -> list[int]:
        return [
            0,
            0,
            random.randint(1000, 2000),
            random.randint(800, 1200),
            random.randint(1600, 2400),
            random.randint(800, 1200),
            0,
            0,
            random.randint(1600, 2400),
            random.randint(800, 1200),
            random.randint(1600, 2400),
            random.randint(10, 50),
            random.randint(100, 200),
            random.randint(50, 100),
            20,
            int(time.time() * 1000) % 256,
        ]

    @staticmethod
    def _derive_mask(index: int, env_data: list[int]) -> int:
        return (env_data[index % 16] + env_data[(3 * index) % 16] + 17 * index) & 0xFF

    @staticmethod
    def _append_byte(buffer: bytearray, value: int) -> None:
        buffer.extend((min(value, 0xFF), 0))

    @staticmethod
    def _append_short(buffer: bytearray, value: int) -> None:
        value = min(value, 0xFFFF)
        buffer.extend(((value >> 8) & 0xFF, 0, value & 0xFF, 0))

    def generate_ctoken(self, is_create_v2: bool) -> str:
        """Return a v3 ctoken for either the prepare or createV2 stage."""
        env_data = self._get_env_data()
        masks = [self._derive_mask(index, env_data) for index in range(1, 10)]

        if is_create_v2:
            elapsed = max(
                0,
                int(time.time() + self.time_offset - self.ticket_collection_t),
            )
            timer = max(0, int(elapsed + self.stay_time))
            touchend = random.randint(30, 50)
            beforeunload = random.randint(10, 50)
        else:
            timer = max(0, int(self.stay_time))
            touchend = random.randint(1, 5)
            beforeunload = random.randint(1, 3)

        visibilitychange = random.randint(10, 50)
        token_bytes = bytearray()
        self._append_byte(token_bytes, masks[0])
        self._append_byte(token_bytes, touchend)
        self._append_byte(token_bytes, 0xFF)
        self._append_byte(token_bytes, masks[1])
        self._append_byte(token_bytes, visibilitychange)
        self._append_byte(token_bytes, 0xFF)
        for mask in masks[2:4]:
            self._append_byte(token_bytes, mask)
        self._append_byte(token_bytes, beforeunload)
        self._append_byte(token_bytes, masks[4])
        self._append_short(token_bytes, timer)
        for mask in masks[5:]:
            self._append_byte(token_bytes, mask)

        return base64.b64encode(token_bytes).decode("ascii")
