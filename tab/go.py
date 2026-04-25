import datetime
import json
import os
import platform
import time

import gradio as gr
import requests
import util
from gradio import SelectData
from loguru import logger

from task.buy import buy_new_terminal
from util import ConfigDB
from util import Endpoint
from util import GlobalStatusInstance
from util import time_service


def withTimeString(string):
    return f"{datetime.datetime.now()}: {string}"


def _parse_sale_start(value) -> datetime.datetime | None:
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(value)
    if isinstance(value, str) and value.strip():
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def _fetch_project_detail(project_id: int) -> dict:
    response = util.main_request.get(
        url=(
            "https://show.bilibili.com/api/ticket/project/getV2"
            f"?version=134&id={project_id}&project_id={project_id}&requestSource=pc-new"
        )
    )
    payload = response.json()
    errno = payload.get("errno", payload.get("code"))
    if errno != 0:
        raise RuntimeError(payload.get("msg", payload.get("message", "未知错误")))
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("项目详情为空")
    return data


def _resolve_sale_start(project_detail: dict, sku_id: int) -> datetime.datetime | None:
    for screen in project_detail.get("screen_list", []):
        if not isinstance(screen, dict):
            continue
        for ticket in screen.get("ticket_list", []):
            if not isinstance(ticket, dict):
                continue
            if int(ticket.get("id", 0)) != sku_id:
                continue
            sale_start = _parse_sale_start(ticket.get("sale_start"))
            if sale_start is None:
                sale_start = _parse_sale_start(ticket.get("saleStart"))
            return sale_start
    return None


def _render_go_steps(
    current: str,
    *,
    uploaded: bool = False,
    scheduled: bool = False,
    launched: bool = False,
) -> str:
    def step(label: str, number: int, key: str, done: bool) -> str:
        classes = ["btb-step-strip__item"]
        if done:
            classes.append("is-done")
        elif key == current:
            classes.append("is-active")
        return (
            f'<div class="{" ".join(classes)}">'
            f"<span>{number}</span>"
            f"<strong>{label}</strong>"
            "</div>"
        )

    return f"""
    <div class="btb-step-strip">
        {step("上传配置", 1, "upload", uploaded)}
        {step("设置时间", 2, "schedule", scheduled)}
        {step("开始运行", 3, "launch", launched)}
    </div>
    """


def _render_go_step_update(
    *,
    uploaded: bool,
    scheduled: bool,
    launched: bool = False,
):
    current = "upload"
    if launched:
        current = "launch"
    elif uploaded and scheduled:
        current = "launch"
    elif uploaded:
        current = "schedule"
    return gr.update(
        value=_render_go_steps(
            current,
            uploaded=uploaded,
            scheduled=scheduled,
            launched=launched,
        )
    )


