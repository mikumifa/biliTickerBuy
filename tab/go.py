import importlib
import os
from time import sleep
from gradio_log import Log
import psutil
from pathlib import Path
import gradio as gr
from gradio import SelectData
from loguru import logger
from py import log

from const import BASE_DIR
from task.buy import buy_new_terminal
from util.config import configDB, time_service, main_request
from util.dynimport import bili_ticket_gt_python
from util.error import withTimeString

ways = []
ways_detail = []
if bili_ticket_gt_python is not None:
    ways_detail.insert(0, importlib.import_module(
        "geetest.TripleValidator").TripleValidator())
    ways.insert(0, "本地过验证码v2(Amorter提供)")
    # ways_detail.insert(0, importlib.import_module("geetest.AmorterValidator").AmorterValidator())
    # ways.insert(0, "本地过验证码(Amorter提供)")


def handle_error(message, e):
    logger.error(message + str(e))
    return [gr.update(value=withTimeString(f"有错误，具体查看控制台日志\n\n当前错误 {e}"), visible=True),
            gr.update(visible=True), *[gr.update() for _ in range(6)]]


def go_tab():
    gr.Markdown("""
> **分享一下经验**
> - 抢票前，不要去提前抢还没有发售的票，会被b站封掉一段时间导致错过抢票的
> - 热门票要提前练习过验证码
> - 使用不同的多个账号抢票 （可以每一个exe文件都使用不同的账号， 或者在使用这个程序的时候，手机使用其他的账号去抢）
> - 程序能保证用最快的速度发送订单请求，但是不保证这一次订单请求能够成功。所以不要完全依靠程序
> - 现在各个平台抢票和秒杀机制都是进抽签池抽签，网速快发请求多快在拥挤的时候基本上没有效果
> 此时就要看你有没有足够的设备和账号来提高中签率
> - 欢迎前往 [discussions](https://github.com/mikumifa/biliTickerBuy/discussions) 分享你的经验
""")
    with gr.Column():
        gr.Markdown("""
            ### 上传或填入你要抢票票种的配置信息
            """)
        with gr.Row(equal_height=True):
            upload_ui = gr.Files(
                label="上传多个配置文件，点击不同的配置文件可快速切换", file_count="multiple")
            ticket_ui = gr.TextArea(label="填入配置",
                                    info="再次填入配置信息",
                                    interactive=True)
        gr.HTML("""<label for="datetime">程序已经提前帮你校准时间，设置成开票时间即可。请勿设置成开票前的时间。在开票前抢票会短暂封号</label><br>
                <input type="datetime-local" id="datetime" name="datetime" step="1">""", label="选择抢票的时间",
                show_label=True, )

        def upload(filepath):
            try:
                with open(filepath[0], 'r', encoding="utf-8") as file:
                    content = file.read()
                return content
            except Exception as e:
                return str(e)

        def file_select_handler(select_data: SelectData, files):
            file_label = files[select_data.index]
            try:
                with open(file_label, 'r', encoding="utf-8") as file:
                    content = file.read()
                return content
            except Exception as e:
                return str(e)

        upload_ui.upload(fn=upload, inputs=upload_ui, outputs=ticket_ui)
        upload_ui.select(file_select_handler, upload_ui, ticket_ui)

        # 手动设置/更新时间偏差
        with gr.Accordion(label='手动设置/更新时间偏差', open=False):
            time_diff_ui = gr.Number(label="当前脚本时间偏差 (单位: ms)",
                                     info="你可以在这里手动输入时间偏差, 或点击下面按钮自动更新当前时间偏差。正值将推迟相应时间开始抢票, 负值将提前相应时间开始抢票。",
                                     value=format(time_service.get_timeoffset() * 1000, '.2f'))  # type: ignore
            refresh_time_ui = gr.Button(value="点击自动更新时间偏差")
            refresh_time_ui.click(fn=lambda: format(float(time_service.compute_timeoffset()) * 1000, '.2f'),
                                  inputs=None, outputs=time_diff_ui)
            time_diff_ui.change(fn=lambda x: time_service.set_timeoffset(format(float(x) / 1000, '.5f')),
                                inputs=time_diff_ui, outputs=None)

        # 验证码选择
        select_way = 0
        way_select_ui = gr.Radio(ways, label="过验证码的方式", info="详细说明请前往 `训练你的验证码速度` 那一栏",
                                 type="index", value=ways[select_way])

        with gr.Accordion(label='配置抢票声音提醒[可选]', open=False):
            with gr.Row():
                audio_path_ui = gr.Audio(
                    label="上传提示声音[只支持格式wav]", type="filepath", loop=True)
        with gr.Accordion(label='配置抢票消息提醒[可选]', open=False):
            gr.Markdown(
                """
                🗨️ 抢票成功提醒
                > 你需要去对应的网站获取key或token，然后填入下面的输入框
                > [Server酱](https://sct.ftqq.com/sendkey) | [pushplus](https://www.pushplus.plus/uc.html)
                > 留空以不启用提醒功能
                """)
            with gr.Row():
                serverchan_ui = gr.Textbox(
                    value=configDB.get("serverchanKey") if configDB.get(
                        "serverchanKey") is not None else "",
                    label="Server酱的SendKey",
                    interactive=True,
                    info="https://sct.ftqq.com/",
                )

                pushplus_ui = gr.Textbox(
                    value=configDB.get("pushplusToken") if configDB.get(
                        "pushplusToken") is not None else "",
                    label="PushPlus的Token",
                    interactive=True,
                    info="https://www.pushplus.plus/",
                )

                def inner_input_serverchan(x):
                    return configDB.insert("serverchanKey", x)

                def inner_input_pushplus(x):
                    return configDB.insert("pushplusToken", x)

                serverchan_ui.change(
                    fn=inner_input_serverchan, inputs=serverchan_ui)

                pushplus_ui.change(fn=inner_input_pushplus, inputs=pushplus_ui)

        def choose_option(way):
            nonlocal select_way
            select_way = way

        way_select_ui.change(choose_option, inputs=way_select_ui)
        with gr.Row():
            interval_ui = gr.Number(label="抢票间隔", value=300, minimum=1,
                                    info="设置抢票任务之间的时间间隔（单位：毫秒），建议不要设置太小", )
            mode_ui = gr.Radio(label="抢票次数", choices=["无限", "有限"], value="无限", info="选择抢票的次数",
                               type="index", interactive=True, )
            total_attempts_ui = gr.Number(label="总过次数", value=100, minimum=1, info="设置抢票的总次数",
                                          visible=False, )

    def start_go(files, time_start, interval, mode, total_attempts, audio_path):
        if not files:
            return [gr.update(value=withTimeString("未提交抢票配置"), visible=True)]
        phone = main_request.cookieManager.get_config_value("phone", "")
        yield [
            gr.update(value=withTimeString("开始多开抢票,详细查看终端"), visible=True)]
        for filename in files:
            with open(filename, 'r', encoding="utf-8") as file:
                content = file.read()
            filename_only = os.path.basename(filename)
            logger.info(f"启动 {filename_only}")
            proc, task_id = buy_new_terminal(filename=filename,
                                             tickets_info_str=content, time_start=time_start, interval=interval, mode=mode,
                                             total_attempts=total_attempts, audio_path=audio_path,
                                             pushplusToken=configDB.get(
                                                 "pushplusToken"),
                                             serverchanKey=configDB.get(
                                                 "serverchanKey"),
                                             timeoffset=time_service.get_timeoffset(), phone=phone, )
        return [gr.update()]
    mode_ui.change(
        fn=lambda x: gr.update(visible=True) if x == 1 else gr.update(visible=False), inputs=[mode_ui],
        outputs=total_attempts_ui, )
    with gr.Row():
        go_btn = gr.Button("开始抢票")

    with gr.Row():
        go_ui = gr.Textbox(
            info="此窗口为临时输出，具体请见控制台", label="输出信息", interactive=False, visible=False,
            show_copy_button=True, max_lines=10,
        )

    time_tmp = gr.Textbox(visible=False)

    go_btn.click(fn=start_go,
                 inputs=[upload_ui, time_tmp, interval_ui, mode_ui, total_attempts_ui,
                         audio_path_ui],
                 outputs=[go_ui],)
