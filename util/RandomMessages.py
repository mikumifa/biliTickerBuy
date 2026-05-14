import json
import os
import random

from util import get_application_path


def get_random_fail_message():
    """
    随机获取一句抢票失败的话语

    Returns:
        str: 随机选择的失败话语
    """
    json_path = os.path.join(get_application_path(), "assets", "fail_messages.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            messages = json.load(f)
        return random.choice(messages)
    except Exception:
        return "抢票失败了..."
