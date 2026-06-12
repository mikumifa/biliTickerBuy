import datetime
import html
import json
import os
import platform
import time
import uuid

import gradio as gr
import requests
from gradio import SelectData
from loguru import logger

from task.buy import buy_new_terminal
from util import (
    ConfigDB,
    Endpoint,
    GlobalStatusInstance,
    LOG_DIR,
    build_public_url,
    time_service,
)

BEIJING_TZ = datetime.timezone(datetime.timedelta(hours=8), name="Asia/Shanghai")


def withTimeString(string):
    return (
        f"{datetime.datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}: {string}"
    )


def _build_task_log_path(filename: str) -> str:
    filename_only = os.path.splitext(os.path.basename(filename))[0]
    safe_name = "".join(
        ch if ch.isalnum() or ch in "-_." else "_" for ch in filename_only
    )
    safe_name = safe_name.strip("._") or "task"
    return os.path.join(LOG_DIR, f"{safe_name}_{uuid.uuid4().hex[:8]}.log")


def _parse_sale_start(value) -> datetime.datetime | None:
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(value, tz=BEIJING_TZ)
    if isinstance(value, str) and value.strip():
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.datetime.strptime(value, fmt).replace(tzinfo=BEIJING_TZ)
            except ValueError:
                continue
    return None


def _preview_value(value) -> str:
    if value in (None, "", []):
        return "-"
    if isinstance(value, list):
        return "、".join(str(item) for item in value) if value else "-"
    return str(value)


def _format_price_cents(value) -> str:
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return _preview_value(value)
    return f"¥{amount / 100:.2f}"


def _render_ticket_preview(config: dict) -> str:
    buyer_info = config.get("buyer_info") or []
    buyer_names = [
        item.get("name", "未命名购票人")
        for item in buyer_info
        if isinstance(item, dict)
    ]
    deliver_info = config.get("deliver_info") or {}
    deliver_name = deliver_info.get("name", "")
    deliver_tel = deliver_info.get("tel", "")
    deliver_addr = deliver_info.get("addr", "")
    delivery_summary = _preview_value(
        " / ".join(part for part in [deliver_name, deliver_tel, deliver_addr] if part)
    )
    purchase_summary = "{0} * {1}".format(
        _preview_value(config.get("count")),
        _format_price_cents(config.get("pay_money")),
    )

    items = [
        ("账号", _preview_value(config.get("username"))),
        ("项目 ID", _preview_value(config.get("project_id"))),
        ("场次 ID", _preview_value(config.get("screen_id"))),
        ("票档 ID", _preview_value(config.get("sku_id"))),
        ("票数 * 单价", purchase_summary),
        ("起售时间", _preview_value(config.get("sale_start"))),
        ("联系人", _preview_value(config.get("buyer"))),
        ("联系电话", _preview_value(config.get("tel"))),
        ("实名购票人", _preview_value(buyer_names)),
    ]
    item_html = "".join(
        (
            '<div class="btb-mini-card">'
            f"<strong>{html.escape(label)}</strong>"
            f"<span>{html.escape(value)}</span>"
            "</div>"
        )
        for label, value in items
    )
    return f"""
    <div class="btb-ticket-panel">
        <div class="btb-ticket-panel__head">
            <div>
                <div class="btb-card-head__eyebrow">Config Preview</div>
                <h4>抢票配置预览</h4>
            </div>
            <span class="btb-badge-pink">已解析</span>
        </div>
        <div class="btb-mini-grid btb-mini-grid--triple">{item_html}</div>
        <div class="btb-mini-card btb-ticket-panel__delivery">
            <strong>收货信息</strong>
            <span>{html.escape(delivery_summary)}</span>
        </div>
    </div>
    """


