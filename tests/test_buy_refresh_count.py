"""计数调度逻辑的单元测试。

验证循环内按随机 create 次数触发 fetch_project_payload 的核心行为：
- 达到目标次数 N 后触发，且触发后重置计数并重抽 N
- 100001 路径也重置计数（两路径共享）
- max_count <= 0 或 min > max 时关闭定时
不涉及真实网络，隔离验证调度逻辑。
"""

import random


from app_cmd.config.BuyConfig import BuyConfig


def _make_scheduler(config: BuyConfig):
    """复刻 task/buy.py 里 buy_stream 的计数调度结构，便于隔离测试。"""
    refresh_min_count = max(0, int(config.refresh_interval_min_count))
    refresh_max_count = max(0, int(config.refresh_interval_max_count))
    refresh_count_enabled = (
        refresh_max_count > 0 and refresh_min_count <= refresh_max_count
    )
    refresh_counter = 0
    refresh_target = (
        random.randint(refresh_min_count, refresh_max_count)
        if refresh_count_enabled
        else None
    )

    fetch_calls = {"count": 0}

    def _fetch_project_detail_only():
        fetch_calls["count"] += 1

    def _reset_refresh_counter():
        nonlocal refresh_counter, refresh_target
        refresh_counter = 0
        if refresh_count_enabled:
            refresh_target = random.randint(refresh_min_count, refresh_max_count)

    def _on_100001():
        _reset_refresh_counter()

    def tick():
        """模拟内层 create 循环出口处的计数+触发逻辑。返回是否触发了 fetch。"""
        nonlocal refresh_counter
        triggered = False
        if refresh_count_enabled and refresh_target is not None:
            refresh_counter += 1
            if refresh_counter >= refresh_target:
                _fetch_project_detail_only()
                triggered = True
                _reset_refresh_counter()
        return triggered

    return {
        "tick": tick,
        "on_100001": _on_100001,
        "fetch_calls": fetch_calls,
        "state": lambda: (refresh_counter, refresh_target, refresh_count_enabled),
    }


def _config(min_count: int, max_count: int) -> BuyConfig:
    return BuyConfig(
        refresh_interval_min_count=min_count,
        refresh_interval_max_count=max_count,
    )


def test_trigger_after_target_count_then_resets():
    random.seed(42)
    sched = _make_scheduler(_config(3, 3))  # 固定 target=3
    target = sched["state"]()[1]
    assert target == 3

    triggered_at = []
    for i in range(1, 10):
        if sched["tick"]():
            triggered_at.append(i)

    # 每 3 次 tick 触发一次：第3、6、9次
    assert triggered_at == [3, 6, 9]
    assert sched["fetch_calls"]["count"] == 3
    # 触发后计数归零
    assert sched["state"]()[0] == 0


def test_fetch_not_concurrent_with_create():
    """tick() 同步返回，fetch 在 tick 内完成 —— 模拟 fetch 落在 sleep 窗口，不与 create 并发。"""
    sched = _make_scheduler(_config(1, 1))  # 每次 tick 都触发
    for _ in range(5):
        assert sched["tick"]() is True
    assert sched["fetch_calls"]["count"] == 5


def test_disabled_when_max_zero():
    sched = _make_scheduler(_config(10, 0))
    assert sched["state"]()[2] is False  # refresh_count_enabled
    for _ in range(100):
        assert sched["tick"]() is False
    assert sched["fetch_calls"]["count"] == 0


def test_disabled_when_min_greater_than_max():
    sched = _make_scheduler(_config(50, 10))
    assert sched["state"]()[2] is False
    for _ in range(100):
        assert sched["tick"]() is False
    assert sched["fetch_calls"]["count"] == 0


def test_100001_resets_counter():
    random.seed(7)
    sched = _make_scheduler(_config(5, 5))
    # 走 3 次 tick，计数到 3，未触发
    for _ in range(3):
        sched["tick"]()
    assert sched["state"]()[0] == 3

    # 100001 触发：计数重置
    sched["on_100001"]()
    assert sched["state"]()[0] == 0
    # 之后需要再 5 次 tick 才触发（重新从 0 计数）
    triggered = []
    for i in range(1, 7):
        if sched["tick"]():
            triggered.append(i)
    assert triggered == [5]


def test_default_config_values():
    cfg = BuyConfig()
    assert cfg.refresh_interval_min_count == 10
    assert cfg.refresh_interval_max_count == 30
    assert cfg.rate_limit_delay_ms == 100
