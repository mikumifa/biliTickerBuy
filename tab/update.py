"""Update center UI."""

from __future__ import annotations

import html
import os
import platform
import sys
from pathlib import Path

import gradio as gr
import requests

from app_update import UPDATE_CHANNEL_STABLE, ReleaseInfo, UpdateError, fetch_update
from app_version import get_app_version
from util import ConfigDB, EXE_PATH
from util.Constant import PACKAGE_NAME, UPDATE_CHANNEL_KEY


def _saved_channel() -> str:
    ConfigDB.get(UPDATE_CHANNEL_KEY)
    return UPDATE_CHANNEL_STABLE


def _format_update(release: ReleaseInfo | None, channel: str) -> str:
    current = html.escape(get_app_version())
    if release is None:
        return (
            '<div class="btb-update-status is-current">'
            "<strong>当前已是所选频道的最新版本</strong>"
            f"<span>当前版本 v{current} · {html.escape(channel)}</span>"
            "</div>"
        )

    release_type = "测试版" if release.prerelease else "稳定版"
    return (
        '<div class="btb-update-status is-available">'
        "<strong>发现可用更新</strong>"
        f"<span>v{current} → v{html.escape(release.version)}（{release_type}）</span>"
        f'<a href="{html.escape(release.html_url)}" target="_blank">查看 GitHub 发布说明</a>'
        "</div>"
    )


def _update_script_name() -> str:
    return "update.bat" if os.name == "nt" else "update.sh"


def _runtime_mode() -> str:
    if getattr(sys, "frozen", False):
        return "bundled"
    if sys.argv and sys.argv[0].endswith(".py"):
        return "source"
    if (Path(EXE_PATH) / "pyproject.toml").exists():
        return "source"
    return "pip"


def _source_update_hint() -> str:
    repo_dir = html.escape(EXE_PATH)
    return (
        "当前是<strong>源码运行</strong>。"
        f"<br>请先同步源码目录 <code>{repo_dir}</code>，再重新安装依赖或重新启动。"
        "<br>如果你是用 Git 拉取的仓库，通常执行 <code>git pull</code> 即可。"
    )


def _pip_update_hint(channel: str) -> str:
    command = f"python -m pip install -U {PACKAGE_NAME}"
    if channel != UPDATE_CHANNEL_STABLE:
        command += " --pre"
    return f"当前是 <strong>pip</strong> 安装版本。<br>请在终端执行：<code>{html.escape(command)}</code>"


def _bundled_update_hint() -> str:
    script_name = _update_script_name()
    script_path = html.escape(os.path.join(EXE_PATH, script_name))
    system = platform.system().lower()
    if system == "windows":
        usage = "关闭程序后，双击运行该 bat，它会自动下载最新版本并覆盖当前目录。"
    else:
        usage = "关闭程序后，在终端执行该脚本，它会自动下载最新版本并覆盖当前目录。"
    return (
        "当前是 <strong>打包版</strong>。"
        f"<br>请使用安装目录中的 <code>{script_path}</code> 完成更新。"
        f"<br>{usage}"
    )


def _update_hint(channel: str) -> str:
    mode = _runtime_mode()
    if mode == "bundled":
        return _bundled_update_hint()
    if mode == "source":
        return _source_update_hint()
    return _pip_update_hint(channel)


def _check_updates(channel: str | None = None):
    channel = UPDATE_CHANNEL_STABLE
    ConfigDB.insert(UPDATE_CHANNEL_KEY, channel)
    try:
        release = fetch_update(get_app_version(), channel)
    except (UpdateError, requests.RequestException, ValueError) as exc:
        message = (
            '<div class="btb-update-status is-error">'
            "<strong>暂时无法检查更新</strong>"
            f"<span>{html.escape(str(exc))}</span>"
            "</div>"
        )
        return message, None, gr.update(value=_update_hint(channel))

    return (
        _format_update(release, channel),
        release.to_dict() if release else None,
        gr.update(value=_update_hint(channel)),
    )


def load_update_check():
    return _check_updates(_saved_channel())


def run_stable_update_check():
    return _check_updates(UPDATE_CHANNEL_STABLE)


def update_tab(demo: gr.Blocks):
    status = gr.HTML(
        '<div class="btb-update-status"><strong>正在检查更新…</strong></div>'
    )
    release_state = gr.State(None)

    with gr.Row():
        stable_button = gr.Button("检查更新", variant="secondary")

    notice = gr.Markdown(_update_hint(_saved_channel()))

    check_outputs = [status, release_state, notice]
    demo.load(load_update_check, outputs=check_outputs)
    stable_button.click(run_stable_update_check, outputs=check_outputs)