def go_tab(demo: gr.Blocks):
    with gr.Column(elem_classes="btb-page-section"):
        gr.HTML(
            """
            <section class="btb-section-head">
                <div>
                    <div class="btb-section-head__eyebrow">STEP 02</div>
                    <h2>启动抢票任务</h2>
                    <p>上传配置文件，校准起抢时间，确认通知与代理策略后再批量启动任务。</p>
                </div>
            </section>
            """
        )
        go_step_status_ui = gr.HTML(
            value=_render_go_steps("upload", uploaded=False, scheduled=False, launched=False)
        )



        with gr.Column(elem_classes="btb-card btb-card-sky btb-layout-card"):
            gr.HTML(
                """
                <div class="btb-card-head">
                    <div>
                        <div class="btb-card-head__eyebrow">Launch</div>
                        <h3>抢票入口</h3>
                        <p>上传一个或多个配置文件，校准开抢时间后即可批量启动任务。</p>
                    </div>
                    <span class="btb-badge-blue">批量启动</span>
                </div>
                """
            )

            with gr.Row(elem_classes="btb-split-grid !items-stretch"):
                upload_ui = gr.Files(
                    label="上传配置文件",
                    file_count="multiple",
                    scale=5,
                    elem_classes="btb-upload-panel",
                )
                ticket_ui = gr.TextArea(
                    label="配置预览",
                    info="选择文件后可预览当前配置内容",
                    interactive=False,
                    visible=False,
                    scale=5,
                    elem_classes="btb-preview-panel",
                )

            time_start_ui = gr.Textbox(
                label="抢票开始时间",
                placeholder="2026-05-01 10:00:00",
                info="直接输入或点击右侧日历图标选择 · 格式 YYYY-MM-DD HH:MM:SS",
                elem_classes="btb-time-input btb-has-picker",
                elem_id="btb-time-start",
            )
            gr.HTML(
                """
                <script>
                (function(){
                    function enhance(){
                        var root=document.getElementById('btb-time-start');
                        if(!root){setTimeout(enhance,300);return;}
                        var input=root.querySelector('input[type="text"],textarea');
                        if(!input){setTimeout(enhance,300);return;}
                        if(root.dataset.enhanced) return;
                        root.dataset.enhanced='1';
                        var ghost=document.createElement('input');
                        ghost.type='datetime-local';ghost.step='1';
                        ghost.className='btb-picker-ghost';ghost.tabIndex=-1;
                        var btn=document.createElement('button');
                        btn.type='button';btn.className='btb-picker-trigger';
                        btn.title='打开日历选择器';
                        btn.innerHTML='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>';
                        var wrap=input.closest('.wrap')||input.parentElement;
                        wrap.style.position='relative';
                        wrap.appendChild(ghost);wrap.appendChild(btn);
                        btn.addEventListener('click',function(e){
                            e.preventDefault();e.stopPropagation();
                            if(input.value){
                                try{ghost.value=input.value.trim().replace(' ','T');}catch(ex){}
                            }
                            ghost.showPicker();
                        });
                        ghost.addEventListener('input',function(){
                            var v=this.value;if(!v)return;
                            var dt=v.replace('T',' ');
                            if(dt.length===16)dt+=':00';
                            var setter=Object.getOwnPropertyDescriptor(
                                Object.getPrototypeOf(input),'value'
                            ).set;
                            setter.call(input,dt);
                            input.dispatchEvent(new Event('input',{bubbles:true}));
                        });
                    }
                    if(document.readyState==='loading')
                        document.addEventListener('DOMContentLoaded',enhance);
                    else setTimeout(enhance,500);
                })();
                </script>
                """
            )

            with gr.Row(elem_classes="btb-inline-actions !justify-end"):
                auto_fill_time_btn = gr.Button(
                    "自动填充抢票时间",
                    elem_classes="btb-soft-button",
                    scale=0,
                    min_width=220,
                )

        def upload(filepath, time_start):
            try:
                with open(filepath[0], "r", encoding="utf-8") as file:
                    content = file.read()
                return [
                    gr.update(value=content, visible=True),
                    _render_go_step_update(
                        uploaded=True,
                        scheduled=bool(str(time_start or "").strip()),
                    ),
                ]
            except Exception as exc:
                return [
                    gr.update(value=str(exc), visible=True),
                    gr.update(),
                ]

        def file_select_handler(select_data: SelectData, files):
            file_label = files[select_data.index]
            try:
                with open(file_label, "r", encoding="utf-8") as file:
                    content = file.read()
                return content
            except Exception as exc:
                return str(exc)

        upload_ui.upload(
            fn=upload,
            inputs=[upload_ui, time_start_ui],
            outputs=[ticket_ui, go_step_status_ui],
        )
        upload_ui.clear(
            fn=lambda: [
                gr.update("", visible=False),
                _render_go_step_update(uploaded=False, scheduled=False),
            ],
            outputs=[ticket_ui, go_step_status_ui],
        )
        upload_ui.select(file_select_handler, upload_ui, ticket_ui)

        def auto_fill_time(files):
            if not files:
                gr.Warning("请先上传至少一个配置文件。")
                return [
                    "",
                    _render_go_step_update(uploaded=False, scheduled=False),
                ]

            sale_start_items: list[tuple[str, datetime.datetime]] = []
            adjusted_now = datetime.datetime.fromtimestamp(
                time.time() + time_service.get_timeoffset()
            )

            for filepath in files:
                with open(filepath, "r", encoding="utf-8") as file:
                    config = json.load(file)

                try:
                    project_id = int(config["project_id"])
                    sku_id = int(config["sku_id"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise gr.Error(f"{os.path.basename(filepath)} 缺少 project_id 或 sku_id") from exc

                project_detail = _fetch_project_detail(project_id)
                sale_start = _resolve_sale_start(project_detail, sku_id)
                if sale_start is None:
                    raise gr.Error(
                        f"{os.path.basename(filepath)} 没有找到对应票档的 sale_start，请重新生成配置。"
                    )
                sale_start_items.append((os.path.basename(filepath), sale_start))

            latest_sale_start = max(sale_start for _, sale_start in sale_start_items)
            unique_sale_starts = sorted({sale_start for _, sale_start in sale_start_items})
            sale_start_lines = "\n".join(
                f"{filename}: {sale_start.strftime('%Y-%m-%d %H:%M:%S')}"
                for filename, sale_start in sale_start_items
            )

            if latest_sale_start <= adjusted_now:
                gr.Warning(
                    "所有配置对应票档都已经过了起售时间，未自动填充。\n"
                    f"当前校准后时间: {adjusted_now.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"{sale_start_lines}"
                )
                return [
                    "",
                    _render_go_step_update(uploaded=True, scheduled=False),
                ]

            autofill_value = latest_sale_start.strftime("%Y-%m-%d %H:%M:%S")
            if len(unique_sale_starts) == 1:
                gr.Info(
                    "已自动填充抢票时间。\n"
                    f"自动填充值: {latest_sale_start.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"当前校准后时间: {adjusted_now.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"{sale_start_lines}"
                )
                return [
                    autofill_value,
                    _render_go_step_update(uploaded=True, scheduled=True),
                ]

            gr.Warning(
                "多个配置的起售时间不同，系统已自动填充为最晚的起售时间。\n"
                f"自动填充值: {latest_sale_start.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"当前校准后时间: {adjusted_now.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"{sale_start_lines}"
            )
            return [
                autofill_value,
                _render_go_step_update(uploaded=True, scheduled=True),
            ]

        def on_time_start_change(files, time_start):
            return _render_go_step_update(
                uploaded=bool(files),
                scheduled=bool(str(time_start or "").strip()),
            )

        with gr.Accordion(
            label="高级设置",
            open=False,
            elem_classes="btb-card btb-soft-accordion",
        ):
            gr.HTML(
                """
                <div class="btb-card-head">
                    <div>
                        <div class="btb-card-head__eyebrow">Advanced</div>
                        <h3>高级设置</h3>
                        <p>这里包含代理、成功提醒、提示音和一些杂项配置。大多数情况下不需要展开修改。</p>
                    </div>
                    <span class="btb-badge-amber">可选配置</span>
                </div>
                """
            )

            with gr.Accordion(
                label="代理配置",
                open=False,
                elem_classes="btb-card",
            ):
                gr.Markdown(
                    """
                    > 填写代理地址后，程序会在请求会员购接口时使用这些代理。
                    >
                    > 支持 HTTP / HTTPS / SOCKS，多个代理请用英文逗号分隔。
                    """
                )

                https_proxy_ui = gr.Textbox(
                    label="代理地址",
                    info="例如 http://127.0.0.1:8080,https://127.0.0.1:8081,socks5://127.0.0.1:1080",
                    value=(ConfigDB.get("https_proxy") or ""),
                )

                def input_https_proxy(_https_proxy):
                    ConfigDB.insert("https_proxy", _https_proxy)
                    return gr.update(ConfigDB.get("https_proxy"))

                https_proxy_ui.submit(
                    fn=input_https_proxy, inputs=https_proxy_ui, outputs=https_proxy_ui
                )

                test_proxy_btn = gr.Button("测试代理连通性", elem_classes="btb-soft-button")
                test_timeout_ui = gr.Number(
                    label="测试超时（秒）",
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
                    placeholder="点击按钮开始测试代理连通性...",
                )

                def test_proxy_connectivity(proxy_string, timeout):
                    try:
                        from util.ProxyTester import test_proxy_connectivity

                        if not proxy_string or proxy_string.strip() == "":
                            proxy_string = "none"
                        return test_proxy_connectivity(proxy_string, int(timeout))
                    except Exception as exc:
                        return f"测试过程中出现错误: {exc}"

                test_proxy_btn.click(
                    fn=test_proxy_connectivity,
                    inputs=[https_proxy_ui, test_timeout_ui],
                    outputs=test_result_ui,
                )

            with gr.Accordion(
                label="提示音配置",
                open=False,
                elem_classes="btb-card",
            ):
                with gr.Row():
                    audio_path_ui = gr.Audio(
                        label="上传提示音（推荐 wav）",
                        type="filepath",
                        loop=True,
                        value=(ConfigDB.get("audioPath") or None),
                    )

            with gr.Accordion(
                label="推送通知配置",
                open=False,
                elem_classes="btb-card",
            ):
                gr.Markdown(
                    """
                    支持 `Server酱 Turbo`、`pushplus`、`Server酱 3`、`ntfy` 和 `Bark`。

                    留空则不会启用对应通知方式。
                    """
                )
                serverchan_ui = gr.Textbox(
                    value=(ConfigDB.get("serverchanKey") or ""),
                    label="Server酱 Turbo SendKey",
                    interactive=True,
                    info="https://sct.ftqq.com/",
                )
                serverchan3_ui = gr.Textbox(
                    value=(ConfigDB.get("serverchan3ApiUrl") or ""),
                    label="Server酱 3 API URL",
                    interactive=True,
                    info="https://sc3.ft07.com/",
                )
                pushplus_ui = gr.Textbox(
                    value=(ConfigDB.get("pushplusToken") or ""),
                    label="PushPlus Token",
                    interactive=True,
                    info="https://www.pushplus.plus/",
                )
                bark_ui = gr.Textbox(
                    value=(ConfigDB.get("barkToken") or ""),
                    label="Bark Token 或完整地址",
                    interactive=True,
                    info="可填写 jmGYK***** 或完整自建 Bark 推送地址",
                )

            with gr.Accordion(
                label="Ntfy 配置",
                open=False,
                elem_classes="btb-card",
            ):
                ntfy_ui = gr.Textbox(
                    value=(ConfigDB.get("ntfyUrl") or ""),
                    label="Ntfy 服务地址",
                    interactive=True,
                    info="例如 https://ntfy.sh/your-topic",
                )

                with gr.Accordion(
                    label="Ntfy 认证（可选）",
                    open=False,
                    elem_classes="btb-card",
                ):
                    with gr.Row():
                        ntfy_username_ui = gr.Textbox(
                            value=(ConfigDB.get("ntfyUsername") or ""),
                            label="Ntfy 用户名",
                            interactive=True,
                        )
                        ntfy_password_ui = gr.Textbox(
                            value=(ConfigDB.get("ntfyPassword") or ""),
                            label="Ntfy 密码",
                            interactive=True,
                            type="password",
                        )

                    def test_ntfy_connection():
                        url = ConfigDB.get("ntfyUrl")
                        username = ConfigDB.get("ntfyUsername")
                        password = ConfigDB.get("ntfyPassword")
                        if not url:
                            return "请先填写 Ntfy 服务地址"

                        from util import NtfyUtil

                        success, message = NtfyUtil.test_connection(url, username, password)
                        return f"成功: {message}" if success else f"错误: {message}"

                    test_ntfy_button = gr.Button("测试 Ntfy 连接", elem_classes="btb-soft-button")
                    test_ntfy_result = gr.Textbox(label="测试结果", interactive=False)
                    test_ntfy_button.click(
                        fn=test_ntfy_connection, inputs=[], outputs=test_ntfy_result
                    )

            with gr.Column():
                test_all_push_button = gr.Button(
                    "测试所有通知方式",
                    elem_classes="btb-soft-button",
                )
                test_push_result = gr.Textbox(label="推送测试结果", interactive=False)

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
                ConfigDB.insert("audioPath", x)
                return gr.update(value=ConfigDB.get("audioPath"))

            def test_all_push():
                try:
                    from util.Notifier import NotifierManager

                    return NotifierManager.test_all_notifiers()
                except Exception as exc:
                    logger.exception(exc)
                    return f"测试过程中出现异常: {exc}"

            serverchan_ui.submit(
                fn=inner_input_serverchan, inputs=serverchan_ui, outputs=serverchan_ui
            )
            serverchan3_ui.submit(
                fn=inner_input_serverchan3, inputs=serverchan3_ui, outputs=serverchan3_ui
            )
            pushplus_ui.submit(
                fn=inner_input_pushplus, inputs=pushplus_ui, outputs=pushplus_ui
            )
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
            test_all_push_button.click(fn=test_all_push, inputs=[], outputs=test_push_result)
            audio_path_ui.upload(
                fn=inner_input_audio_path, inputs=audio_path_ui, outputs=audio_path_ui
            )

            with gr.Accordion(
                label="杂项配置",
                open=False,
                elem_classes="btb-card",
            ):
                show_random_message_ui = gr.Checkbox(
                    label="关闭群友语录",
                    value=True,
                    info="关闭后，抢票失败时不再显示随机提示语",
                )

        with gr.Row(elem_classes="btb-card !items-end !gap-3"):
            interval_ui = gr.Number(
                label="抢票间隔（毫秒）",
                value=1000,
                minimum=1,
                info="请求间隔越小越激进，请按需调整。",
            )
            choices = ["网页"]
            if platform.system() == "Windows":
                choices.insert(0, "终端")
            terminal_ui = gr.Radio(
                label="日志显示方式",
                choices=choices,
                value=choices[0],
                info="Windows 支持终端和网页，其它平台默认网页。",
                type="value",
                interactive=True,
            )

    def try_assign_endpoint(endpoint_url, payload):
        try:
            response = requests.post(f"{endpoint_url}/buy", json=payload, timeout=5)
            if response.status_code == 200:
                return True
            if response.status_code == 409:
                logger.info(f"{endpoint_url} 已经占用")
                return False
            return False
        except Exception as exc:
            logger.exception(exc)
            raise exc

    def split_proxies(https_proxy_list: list[str], task_num: int) -> list[list[str]]:
        assigned_proxies: list[list[str]] = [[] for _ in range(task_num)]
        for index, proxy in enumerate(https_proxy_list):
            assigned_proxies[index % task_num].append(proxy)
        return assigned_proxies

    def start_go(
        files,
        time_start,
        interval,
        audio_path,
        https_proxys,
        terminal_mode,
        hide_random_message,
    ):
        if not files:
            return [
                gr.update(value=withTimeString("尚未上传配置文件"), visible=True),
                _render_go_step_update(uploaded=False, scheduled=False),
            ]
        if not str(time_start or "").strip():
            gr.Warning("请先填写或自动填充抢票开始时间。")
            return [
                gr.update(value=withTimeString("尚未设置抢票开始时间"), visible=True),
                _render_go_step_update(uploaded=True, scheduled=False),
            ]
        yield [
            gr.update(value=withTimeString("正在启动任务，请查看终端或网页日志"), visible=True),
            _render_go_step_update(uploaded=True, scheduled=True, launched=True),
        ]

        endpoints = GlobalStatusInstance.available_endpoints()
        endpoints_next_idx = 0
        https_proxy_list = ["none"] + https_proxys.split(",")
        assigned_proxies: list[list[str]] = []
        assigned_proxies_next_idx = 0

        for idx, filename in enumerate(files):
            with open(filename, "r", encoding="utf-8") as file:
                content = file.read()

            logger.info(f"启动 {os.path.basename(filename)}")
            while endpoints_next_idx < len(endpoints) and terminal_mode == "网页":
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

                buy_new_terminal(
                    endpoint_url=demo.local_url,
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
                    terminal_ui=terminal_mode,
                    show_random_message=not hide_random_message,
                )
                assigned_proxies_next_idx += 1
        gr.Info("正在启动，请等待抢票页面或终端弹出。")

    go_btn = gr.Button("开始抢票", elem_classes="btb-strong-button")

    auto_fill_time_btn.click(
        fn=auto_fill_time,
        inputs=upload_ui,
        outputs=[time_start_ui, go_step_status_ui],
    )

    time_start_ui.change(
        fn=on_time_start_change,
        inputs=[upload_ui, time_start_ui],
        outputs=go_step_status_ui,
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
        inputs=[_end_point_tinput, time_start_ui],
        api_name="report",
    )

    def tick():
        return f"当前时间戳：{int(time.time())}"

    timer = gr.Textbox(label="定时刷新", interactive=False, visible=False)
    demo.load(fn=tick, inputs=None, outputs=timer, every=1)

    @gr.render(inputs=timer)
    def show_split(_text):
        endpoints = GlobalStatusInstance.available_endpoints()
        if len(endpoints) != 0:
            gr.Markdown("## 当前运行终端列表")
            for endpoint in endpoints:
                with gr.Row():
                    gr.Button(
                        value=f"打开终端 {endpoint.endpoint} {endpoint.detail}",
                        link=endpoint.endpoint,
                    )

    go_btn.click(
        fn=start_go,
        inputs=[
            upload_ui,
            time_start_ui,
            interval_ui,
            audio_path_ui,
            https_proxy_ui,
            terminal_ui,
            show_random_message_ui,
        ],
        outputs=[ticket_ui, go_step_status_ui],
    )
