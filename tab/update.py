"""Update center UI."""

from __future__ import annotations

import html
from pathlib import Path

import gradio as gr
import requests

from app_update import (
    UPDATE_CHANNELS,
    UPDATE_CHANNEL_STABLE,
    ReleaseInfo,
    UpdateError,
    download_update_package,
    fetch_update,
)
from app_version import get_app_version
from util import ConfigDB, EXE_PATH

UPDATE_CHANNEL_KEY = "update_channel"


def _saved_channel() -> str:
    channel = ConfigDB.get(UPDATE_CHANNEL_KEY)
    return channel if channel in UPDATE_CHANNELS else UPDATE_CHANNEL_STABLE


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


def check_updates(channel: str):
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
        return message, None, gr.update(visible=False)

    return (
        _format_update(release, channel),
        release.to_dict() if release else None,
        gr.update(visible=release is not None),
    )


def download_update(release_data: dict | None):
    if not release_data:
        return gr.update(value=None, visible=False), "请先检查更新。"

    try:
        release = ReleaseInfo.from_dict(release_data)
        download_dir = Path(EXE_PATH) / "updates" / release.tag_name
        package_path = download_update_package(release, download_dir)
    except (UpdateError, requests.RequestException, OSError, ValueError) as exc:
        return gr.update(value=None, visible=False), f"下载失败：{exc}"

    return (
        gr.update(value=str(package_path), visible=True),
        "更新包下载完成且 SHA-256 校验通过。程序不会自动退出或覆盖文件，"
        "请结束正在执行的任务后，再解压并替换旧版本。",
    )


def update_tab(demo: gr.Blocks):
    channel = gr.Radio(
        choices=list(UPDATE_CHANNELS),
        value=_saved_channel(),
        label="更新频道",
        info="稳定版会跳过 GitHub prerelease；测试版会同时接收预发布版本。",
    )
    status = gr.HTML(
        '<div class="btb-update-status"><strong>正在检查更新…</strong></div>'
    )
    release_state = gr.State(None)

    with gr.Row():
        check_button = gr.Button("立即检查", variant="secondary")
        download_button = gr.Button(
            "下载并校验更新包", variant="primary", visible=False
        )

    notice = gr.Markdown(
        "更新不会静默安装。只有点击下载后才会获取更新包，且校验通过后仍需由你确认并手动替换。"
    )
    package_file = gr.File(label="已验证的更新包", visible=False, interactive=False)

    check_outputs = [status, release_state, download_button]
    demo.load(check_updates, inputs=channel, outputs=check_outputs)
    check_button.click(check_updates, inputs=channel, outputs=check_outputs)
    channel.change(check_updates, inputs=channel, outputs=check_outputs)
    download_button.click(
        download_update,
        inputs=release_state,
        outputs=[package_file, notice],
    )
