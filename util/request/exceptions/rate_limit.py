class BiliRateLimitError(RuntimeError):
    def __init__(self, message: str, *, response=None):
        super().__init__(message)
        self.response = response
