import datetime
import importlib
from math import lgamma
import os
import platform
import time
import gradio as gr
from gradio import SelectData
from loguru import logger
import requests

from geetest.Validator import Validator
from task.buy import buy_new_terminal
from util import ConfigDB, Endpoint, GlobalStatusInstance, time_service
from util import bili_ticket_gt_python


def withTimeString(string):
    return f"{datetime.datetime.now()}: {string}"


ways: list[str] = []
ways_detail: list[Validator] = []
if bili_ticket_gt_python is not None:
    ways_detail.insert(
        0, importlib.import_module("geetest.TripleValidator").TripleValidator()
    )
    ways.insert(0, "本地过验证码v2(Amorter提供)")
    # ways_detail.insert(0, importlib.import_module("geetest.AmorterValidator").AmorterValidator())
    # ways.insert(0, "本地过验证码(Amorter提供)")


def go_tab(demo: gr.Blocks):
    with gr.Column():
        gr.Markdown("""
            ### 上传或填入你要抢票票种的配置信息
            """)
        with gr.Row():
            upload_ui = gr.Files(
                label="上传多个配置文件,每一个上传的文件都会启动一个抢票程序",
                file_count="multiple",
            )
            ticket_ui = gr.TextArea(
                label="查看", info="只能通过上传文件方式上传信息", interactive=False
            )
        with gr.Row(variant="compact"):
            gr.HTML(
                """
            <div class="bg-red-50 border border-red-200 rounded-xl p-4 shadow-sm">
                <p class="text-red-600 font-medium mb-2">
                    程序已经提前帮你校准时间，<strong>请设置成开票时间</strong>。切勿设置为开票前时间，
                    否则<strong>有封号风险</strong>！
                </p>
                <label for="datetime" class="block text-gray-700 font-semibold mb-1">选择抢票时间（精确到秒）</label>
                <input 
                    type="datetime-local" 
                    id="datetime" 
                    name="datetime" 
                    step="1"
                    class="w-full border border-gray-300 rounded-lg p-2 shadow-sm 
                        focus:outline-none focus:ring-2 focus:ring-blue-400 
                        hover:border-blue-400 transition-all"
                >
            </div>
            """,
                label="选择抢票的时间",
            )

        def upload(filepath):
            try:
                with open(filepath[0], "r", encoding="utf-8") as file:
                    content = file.read()
                return content
            except Exception as e:
                return str(e)

        def file_select_handler(select_data: SelectData, files):
            file_label = files[select_data.index]
            try:
                with open(file_label, "r", encoding="utf-8") as file:
                    content = file.read()
                return content
            except Exception as e:
                return str(e)

        upload_ui.upload(fn=upload, inputs=upload_ui, outputs=ticket_ui)
        upload_ui.select(file_select_handler, upload_ui, ticket_ui)

        # 手动设置/更新时间偏差
        with gr.Accordion(label="手动设置/更新时间偏差", open=False):
            time_diff_ui = gr.Number(
                label="当前脚本时间偏差 (单位: ms)",
                info="你可以在这里手动输入时间偏差, 或点击下面按钮自动更新当前时间偏差。正值将推迟相应时间开始抢票, 负值将提前相应时间开始抢票。",
                value=float(format(time_service.get_timeoffset() * 1000, ".2f")),
            )  # type: ignore
            refresh_time_ui = gr.Button(value="点击自动更新时间偏差")
            refresh_time_ui.click(
                fn=lambda: format(
                    float(time_service.compute_timeoffset()) * 1000, ".2f"
                ),
                inputs=None,
                outputs=time_diff_ui,
            )
            time_diff_ui.change(
                fn=lambda x: time_service.set_timeoffset(
                    format(float(x) / 1000, ".5f")
                ),
                inputs=time_diff_ui,
                outputs=None,
            )

        # 验证码选择
        select_way = 0
        way_select_ui = gr.Radio(
            ways,
            label="过验证码的方式",
            info="详细说明请前往 `训练你的验证码速度` 那一栏",
            type="index",
            value=ways[select_way],
        )
        with gr.Accordion(label="填写你的HTTPS代理服务器[可选]", open=False):
            gr.Markdown("""
                        > **注意**：

                        填写代理服务器地址后，程序在使用这个配置文件后会在出现风控后后根据代理服务器去访问哔哩哔哩的抢票接口。

                        抢票前请确保代理服务器已经开启，并且可以正常访问哔哩哔哩的抢票接口。

                        """)

            def get_latest_proxy():
                return ConfigDB.get("https_proxy") or ""

            https_proxy_ui = gr.Textbox(
                label="填写抢票时候的代理服务器地址，使用逗号隔开|输入完成后，回车键保存",
                info="例如： http://127.0.0.1:8080,http://127.0.0.1:8081,http://127.0.0.1:8082",
                value=get_latest_proxy,
            )

            def input_https_proxy(_https_proxy):
                ConfigDB.insert("https_proxy", _https_proxy)
                return gr.update(ConfigDB.get("https_proxy"))

            https_proxy_ui.submit(
                fn=input_https_proxy, inputs=https_proxy_ui, outputs=https_proxy_ui
            )

            test_proxy_btn = gr.Button("🔍 测试代理连通性")
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

            def test_proxy_connectivity(proxy_string, timeout):
                """测试代理连通性"""
                try:
                    from util.ProxyTester import test_proxy_connectivity

                    if not proxy_string or proxy_string.strip() == "":
                        proxy_string = "none"  # 测试直连
                    result = test_proxy_connectivity(proxy_string, int(timeout))
                    return result
                except Exception as e:
                    return f"❌ 测试过程中发生错误: {str(e)}"

            test_proxy_btn.click(
                fn=test_proxy_connectivity,
                inputs=[https_proxy_ui, test_timeout_ui],
                outputs=test_result_ui,
            )
        with gr.Accordion(label="配置抢票成功后播放音乐[可选]", open=False):
            with gr.Row():
                audio_path_ui = gr.Audio(
                    label="上传提示声音[只支持格式wav]", type="filepath", loop=True
                )
        with gr.Accordion(label="配置抢票推送消息[可选]", open=False):
            gr.Markdown(
            """
            🗨️ **抢票成功提醒**

            > 你需要去对应的网站获取 key 或 token，然后填入下面的输入框  
            > [Server酱](https://sct.ftqq.com/sendkey) | [pushplus](https://www.pushplus.plus/uc.html) | [ntfy](https://ntfy.sh/)  
            > 留空以不启用提醒功能

            ### 🔍 推送服务对比

            | 服务     | 优点                               | 缺点                            |
            |----------|------------------------------------|---------------------------------|
            | Server酱 | 简单易用，微信推送              | 微信推送很难看到 |
            | pushplus | 简单易用，微信推送| 微信推送很难看到               |
            | ntfy     | APP推送 | 配置复杂，需要手动搭建或注册公网地址 |

            ✅ 推荐：初次使用建议选择 **pushplus** 或 **Server酱**，配置最简单  
            🛠️ 追求高度自由或有自建服务器建议用 **ntfy**
            """
            )   
            with gr.Row():
                serverchan_ui = gr.Textbox(
                    value= lambda : (ConfigDB.get("serverchanKey") or ""),
                    label="Server酱的SendKey｜输入完成后，回车键保存",
                    interactive=True,
                    info="https://sct.ftqq.com/",
                )

                pushplus_ui = gr.Textbox(
                    value=lambda :(ConfigDB.get("pushplusToken") or ''),
                    label="PushPlus的Token｜输入完成后，回车键保存",
                    interactive=True,
                    info="https://www.pushplus.plus/",
                )

                ntfy_ui = gr.Textbox(
                    value=lambda :(ConfigDB.get("ntfyUrl") or ""),
                    label="Ntfy服务器URL｜输入完成后，回车键保存",
                    interactive=True,
                    info="例如: https://ntfy.sh/your-topic",
                )

            with gr.Accordion(label="Ntfy认证配置[可选]", open=False):
                    with gr.Row():
                        ntfy_username_ui = gr.Textbox(
                            value=lambda :(ConfigDB.get("ntfyUsername") or ""),
                            label="Ntfy用户名",
                            interactive=True,
                            info="如果你的Ntfy服务器需要认证",
                        )

                        ntfy_password_ui = gr.Textbox(
                            value=lambda :(ConfigDB.get("ntfyPassword") or ""),
                            label="Ntfy密码",
                            interactive=True,
                            type="password",
                        )

                    def test_ntfy_connection():
                        url = ConfigDB.get("ntfyUrl")
                        username = ConfigDB.get("ntfyUsername")
                        password = ConfigDB.get("ntfyPassword")

                        if not url:
                            return "错误: 请先设置Ntfy服务器URL"

                        from util import NtfyUtil

                        success, message = NtfyUtil.test_connection(
                            url, username, password
                        )

                        if success:
                            return f"成功: {message}"
                        else:
                            return f"错误: {message}"

                    test_ntfy_button = gr.Button("测试Ntfy连接")
                    test_ntfy_result = gr.Textbox(label="测试结果", interactive=False)
                    test_ntfy_button.click(
                        fn=test_ntfy_connection, inputs=[], outputs=test_ntfy_result
                    )

            def inner_input_serverchan(x):
                ConfigDB.insert("serverchanKey", x)
                return gr.update(value=ConfigDB.get("serverchanKey"))

            def inner_input_pushplus(x):
                ConfigDB.insert("pushplusToken", x)
                return gr.update(value=ConfigDB.get("pushplusToken"))

            def inner_input_ntfy(x):
                ConfigDB.insert("ntfyUrl", x)
                return gr.update(value=ConfigDB.get("ntfyUrl"))

            def inner_input_ntfy_username(x):
                ConfigDB.insert("ntfyUsername", x)
                return gr.update(value=ConfigDB.get("ntfyUsername"))

            def inner_input_ntfy_password(x):
                ConfigDB.insert("ntfyPassword", x)
                return gr.update(value=ConfigDB.get("ntfyPassword"))

            serverchan_ui.submit(fn=inner_input_serverchan, inputs=serverchan_ui, outputs=serverchan_ui)

            pushplus_ui.submit(fn=inner_input_pushplus, inputs=pushplus_ui, outputs=pushplus_ui)

            ntfy_ui.submit(fn=inner_input_ntfy, inputs=ntfy_ui, outputs=ntfy_ui)

            ntfy_username_ui.submit(fn=inner_input_ntfy_username, inputs=ntfy_username_ui, outputs=ntfy_username_ui)

            ntfy_password_ui.submit(fn=inner_input_ntfy_password, inputs=ntfy_password_ui, outputs=ntfy_password_ui)


        def choose_option(way):
            nonlocal select_way
            select_way = way

        way_select_ui.change(choose_option, inputs=way_select_ui)

        with gr.Row():
            interval_ui = gr.Number(
                label="抢票间隔",
                value=300,
                minimum=1,
                info="设置抢票任务之间的时间间隔（单位：毫秒），建议不要设置太小",
            )
            mode_ui = gr.Radio(
                label="抢票次数",
                choices=["无限", "有限"],
                value="无限",
                info="选择抢票的次数",
                type="index",
                interactive=True,
            )
            choices = ["网页"]
            if platform.system() == "Windows":
                choices.insert(0, "终端")  # 或 append，取决于你想要顺序
            terminal_ui = gr.Radio(
                label="日志显示方式",
                choices=choices,
                value=choices[0],
                info="日志显示的方式,非windows用戶只支持網頁",
                type="value",
                interactive=True,
            )
            total_attempts_ui = gr.Number(
                label="总过次数",
                value=100,
                minimum=1,
                info="设置抢票的总次数",
                visible=False,
            )

    def try_assign_endpoint(endpoint_url, payload):
        try:
            response = requests.post(f"{endpoint_url}/buy", json=payload, timeout=5)
            if response.status_code == 200:
                return True
            elif response.status_code == 409:
                logger.info(f"{endpoint_url} 已经占用")
                return False
            else:
                return False

        except Exception as e:
            logger.exception(e)
            raise e

    def split_proxies(https_proxy_list: list[str], task_num: int) -> list[list[str]]:
        assigned_proxies: list[list[str]] = [[] for _ in range(task_num)]
        for i, proxy in enumerate(https_proxy_list):
            assigned_proxies[i % task_num].append(proxy)
        return assigned_proxies

    def start_go(
        files,
        time_start,
        interval,
        mode,
        total_attempts,
        audio_path,
        https_proxys,
        terminal_ui,
    ):
        if not files:
            return [gr.update(value=withTimeString("未提交抢票配置"), visible=True)]
        yield [
            gr.update(value=withTimeString("开始多开抢票,详细查看终端"), visible=True)
        ]
        endpoints = GlobalStatusInstance.available_endpoints()
        endpoints_next_idx = 0
        https_proxy_list = ["none"] + https_proxys.split(",")
        assigned_proxies: list[list[str]] = []
        assigned_proxies_next_idx = 0
        for idx, filename in enumerate(files):
            with open(filename, "r", encoding="utf-8") as file:
                content = file.read()
            filename_only = os.path.basename(filename)
            logger.info(f"启动 {filename_only}")
            # 先分配worker
            while endpoints_next_idx < len(endpoints) and terminal_ui == "网页":
                success = try_assign_endpoint(
                    endpoints[endpoints_next_idx].endpoint,
                    payload={
                        "force": True,
                        "train_info": content,
                        "time_start": time_start,
                        "interval": interval,
                        "mode": mode,
                        "total_attempts": total_attempts,
                        "audio_path": audio_path,
                        "pushplusToken": ConfigDB.get("pushplusToken"),
                        "serverchanKey": ConfigDB.get("serverchanKey"),
                        "ntfy_url": ConfigDB.get("ntfyUrl"),
                        "ntfy_username": ConfigDB.get("ntfyUsername"),
                        "ntfy_password": ConfigDB.get("ntfyPassword"),
                    },
                )
                endpoints_next_idx += 1
                if success:
                    break
            else:
                # 再分配https_proxys
                if assigned_proxies == []:
                    left_task_num = len(files) - idx
                    assigned_proxies = split_proxies(https_proxy_list, left_task_num)

                buy_new_terminal(
                    endpoint_url=demo.local_url,
                    filename=filename,
                    tickets_info_str=content,
                    time_start=time_start,
                    interval=interval,
                    mode=mode,
                    total_attempts=total_attempts,
                    audio_path=audio_path,
                    pushplusToken=ConfigDB.get("pushplusToken"),
                    serverchanKey=ConfigDB.get("serverchanKey"),
                    ntfy_url=ConfigDB.get("ntfyUrl"),
                    ntfy_username=ConfigDB.get("ntfyUsername"),
                    ntfy_password=ConfigDB.get("ntfyPassword"),
                    https_proxys=",".join(assigned_proxies[assigned_proxies_next_idx]),
                    terminal_ui=terminal_ui,
                )
                assigned_proxies_next_idx += 1
        gr.Info("正在启动，请等待抢票页面弹出。")

    mode_ui.change(
        fn=lambda x: gr.update(visible=True) if x == 1 else gr.update(visible=False),
        inputs=[mode_ui],
        outputs=total_attempts_ui,
    )

    go_btn = gr.Button("开始抢票")

    _time_tmp = gr.Textbox(visible=False)
    go_btn.click(
        fn=None,
        inputs=None,
        outputs=_time_tmp,
        js='(x) => document.getElementById("datetime").value',
    )
    _report_tmp = gr.Button(visible=False)
    _report_tmp.api_info

    # hander endpoint hearts

    _end_point_tinput = gr.Textbox(visible=False)

    def report(end_point, detail):
        now = time.time()
        GlobalStatusInstance.endpoint_details[end_point] = Endpoint(
            endpoint=end_point, detail=detail, update_at=now
        )

    _report_tmp.click(
        fn=report,
        inputs=[_end_point_tinput, _time_tmp],  # fake useage
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
                with gr.Row():
                    gr.Button(
                        value=f"点击跳转 🚀 {endpoint.endpoint} {endpoint.detail}",
                        link=endpoint.endpoint,
                    )

    go_btn.click(
        fn=start_go,
        inputs=[
            upload_ui,
            _time_tmp,
            interval_ui,
            mode_ui,
            total_attempts_ui,
            audio_path_ui,
            https_proxy_ui,
            terminal_ui,
        ],
    )
