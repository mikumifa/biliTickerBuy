import json
import logging
import os
import sys
import time
from datetime import datetime

import gradio as gr

from common import format_dictionary_to_string
from config import cookies_config_path
from util.BiliRequest import BiliRequest

buyer_value = []
addr_value = []
ticket_value = []
isRunning = False


def onSubmitTicketId(num):
    global buyer_value
    global addr_value
    global ticket_value

    try:
        num = int(num)
        _request = BiliRequest(cookies_config_path=cookies_config_path)
        res = _request.get(
            url=f"https://show.bilibili.com/api/ticket/project/getV2?version=134&id={num}&project_id={num}")
        ret = res.json()
        logging.info(ret)

        ticket_str_list = []
        project_id = ret["data"]["id"]
        for screen in ret["data"]["screen_list"]:
            screen_name = screen["name"]
            screen_id = screen["id"]
            for ticket in screen["ticket_list"]:
                ticket_desc = ticket['desc']
                ticket_price = ticket['price']

                ticket["screen"] = screen_name
                ticket["screen_id"] = screen_id
                ticket_can_buy = "可购买" if ticket['clickable'] else "无法购买"
                ticket_str = f"{screen_name} - {ticket_desc} - ￥{ticket_price / 100} - {ticket_can_buy}"
                ticket_str_list.append(ticket_str)
                ticket_value.append({"project_id": project_id, "ticket": ticket})

        buyer_json = _request.get(
            url=f"https://show.bilibili.com/api/ticket/buyer/list?is_default&projectId={project_id}").json()
        logging.info(buyer_json)
        addr_json = _request.get(url="https://show.bilibili.com/api/ticket/addr/list").json()
        logging.info(addr_json)

        buyer_str_list = [f"{item['name']}-{item['personal_id']}" for item in buyer_json["data"]["list"]]
        buyer_value = [item for item in buyer_json["data"]["list"]]
        addr_str_list = [f"{item['addr']}-{item['name']}-{item['phone']}" for item in addr_json["data"]["addr_list"]]
        addr_value = [item for item in addr_json["data"]["addr_list"]]

        return [gr.update(choices=ticket_str_list), gr.update(choices=buyer_str_list),
                gr.update(choices=buyer_str_list), gr.update(choices=addr_str_list), gr.update(visible=True),
                gr.update(value="获取票信息成功", visible=True)]
    except Exception as e:
        return [gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(value=e, visible=True)]


def onSubmitAll(ticket_number, ticket_info, people, people_buyer, address):
    if ticket_number != len(people):
        return gr.update(value="生成配置文件失败，保证选票数目和购买人数目一致", visible=True)
    ticket_cur = ticket_value[ticket_info]
    people_cur = [buyer_value[item] for item in people]
    people_buyer_cur = buyer_value[people_buyer]

    address_cur = addr_value[address]
    config_dir = {"count": ticket_number, "screen_id": ticket_cur["ticket"]["screen_id"],
                  "project_id": ticket_cur["project_id"], "sku_id": ticket_cur["ticket"]["id"], "order_type": 1,
                  "buyer_info": people_cur, "buyer": people_buyer_cur["name"], "tel": people_buyer_cur["tel"],
                  "deliver_info": {"name": address_cur["name"], "tel": address_cur["phone"],
                                   "addr_id": address_cur["id"],
                                   "addr": address_cur["prov"] + address_cur["city"] + address_cur["area"] +
                                           address_cur["addr"]}}
    return gr.update(value=json.dumps(config_dir), visible=True)


def start_go(tickets_info, time_start, interval, mode, total_attempts):
    global isRunning
    result = ""
    request_result = {"msg": "配置文件有错"}
    isRunning = True
    try:
        _request = BiliRequest(cookies_config_path=cookies_config_path)
        tickets_info = json.loads(tickets_info)
        token_payload = {"count": tickets_info["count"], "screen_id": tickets_info["screen_id"], "order_type": 1,
                         "project_id": tickets_info["project_id"], "sku_id": tickets_info["sku_id"], "token": "", }
        request_result = _request.post(
            url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
            data=token_payload).json()
        logging.info(f"{request_result}")

        tickets_info["token"] = request_result["data"]["token"]

        request_result = _request.get(
            url=f"https://show.bilibili.com/api/ticket/order/confirmInfo?token={tickets_info['token']}&voucher=&project_id={tickets_info['project_id']}").json()
        tickets_info["pay_money"] = request_result["data"]["pay_money"]
        tickets_info["timestamp"] = int(time.time()) * 100
        payload = format_dictionary_to_string(tickets_info)
        left_time = total_attempts
        if time_start != '':
            time_difference = datetime.strptime(time_start, "%Y-%m-%dT%H:%M").timestamp() - time.time()
            if time_difference > 0:
                result += f'{datetime.now()} msg: 等待中\n'
                yield [gr.update(value=result, visible=True), gr.update(visible=True)]
                time.sleep(time_difference)  # 等待到指定的开始时间
        while isRunning:
            creat_request_result = _request.post(
                url=f"https://show.bilibili.com/api/ticket/order/createV2?project_id={tickets_info['project_id']}",
                data=payload).json()
            res = creat_request_result["msg"] if creat_request_result["msg"] else creat_request_result["data"]
            result += f'{datetime.now()} msg: {res} 剩余次数: {left_time}\n'
            yield [gr.update(value=result, visible=True), gr.update(visible=True)]
            time.sleep(interval / 1000.0)
            if mode == 1:
                left_time -= 1
                if left_time <= 0:
                    break
        return [gr.update(value=result, visible=True), gr.update(visible=False)]
    except KeyError as e:
        logging.info(e)
        return [gr.update(value="request_result", visible=True), gr.update(visible=False)]


