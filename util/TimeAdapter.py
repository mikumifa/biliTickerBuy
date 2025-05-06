import time

from loguru import logger


class TimeAdapter:
    def __init__(self):
        self.start_time = time.time()
        self.n = 0
        self.mean_x = 0.0
        self.mean_y = 0.0
        self.S_xx = 0.0
        self.S_xy = 0.0
        self.a = 1
        self.b = -5

    def start(self):
        self.start_time = time.time()

    def adapter(self, t: float, isSuccess: bool):
        if self.start_time is None:
            raise ValueError("Call start() before adapter().")

        x = t - self.start_time
        logger.debug(
            f"X: {x} isSuccess: {isSuccess}")
        label = 1 if isSuccess else -1
        y_hat = self.a * x + self.b
        lr = 0.001
        self.a += lr * label * x
        self.b += lr * label

    def get_model(self):
        return self.a, self.b

    def get_next_try_time(self):
        if self.start_time is None:
            raise ValueError("Call start() before get_next_try_time().")
        return self.start_time-self.b / (self.a+1e-6)
