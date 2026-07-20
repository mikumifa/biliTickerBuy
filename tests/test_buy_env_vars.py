"""buy(CLI/无头)命令下环境变量(BTB_*)生效的单元测试。

覆盖 issue #1106：buy 装配链此前从不调用 from_env()，导致所有 BTB_* 不生效。
验证优先级：CLI 参数 > 环境变量(BTB_*) > 硬默认值，并保证不设 env 时行为不变。

通过构造 argv + monkeypatch 环境变量，走 main.py 真实装配链
（tyro.cli 解析 -> merge_env 回填），断言最终 BuyConfig 的字段值。
"""

from __future__ import annotations

import tyro

from app_cmd.config.BuyConfig import BuyConfig


def _assemble(argv: list[str]) -> BuyConfig:
    """复刻 main.main() 中 buy 分支的装配：解析 -> env 回填。"""
    # 延迟导入 main：避免 pytest 采集期把仓库根当作包（根目录存在 __init__.py）。
    import main as main_module

    normalized = main_module._normalize_argv(argv)
    command = tyro.cli(main_module.CliCommand, args=normalized)
    assert isinstance(command, BuyConfig)
    return command.merge_env(main_module._explicit_cli_flags(normalized))


def test_env_applies_when_no_cli(monkeypatch):
    """只设环境变量、CLI 未传：应读到 env 值。"""
    monkeypatch.setenv("BTB_NTFY_URL", "https://ntfy.example/topic")
    monkeypatch.setenv("BTB_INTERVAL", "500")
    monkeypatch.setenv("BTB_HTTPS_PROXYS", "http://127.0.0.1:7890")

    config = _assemble(["buy"])

    assert config.notifier_config.ntfy_url == "https://ntfy.example/topic"
    assert config.interval == 500
    assert config.https_proxys == "http://127.0.0.1:7890"


def test_cli_overrides_env(monkeypatch):
    """CLI 与 env 同时存在：CLI 显式参数优先。"""
    monkeypatch.setenv("BTB_INTERVAL", "500")
    monkeypatch.setenv("BTB_NTFY_URL", "https://env.example/topic")

    config = _assemble(
        [
            "buy",
            "--interval",
            "1234",
            "--notifier-config.ntfy-url",
            "https://cli.example/topic",
        ]
    )

    assert config.interval == 1234
    assert config.notifier_config.ntfy_url == "https://cli.example/topic"


def test_defaults_when_nothing_set(monkeypatch):
    """既无 env 也无 CLI：使用硬默认值，行为与修复前完全一致。"""
    for key in (
        "BTB_INTERVAL",
        "BTB_NTFY_URL",
        "BTB_HTTPS_PROXYS",
        "BTB_LOG_LEVEL",
    ):
        monkeypatch.delenv(key, raising=False)

    config = _assemble(["buy"])

    assert config.interval == 1000
    assert config.notifier_config.ntfy_url == ""
    assert config.https_proxys == "none"
    assert config.log_level == "standard"


def test_btb_ntfy_url_now_effective_in_buy(monkeypatch):
    """issue #1106 回归点：BTB_NTFY_URL 在 buy 命令下现在生效。"""
    monkeypatch.delenv("BTB_NTFY_URL", raising=False)
    # 未设时保持空（默认）
    assert _assemble(["buy"]).notifier_config.ntfy_url == ""

    # 设置后 buy 装配链应读到该值
    monkeypatch.setenv("BTB_NTFY_URL", "https://ntfy.sh/mytopic")
    assert (
        _assemble(["buy"]).notifier_config.ntfy_url == "https://ntfy.sh/mytopic"
    )


def test_bool_env_applies(monkeypatch):
    """bool 字段(cli_true)未显式传时也应被 env 覆盖。"""
    monkeypatch.setenv("BTB_USE_LOCAL_TOKEN", "true")
    config = _assemble(["buy"])
    assert config.use_local_token is True


def test_bool_cli_true_overrides_env_absent(monkeypatch):
    """显式传 --use-local-token 时保持 True，即便 env 未设。"""
    monkeypatch.delenv("BTB_USE_LOCAL_TOKEN", raising=False)
    config = _assemble(["buy", "--use-local-token"])
    assert config.use_local_token is True