def configure_global_logging():
    application_path = os.path.dirname(os.path.abspath(__file__))
    if hasattr(sys, "_MEIPASS"):
        application_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    global_logger = logging.getLogger()
    global_logger.setLevel(logging.INFO)
    log_file_path = os.path.join(application_path, 'app.log')
    file_handler = logging.FileHandler(log_file_path)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    global_logger.addHandler(file_handler)


if __name__ == '__main__':
    configure_global_logging()
    with gr.Blocks() as demo:
        gr.Markdown("抢票")
        with gr.Tab("配置") as setting_tab:
            info_ui = gr.TextArea(info="此窗口为输出信息", label="输出信息", interactive=False, visible=False)
            with gr.Column() as first:
                ticket_id_ui = gr.Textbox(label="票ID", interactive=True)
                ticket_id_btn = gr.Button("提交票id")
                with gr.Column(visible=False) as inner:
                    ticket_number_ui = gr.Number(label="票数目", value=1)
                    ticket_info_ui = gr.Dropdown(label="选票", interactive=True, type="index")
                    people_ui = gr.CheckboxGroup(label="实名人", interactive=True, type="index",
                                                 info="用于身份证实名认证，请确保曾经在b站填写过购买人的实名信息，否则这个表单不会有任何信息")
                    people_buyer_ui = gr.Dropdown(label="联系人", interactive=True, type="index",
                                                  info="选一个作为联系人，请确保曾经在b站填写过购买人的实名信息，否则这个表单不会有任何信息")
                    address_ui = gr.Dropdown(label="地址", interactive=True, type="index",
                                             info="请确保曾经在b站填写过地址，否则这个表单不会有任何信息")
                    config_output_ui = gr.Textbox(label="生成配置文件", show_copy_button=True, info="右上角粘贴",
                                                  visible=False)
                    config_btn = gr.Button("生成配置")
                    config_btn.click(fn=onSubmitAll,
                                     inputs=[ticket_number_ui, ticket_info_ui, people_ui, people_buyer_ui, address_ui],
                                     outputs=config_output_ui, )

                ticket_id_btn.click(fn=onSubmitTicketId, inputs=ticket_id_ui,
                                    outputs=[ticket_info_ui, people_ui, people_buyer_ui, address_ui, inner, info_ui])

        with gr.Tab("抢票") as go_tab:
            with gr.Column() as second:
                ticket_ui = gr.TextArea(label="填入配置", info="再次填入配置信息", interactive=True)
                time_html = gr.HTML("""<label for="datetime">选择抢票的时间</label><br> 
                <input type="datetime-local" id="datetime" name="datetime">""", label="选择抢票的时间", show_label=True)
                interval_ui = gr.Number(label="抢票间隔", value=1000, minimum=1,
                                        info="设置抢票任务之间的时间间隔（单位：毫秒），建议不要设置太小")
                mode_ui = gr.Radio(label="抢票模式", choices=["无限", "有限"], value="无限", info="选择抢票的模式",
                                   type="index", interactive=True)
                total_attempts_ui = gr.Number(label="总过次数", value=100, minimum=1, info="设置抢票的总次数",
                                              visible=False)
                mode_ui.change(fn=lambda x: gr.update(visible=True) if x == 1 else gr.update(visible=False),
                               inputs=[mode_ui], outputs=total_attempts_ui)
                go_btn = gr.Button("开始抢票")
                go_ui = gr.TextArea(info="此窗口为输出信息", label="输出信息", interactive=False, visible=False,
                                    show_copy_button=True, max_lines=10)
                time_tmp = gr.Textbox(visible=False)
                go_btn.click(fn=None, inputs=None, outputs=time_tmp,
                             js='(x) => {return (document.getElementById("datetime")).value;}')

                stop_btn = gr.Button("停止", visible=False)


                def stop():
                    global isRunning
                    isRunning = False


                go_btn.click(fn=start_go, inputs=[ticket_ui, time_tmp, interval_ui, mode_ui, total_attempts_ui],
                             outputs=[go_ui, stop_btn], )
                stop_btn.click(fn=stop, inputs=None,
                               outputs=None, )

                # 运行应用
    demo.launch()
