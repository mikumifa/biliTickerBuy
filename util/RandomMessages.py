import json
import os
import random

from util import get_application_path

_FAIL_MESSAGES: list[str] = []


def _load_messages() -> list[str]:
    json_path = os.path.join(get_application_path(), "assets", "fail_messages.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return ["抢票失败了..."]


_FAIL_MESSAGES = _load_messages()


def get_random_fail_message() -> str:
    return random.choice(_FAIL_MESSAGES)