def go_start_tab(demo: gr.Blocks, server_name: str | None = None):
    auto_fill_time_default = ConfigDB.get("autoFillTime")
    if auto_fill_time_default is None:
        auto_fill_time_default = True

    with gr.Column(elem_classes="btb-page-section"):
        with gr.Column(elem_classes="btb-card btb-card-sky btb-layout-card"):
            with gr.Row(elem_classes="!items-stretch !gap-3"):
                upload_ui = gr.Files(
                    label="上传多个配置文件,每一个上传的文件都会启动一个抢票程序",
                    file_count="multiple",
                    scale=5,
                )
                with gr.Column(scale=4):
                    ticket_ui = gr.HTML(
                        value=_render_ticket_preview({}),
                        visible=True,
                    )
            with gr.Column(elem_classes="btb-card btb-card-sky btb-layout-card"):
                gr.HTML(
                    """
                    <div class="btb-card-head">
                        <div>
                            <h4>选择抢票时间</h3>
                            <p>
                                程序已经提前帮你校准时间，请设置成<strong>开票时间</strong>。
                                切勿设置为开票前时间，否则有封号风险。
                                这里的时间按<strong>北京时间（UTC+8）</strong>填写。
                            </p>
                        </div>
                        <span class="btb-badge-pink">精确到秒</span>
                    </div>
                    """,
                    label="选择抢票的时间",
                )
                gr.HTML(
                    """
                    <div class="btb-time-picker-card">
                        <label class="btb-time-picker-card__label" for="datetime">
                            抢票开始时间
                        </label>
                        <input
                            type="datetime-local"
                            id="datetime"
                            name="datetime"
                            step="1"
                            class="btb-native-datetime-input"
                        >
                    </div>
                    """
                )
            with gr.Row(elem_classes="!justify-end"):
                auto_fill_time_btn = gr.Button(
                    "自动填写抢票时间",
                    elem_classes="btb-soft-button",
                    scale=0,
                    min_width=220,
                )

        with gr.Row(elem_classes="btb-inline-actions !justify-end"):
            interval_ui = gr.Number(
                label="抢票间隔",
                value=1000,
                minimum=1,
                info="设置抢票请求之间的时间间隔（单位：毫秒），建议不要设置太小",
            )
            choices = ["网页"]
            if platform.system() == "Windows":
                choices.insert(0, "终端")
            terminal_ui = gr.Radio(
                label="日志显示方式",
                choices=choices,
                value=choices[0],
                info="日志显示的方式,非windows用戶只支持網頁",
                type="value",
                interactive=True,
            )

    def upload(filepath):
        try:
            with open(filepath[0], "r", encoding="utf-8") as file:
                content = json.load(file)
            return gr.update(value=_render_ticket_preview(content), visible=True)
        except Exception as e:
            return gr.update(
                value=(
                    '<div class="btb-card-note">配置预览失败：'
                    f"{html.escape(str(e))}</div>"
                ),
                visible=True,
            )

    def file_select_handler(select_data: SelectData, files):
        file_label = files[select_data.index]
        try:
            with open(file_label, "r", encoding="utf-8") as file:
                content = json.load(file)
            return _render_ticket_preview(content)
        except Exception as e:
            return (
                f'<div class="btb-card-note">配置预览失败：{html.escape(str(e))}</div>'
            )

    def auto_fill_time(files):
        if not files:
            gr.Warning("请先上传至少一个抢票配置文件。")
            return ""

        sale_start_items: list[tuple[str, datetime.datetime]] = []
        adjusted_now = datetime.datetime.fromtimestamp(
            time.time() + time_service.get_timeoffset(),
            tz=BEIJING_TZ,
        )

        for filepath in files:
            with open(filepath, "r", encoding="utf-8") as file:
                config = json.load(file)

            sale_start = _parse_sale_start(
                config.get("sale_start", config.get("saleStart"))
            )
            if sale_start is None:
                raise gr.Error("缺少有效的 sale_start，请重新生成该配置。")
            sale_start_items.append((os.path.basename(filepath), sale_start))

        latest_sale_start = max(sale_start for _, sale_start in sale_start_items)
        unique_sale_starts = sorted({sale_start for _, sale_start in sale_start_items})
        if latest_sale_start <= adjusted_now:
            gr.Warning("已经过起售时间，不需要填写抢票时间。\n")
            return ""

        autofill_value = latest_sale_start.strftime("%Y-%m-%dT%H:%M:%S")
        if len(unique_sale_starts) == 1:
            gr.Info("已自动填写抢票时间。\n")
            return autofill_value

        gr.Warning(
            "抢票的起始时间不一样，已自动填写为最晚的起售时间，确保所有票档届时都已开始抢票。\n"
        )
        return autofill_value

    def try_assign_endpoint(endpoint_url, payload):
        try:
            response = requests.post(f"{endpoint_url}/buy", json=payload, timeout=5)
            if response.status_code == 200:
                return True
            if response.status_code == 409:
                logger.info(f"{endpoint_url} 已经占用")
                return False
            return False
        except Exception as e:
            logger.exception(e)
            raise e

    def split_proxies(https_proxy_list: list[str], task_num: int) -> list[list[str]]:
        assigned_proxies: list[list[str]] = [[] for _ in range(task_num)]
        for i, proxy in enumerate(https_proxy_list):
            assigned_proxies[i % task_num].append(proxy)
        return assigned_proxies

    def start_go(files, time_start, interval, terminal_ui):
        if not files:
            return [gr.update(value=withTimeString("未提交抢票配置"), visible=True)]
        yield [
            gr.update(value=withTimeString("开始多开抢票,详细查看终端"), visible=True)
        ]

        master_endpoint_url = build_public_url(demo.local_url or "", server_name)
        endpoints = GlobalStatusInstance.available_endpoints()
        endpoints_next_idx = 0

        https_proxys = ConfigDB.get("https_proxy") or ""
        https_proxy_list = ["none"] + https_proxys.split(",")
        assigned_proxies: list[list[str]] = []
        assigned_proxies_next_idx = 0

        audio_path = ConfigDB.get("audioPath") or ""
        hide_random_message = ConfigDB.get("hideRandomMessage")
        if hide_random_message is None:
            hide_random_message = True

        for idx, filename in enumerate(files):
            with open(filename, "r", encoding="utf-8") as file:
                content = file.read()
            filename_only = os.path.basename(filename)
            logger.info(f"启动 {filename_only}")

            while endpoints_next_idx < len(endpoints) and terminal_ui == "网页":
                success = try_assign_endpoint(
                    endpoints[endpoints_next_idx].endpoint,
                    payload={
                        "force": True,
                        "train_info": content,
                        "time_start": time_start,
                        "interval": interval,
                        "audio_path": audio_path,
                        "pushplusToken": ConfigDB.get("pushplusToken"),
                        "serverchanKey": ConfigDB.get("serverchanKey"),
                        "serverchan3ApiUrl": ConfigDB.get("serverchan3ApiUrl"),
                        "barkToken": ConfigDB.get("barkToken"),
                        "ntfy_url": ConfigDB.get("ntfyUrl"),
                        "ntfy_username": ConfigDB.get("ntfyUsername"),
                        "ntfy_password": ConfigDB.get("ntfyPassword"),
                    },
                )
                endpoints_next_idx += 1
                if success:
                    break
            else:
                if assigned_proxies == []:
                    left_task_num = len(files) - idx
                    assigned_proxies = split_proxies(https_proxy_list, left_task_num)

                log_file_path = _build_task_log_path(filename_only)
                logger.info(f"任务 {filename_only} 的日志文件：{log_file_path}")
                proc = buy_new_terminal(
                    endpoint_url=master_endpoint_url or demo.local_url,
                    tickets_info=content,
                    time_start=time_start,
                    interval=interval,
                    audio_path=audio_path,
                    pushplusToken=ConfigDB.get("pushplusToken"),
                    serverchanKey=ConfigDB.get("serverchanKey"),
                    serverchan3ApiUrl=ConfigDB.get("serverchan3ApiUrl"),
                    barkToken=ConfigDB.get("barkToken"),
                    ntfy_url=ConfigDB.get("ntfyUrl"),
                    ntfy_username=ConfigDB.get("ntfyUsername"),
                    ntfy_password=ConfigDB.get("ntfyPassword"),
                    https_proxys=",".join(assigned_proxies[assigned_proxies_next_idx]),
                    terminal_ui=terminal_ui,
                    show_random_message=not hide_random_message,
                    server_name=server_name,
                    log_file_path=log_file_path,
                )
                GlobalStatusInstance.register_task_log(
                    title=filename_only,
                    mode=terminal_ui,
                    log_file=log_file_path,
                    pid=proc.pid,
                )
                assigned_proxies_next_idx += 1
        gr.Info("正在启动，请等待抢票页面弹出。")

    upload_ui.upload(fn=upload, inputs=upload_ui, outputs=ticket_ui)

    def maybe_auto_fill_time(files):
        if not ConfigDB.get("autoFillTime"):
            return ""
        return auto_fill_time(files)

    upload_ui.clear(
        fn=lambda x: gr.update("", visible=False),
        inputs=upload_ui,
        outputs=ticket_ui,
    )
    upload_ui.select(file_select_handler, upload_ui, ticket_ui)

    go_btn = gr.Button(
        "开始抢票",
        elem_classes="btb-strong-button",
    )

    _time_tmp = gr.Textbox(visible=False)
    _auto_fill_time_tmp = gr.Textbox(visible=False)
    auto_fill_time_btn.click(
        fn=auto_fill_time,
        inputs=upload_ui,
        outputs=_auto_fill_time_tmp,
    ).then(
        fn=None,
        inputs=_auto_fill_time_tmp,
        outputs=_time_tmp,
        js="""
        (value) => {
            const input = document.getElementById("datetime");
            if (input) {
                input.value = value || "";
            }
            return value || "";
        }
        """,
    )
    upload_ui.upload(
        fn=maybe_auto_fill_time,
        inputs=upload_ui,
        outputs=_auto_fill_time_tmp,
    ).then(
        fn=None,
        inputs=_auto_fill_time_tmp,
        outputs=_time_tmp,
        js="""
        (value) => {
            const input = document.getElementById("datetime");
            if (input) {
                input.value = value || "";
            }
            return value || "";
        }
        """,
    )
    go_btn.click(
        fn=None,
        inputs=None,
        outputs=_time_tmp,
        js='(x) => document.getElementById("datetime").value',
    )

    _report_tmp = gr.Button(visible=False)
    _report_tmp.api_info
    _end_point_tinput = gr.Textbox(visible=False)

    def report(end_point, detail):
        now = time.time()
        GlobalStatusInstance.endpoint_details[end_point] = Endpoint(
            endpoint=end_point, detail=detail, update_at=now
        )

    _report_tmp.click(
        fn=report,
        inputs=[_end_point_tinput, _time_tmp],
        api_name="report",
    )

    def tick():
        return f"当前时间戳：{int(time.time())}"

    timer = gr.Textbox(label="定时更新", interactive=False, visible=False)
    demo.load(fn=tick, inputs=None, outputs=timer, every=1)

    @gr.render(inputs=timer)
    def show_split(text):
        endpoints = GlobalStatusInstance.available_endpoints()
        if len(endpoints) != 0:
            gr.Markdown("## 当前运行终端列表")
            for endpoint in endpoints:
                link = html.escape(endpoint.endpoint, quote=True)
                detail = html.escape(endpoint.detail)
                gr.HTML(
                    f"""
                    <div class="btb-inline-actions !justify-end">
                        <a
                            class="btb-soft-button"
                            href="{link}"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            点击跳转 🚀 {link} {detail}
                        </a>
                    </div>
                    """
                )

    go_btn.click(
        fn=start_go,
        inputs=[upload_ui, _time_tmp, interval_ui, terminal_ui],
    )


