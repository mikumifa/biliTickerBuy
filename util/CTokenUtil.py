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

    def generate_ctoken(
        self,
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
        ticket_collection_t: int = 0,
        openWindow: int = -1,
    ) -> str:
        def m(t: int, env_data: list[int]) -> int:
            idx1 = t % 16
            idx2 = (3 * t) % 16
            result = (env_data[idx1] + env_data[idx2] + 17 * t) & 255
            return result

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

        env_data = self._get_env_data()
        if m1 == -1:
            m1 = m(1, env_data)
        if m2 == -1:
            m2 = m(2, env_data)
        if m3 == -1:
            m3 = m(3, env_data)
        if m4 == -1:
            m4 = m(4, env_data)
        if m5 == -1:
            m5 = m(5, env_data)
        if m6 == -1:
            m6 = m(6, env_data)
        if m7 == -1:
            m7 = m(7, env_data)
        if m8 == -1:
            m8 = m(8, env_data)
        if m9 == -1:
            m9 = m(9, env_data)

        token_bytes = b""
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
        token_bytes += data["m1"].to_bytes(1, byteorder="big")
        token_bytes += b"\x00"
        try:
            token_bytes += data["touchend"].to_bytes(1, byteorder="big")
        except OverflowError:
            token_bytes += b"\xff"
        token_bytes += b"\x00"
        token_bytes += data["m2"].to_bytes(1, byteorder="big")
        token_bytes += b"\x00"
        try:
            token_bytes += data["visibilitychange"].to_bytes(1, byteorder="big")
        except OverflowError:
            token_bytes += b"\xff"
        token_bytes += b"\x00"
        token_bytes += data["m3"].to_bytes(1, byteorder="big")
        token_bytes += b"\x00"
        token_bytes += data["m4"].to_bytes(1, byteorder="big")
        token_bytes += b"\x00"
        try:
            token_bytes += data["beforeunload"].to_bytes(1, byteorder="big")
        except OverflowError:
            token_bytes += b"\xff"
        token_bytes += b"\x00"
        token_bytes += data["m5"].to_bytes(1, byteorder="big")
        token_bytes += b"\x00"

        try:
            temp_timer = int(data["timer"]).to_bytes(2, byteorder="big")
            token_bytes += temp_timer[0].to_bytes(1, byteorder="big")
            token_bytes += b"\x00"
            token_bytes += temp_timer[1].to_bytes(1, byteorder="big")
            token_bytes += b"\x00"
        except OverflowError:
            token_bytes += b"\xff\x00\xff\x00"

        try:
            temp_ticket_collection_t = int(data["ticket_collection_t"]).to_bytes(
                2, byteorder="big"
            )
            token_bytes += temp_ticket_collection_t[0].to_bytes(1, byteorder="big")
            token_bytes += b"\x00"
            token_bytes += temp_ticket_collection_t[1].to_bytes(1, byteorder="big")
            token_bytes += b"\x00"
        except OverflowError:
            token_bytes += b"\xff\x00\xff\x00"
        token_bytes += data["m6"].to_bytes(1, byteorder="big")
        token_bytes += b"\x00"
        token_bytes += data["m7"].to_bytes(1, byteorder="big")
        token_bytes += b"\x00"
        token_bytes += data["m8"].to_bytes(1, byteorder="big")
        token_bytes += b"\x00"
        token_bytes += data["m9"].to_bytes(1, byteorder="big")
        token_bytes += b"\x00"
        return base64.b64encode(token_bytes).decode("utf-8")

    @staticmethod
    def _derive_mask(index: int, env_data: list[int]) -> int:
        return (env_data[index % 16] + env_data[(3 * index) % 16] + 17 * index) & 255
