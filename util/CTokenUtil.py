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
        return (env_data[index % 16] + env_data[(3 * index) % 16] + 17 * index) & 255

    def generate_ctoken(
        self,
        for_create_stage: bool | None = None,
        *,
        m1: int = -1,
        m2: int = -1,
        m3: int = -1,
        m4: int = -1,
        m5: int = -1,
        m6: int = -1,
        m7: int = -1,
        m8: int = -1,
        m9: int = -1,
        touchend: int = -1,
        visibilitychange: int = -1,
        beforeunload: int = -1,
        timer: int = -1,
        ticket_collection_t: int | None = None,
        openWindow: int = -1,
    ) -> str:
        """BHYG-style ctoken generator, with a compatibility bool mode."""

        if for_create_stage is not None:
            if for_create_stage:
                if timer == -1:
                    elapsed = max(
                        0,
                        int(time.time() + self.time_offset - self.ticket_collection_t),
                    )
                    timer = elapsed + 10
                if touchend == -1:
                    touchend = random.randint(30, 50)
                if beforeunload == -1 and openWindow == -1:
                    beforeunload = random.randint(10, 50)
            else:
                if touchend == -1:
                    touchend = random.randint(1, 5)
                if beforeunload == -1 and openWindow == -1:
                    beforeunload = random.randint(1, 3)

        if touchend == -1:
            touchend = random.randint(30, 50)
        if visibilitychange == -1:
            visibilitychange = random.randint(10, 50)
        if beforeunload == -1:
            if openWindow != -1:
                beforeunload = openWindow
            else:
                beforeunload = random.randint(10, 50)
        if timer == -1:
            timer = random.randint(1, 10)
        if ticket_collection_t is None:
            ticket_collection_t = 0

        env_data = self._get_env_data()
        if m1 == -1:
            m1 = self._derive_mask(1, env_data)
        if m2 == -1:
            m2 = self._derive_mask(2, env_data)
        if m3 == -1:
            m3 = self._derive_mask(3, env_data)
        if m4 == -1:
            m4 = self._derive_mask(4, env_data)
        if m5 == -1:
            m5 = self._derive_mask(5, env_data)
        if m6 == -1:
            m6 = self._derive_mask(6, env_data)
        if m7 == -1:
            m7 = self._derive_mask(7, env_data)
        if m8 == -1:
            m8 = self._derive_mask(8, env_data)
        if m9 == -1:
            m9 = self._derive_mask(9, env_data)

        token_bytes = bytearray()
        data = {
            "m1": m1,
            "m2": m2,
            "m3": m3,
            "m4": m4,
            "m5": m5,
            "m6": m6,
            "m7": m7,
            "m8": m8,
            "m9": m9,
            "touchend": touchend,
            "visibilitychange": visibilitychange,
            "beforeunload": beforeunload,
            "timer": timer,
            "ticket_collection_t": ticket_collection_t,
        }

        def append_byte(value: int) -> None:
            try:
                token_bytes.extend(int(value).to_bytes(1, byteorder="big"))
            except OverflowError:
                token_bytes.extend(b"\xff")
            token_bytes.extend(b"\x00")

        append_byte(data["m1"])
        append_byte(data["touchend"])
        append_byte(data["m2"])
        append_byte(data["visibilitychange"])
        append_byte(data["m3"])
        append_byte(data["m4"])
        append_byte(data["beforeunload"])
        append_byte(data["m5"])

        try:
            temp_timer = int(data["timer"]).to_bytes(2, byteorder="big")
            token_bytes.extend((temp_timer[0], 0, temp_timer[1], 0))
        except OverflowError:
            token_bytes.extend(b"\xff\x00\xff\x00")

        try:
            temp_collection = int(data["ticket_collection_t"]).to_bytes(
                2, byteorder="big"
            )
            token_bytes.extend((temp_collection[0], 0, temp_collection[1], 0))
        except OverflowError:
            token_bytes.extend(b"\xff\x00\xff\x00")

        append_byte(data["m6"])
        append_byte(data["m7"])
        append_byte(data["m8"])
        append_byte(data["m9"])

        return base64.b64encode(bytes(token_bytes)).decode("utf-8")