def go_settings_tab():
    def get_latest_proxy():
        return ConfigDB.get("https_proxy") or ""

    def input_https_proxy(_https_proxy):
        ConfigDB.insert("https_proxy", _https_proxy)
        return gr.update(ConfigDB.get("https_proxy"))

    def test_proxy_connectivity(proxy_string, timeout):
        try:
            from util.ProxyTester import test_proxy_connectivity

            if not proxy_string or proxy_string.strip() == "":
                proxy_string = "none"
            return test_proxy_connectivity(proxy_string, int(timeout))
        except Exception as e:
            return f"❌ 测试过程中发生错误: {str(e)}"

    def inner_input_serverchan(x):
        ConfigDB.insert("serverchanKey", x)
        return gr.update(value=ConfigDB.get("serverchanKey"))

    def inner_input_serverchan3(x):
        ConfigDB.insert("serverchan3ApiUrl", x)
        return gr.update(value=ConfigDB.get("serverchan3ApiUrl"))

    def inner_input_pushplus(x):
        ConfigDB.insert("pushplusToken", x)
        return gr.update(value=ConfigDB.get("pushplusToken"))

    def inner_input_bark(x):
        ConfigDB.insert("barkToken", x)
        return gr.update(value=ConfigDB.get("barkToken"))

    def inner_input_ntfy(x):
        ConfigDB.insert("ntfyUrl", x)
        return gr.update(value=ConfigDB.get("ntfyUrl"))

    def inner_input_ntfy_username(x):
        ConfigDB.insert("ntfyUsername", x)
        return gr.update(value=ConfigDB.get("ntfyUsername"))

    def inner_input_ntfy_password(x):
        ConfigDB.insert("ntfyPassword", x)
        return gr.update(value=ConfigDB.get("ntfyPassword"))

    def inner_input_audio_path(x):
        if not x:
            ConfigDB.insert("audioPath", "")
            return gr.update(value=None)

        ConfigDB.insert("audioPath", x)
        gr.Info("提示音已保存。")
        return gr.update(value=ConfigDB.get("audioPath"))

    def test_terminal_audio():
        audio_path = ConfigDB.get("audioPath")
        if not audio_path:
            return "错误: 请先上传提示音"

        try:
            from util.AudioUtil import AudioNotifier

            AudioNotifier(audio_path).send_message(
                "🎫 抢票测试",
                "这是一条终端版音频测试消息",
            )
            return "✅ 终端音频通知: 测试播放成功"
        except Exception as e:
            logger.exception(e)
            return f"❌ 终端音频通知: 测试播放失败 - {str(e)}"

    def test_all_push():
        try:
            from util.Notifier import NotifierManager

            return NotifierManager.test_all_notifiers(include_audio=False)
        except Exception as e:
            logger.exception(e)
            return f"错误: 测试过程中发生异常 - {str(e)}"

    def test_ntfy_connection():
        url = ConfigDB.get("ntfyUrl")
        username = ConfigDB.get("ntfyUsername")
        password = ConfigDB.get("ntfyPassword")

        if not url:
            return "错误: 请先设置Ntfy服务器URL"

        from util import NtfyUtil

        success, message = NtfyUtil.test_connection(url, username, password)
        return f"成功: {message}" if success else f"错误: {message}"

    def update_hide_random_message(value):
        ConfigDB.insert("hideRandomMessage", value)
        return gr.update(value=ConfigDB.get("hideRandomMessage"))

    def update_auto_fill_time(value):
        ConfigDB.insert("autoFillTime", value)
        return gr.update(value=ConfigDB.get("autoFillTime"))

    hide_random_message_default = ConfigDB.get("hideRandomMessage")
    if hide_random_message_default is None:
        hide_random_message_default = True
    auto_fill_time_default = ConfigDB.get("autoFillTime")
    if auto_fill_time_default is None:
        auto_fill_time_default = True

    with gr.Column(elem_classes="btb-page-section"):
        with gr.Column(elem_classes="btb-card btb-layout-card"):
            gr.Markdown(
                """
                <div class="flex flex-wrap items-start justify-between gap-3">
                    <div>
                        <p class="text-base font-semibold text-slate-900">高级设置</p>
                        <p class="mt-1 text-sm leading-6 text-slate-600">
                            这里包含代理、成功提醒、提示音和杂项选项，进入标签页后会直接显示。
                        </p>
                    </div>
                    <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600">
                        可选配置
                    </span>
                </div>
                """,
                elem_classes="!p-0",
            )
        with gr.Tabs(elem_classes="btb-top-tabs"):
            with gr.Tab("代理设置"):
                with gr.Column(elem_classes="btb-card btb-layout-card"):
                    gr.Markdown("### 填写你的代理服务器[可选]")
                    gr.Markdown(
                        """
                        > **注意**：

                        填写代理服务器地址后，程序在使用这个配置文件后会在出现风控后后根据代理服务器去访问哔哩哔哩的抢票接口。

                        抢票前请确保代理服务器已经开启，并且可以正常访问哔哩哔哩的抢票接口。

                        支持 HTTP/HTTPS/SOCKS 代理。
                        """
                    )
                    https_proxy_ui = gr.Textbox(
                        label="填写抢票时候的代理服务器地址，使用逗号隔开|输入完成后，回车键保存",
                        info="例如： http://127.0.0.1:8080,https://127.0.0.1:8081,socks5://127.0.0.1:1080",
                        value=get_latest_proxy(),
                    )
                    test_proxy_btn = gr.Button(
                        "🔍 测试代理连通性",
                        elem_classes="btb-soft-button",
                    )
                    test_timeout_ui = gr.Number(
                        label="测试代理超时时间(秒)",
                        value=10,
                        minimum=5,
                        maximum=60,
                        step=1,
                    )
                    test_result_ui = gr.Textbox(
                        label="测试结果",
                        lines=10,
                        max_lines=15,
                        interactive=False,
                        placeholder="点击上方按钮开始测试代理连通性...",
                    )

            with gr.Tab("音乐设置"):
                with gr.Column(elem_classes="btb-card btb-layout-card"):
                    gr.Markdown("### 配置抢票成功后播放音乐[可选]")
                    gr.Markdown(
                        "推荐上传 WAV。若上传 MP3、FLAC、M4A、OGG 等格式，请先在系统中安装 "
                        "`ffmpeg/ffprobe`；如果安装时报错，也可以先前往 "
                        "https://cloudconvert.com/wav-converter 转成 WAV 后再上传。"
                    )
                    audio_path_ui = gr.Audio(
                        label="上传提示声音",
                        type="filepath",
                        loop=True,
                        value=(ConfigDB.get("audioPath") or None),
                    )
                    test_audio_button = gr.Button(
                        "测试终端播放",
                        elem_classes="btb-soft-button",
                    )
                    test_audio_result = gr.Textbox(
                        label="音乐测试结果",
                        interactive=False,
                    )

            with gr.Tab("推送设置"):
                with gr.Column(elem_classes="btb-card btb-layout-card"):
                    gr.Markdown("### 配置抢票推送消息[可选]")
                    gr.Markdown(
                        """
                        🗨️ **抢票成功提醒**

                        > 你需要去对应的网站获取 key 或 token，然后填入下面的输入框  
                        > [Server酱<sup>Turbo</sup>](https://sct.ftqq.com/sendkey) | [pushplus](https://www.pushplus.plus/uc.html) | [Server酱<sup>3</sup>](https://sc3.ft07.com/sendkey) | [ntfy](https://ntfy.sh/) | [Bark](https://bark.day.app/)  
                        > 留空以不启用提醒功能

                        ### 🔍 推送服务对比

                        | 服务     | 优点                               | 缺点                            |
                        |----------|------------------------------------|---------------------------------|
                        | Server酱<sup>Turbo</sup> | 简单易用，微信推送              | 微信推送很难看到 |
                        | pushplus | 简单易用，微信推送| 微信推送很难看到               |
                        | Server酱<sup>3</sup> | APP推送，有中文文档              | 配置复杂 |
                        | ntfy     | APP推送, 功能强大, 支持长期响铃 | 配置复杂，需要手动搭建或注册公网地址 |
                        | Bark     | iOS通知推送，配置简单，无视静音和勿扰模式，支持APP跳转 | 仅支持iOS设备 |

                        ✅ 推荐：初次使用建议选择 **pushplus** 或 **Server酱ᵀᵘʳᵇᵒ**，配置最简单  
                        🍎 iOS用户推荐使用 **Bark**，通知效果最佳  
                        🛠️ 追求高度自由/有自建服务器/需要在抢票成功时通过手机播放铃声时，建议用 **ntfy** 或 **Server酱³**
                        """
                    )
                    serverchan_ui = gr.Textbox(
                        value=(ConfigDB.get("serverchanKey") or ""),
                        label="Server酱ᵀᵘʳᵇᵒ的SendKey｜输入完成后，回车键保存",
                        interactive=True,
                        info="https://sct.ftqq.com/",
                    )
                    serverchan3_ui = gr.Textbox(
                        value=(ConfigDB.get("serverchan3ApiUrl") or ""),
                        label="Server酱³的API URL｜输入完成后，回车键保存",
                        interactive=True,
                        info="https://sc3.ft07.com/",
                    )
                    pushplus_ui = gr.Textbox(
                        value=(ConfigDB.get("pushplusToken") or ""),
                        label="PushPlus的Token｜输入完成后，回车键保存",
                        interactive=True,
                        info="https://www.pushplus.plus/",
                    )
                    bark_ui = gr.Textbox(
                        value=(ConfigDB.get("barkToken") or ""),
                        label="Bark的Token｜输入完成后，回车键保存",
                        interactive=True,
                        info='iOS Bark App的"服务器"页面获取，例如: jmGYK*****(并非Device Token)；自托管服务请输入完整推送地址，例如: https://bark.example.app/jmGYK*****',
                    )

                    with gr.Column(elem_classes="btb-card btb-layout-card"):
                        gr.Markdown("#### Ntfy配置")
                        ntfy_ui = gr.Textbox(
                            value=(ConfigDB.get("ntfyUrl") or ""),
                            label="Ntfy服务器URL｜输入完成后，回车键保存",
                            interactive=True,
                            info="例如: https://ntfy.sh/your-topic",
                        )

                        with gr.Column(elem_classes="btb-card btb-layout-card"):
                            gr.Markdown("#### Ntfy认证配置[可选]")
                            with gr.Row(elem_classes="btb-inline-actions !justify-end"):
                                ntfy_username_ui = gr.Textbox(
                                    value=(ConfigDB.get("ntfyUsername") or ""),
                                    label="Ntfy用户名",
                                    interactive=True,
                                    info="如果你的Ntfy服务器需要认证",
                                )
                                ntfy_password_ui = gr.Textbox(
                                    value=(ConfigDB.get("ntfyPassword") or ""),
                                    label="Ntfy密码",
                                    interactive=True,
                                    type="password",
                                )
                            test_ntfy_button = gr.Button(
                                "测试Ntfy连接",
                                elem_classes="btb-soft-button",
                            )
                            test_ntfy_result = gr.Textbox(
                                label="测试结果",
                                interactive=False,
                            )

                    with gr.Column(
                        elem_classes="btb-card btb-card-sky btb-layout-card"
                    ):
                        test_all_push_button = gr.Button(
                            "🧪 测试所有推送",
                            elem_classes="!rounded-xl !border !border-slate-300 !bg-white !text-slate-900 !shadow-sm hover:!bg-slate-100 !transition",
                        )
                        test_push_result = gr.Textbox(
                            label="推送测试结果",
                            interactive=False,
                        )

            with gr.Tab("杂项设置"):
                with gr.Column(elem_classes="btb-card btb-layout-card"):
                    gr.Markdown("### 杂项配置")
                    auto_fill_time_ui = gr.Checkbox(
                        label="默认自动填写抢票时间",
                        value=auto_fill_time_default,
                        info="开启后，上传抢票配置文件时会自动按票档起售时间回填抢票时间。",
                    )
                    show_random_message_ui = gr.Checkbox(
                        label="关闭群友语录",
                        value=hide_random_message_default,
                        info="关闭后，抢票失败时将不再显示有趣的语录",
                    )

    https_proxy_ui.submit(
        fn=input_https_proxy, inputs=https_proxy_ui, outputs=https_proxy_ui
    )
    test_proxy_btn.click(
        fn=test_proxy_connectivity,
        inputs=[https_proxy_ui, test_timeout_ui],
        outputs=test_result_ui,
    )

    serverchan_ui.submit(
        fn=inner_input_serverchan, inputs=serverchan_ui, outputs=serverchan_ui
    )
    serverchan3_ui.submit(
        fn=inner_input_serverchan3,
        inputs=serverchan3_ui,
        outputs=serverchan3_ui,
    )
    pushplus_ui.submit(fn=inner_input_pushplus, inputs=pushplus_ui, outputs=pushplus_ui)
    bark_ui.submit(fn=inner_input_bark, inputs=bark_ui, outputs=bark_ui)
    ntfy_ui.submit(fn=inner_input_ntfy, inputs=ntfy_ui, outputs=ntfy_ui)
    ntfy_username_ui.submit(
        fn=inner_input_ntfy_username,
        inputs=ntfy_username_ui,
        outputs=ntfy_username_ui,
    )
    ntfy_password_ui.submit(
        fn=inner_input_ntfy_password,
        inputs=ntfy_password_ui,
        outputs=ntfy_password_ui,
    )
    audio_path_ui.upload(
        fn=inner_input_audio_path,
        inputs=audio_path_ui,
        outputs=audio_path_ui,
    )
    show_random_message_ui.change(
        fn=update_hide_random_message,
        inputs=show_random_message_ui,
        outputs=show_random_message_ui,
    )
    auto_fill_time_ui.change(
        fn=update_auto_fill_time,
        inputs=auto_fill_time_ui,
        outputs=auto_fill_time_ui,
    )
    test_audio_button.click(
        fn=test_terminal_audio,
        inputs=[],
        outputs=test_audio_result,
    )
    test_ntfy_button.click(
        fn=test_ntfy_connection,
        inputs=[],
        outputs=test_ntfy_result,
    )
    test_all_push_button.click(
        fn=test_all_push,
        inputs=[],
        outputs=test_push_result,
    )
