import json
import logging
import os
import sys
import time
from datetime import datetime
from urllib.parse import urlencode

import gradio as gr
import qrcode

from common import format_dictionary_to_string
from config import cookies_config_path
from util.BiliRequest import BiliRequest
from util.error import errnoDict
from util.order_qrcode import get_qrcode_url

buyer_value = []
addr_value = []
ticket_value = []
isRunning = False
gt = ""
challenge = ""
geetest_validate = ""
geetest_seccode = ""


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
        project_name = ret["data"]["name"]
        project_start_time_unix = ret["data"]["start_time"]
        project_end_time_unix = ret["data"]["end_time"]
        project_start_time = datetime.fromtimestamp(project_start_time_unix).strftime("%Y-%m-%d %H:%M:%S")
        project_end_time = datetime.fromtimestamp(project_end_time_unix).strftime("%Y-%m-%d %H:%M:%S")
        venue_info = ret["data"]["venue_info"]
        venue_name = venue_info["name"]
        venue_address = venue_info["address_detail"]
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
                gr.update(
                    value=f"获取票信息成功:\n展会名称: {project_name}\n开展时间: {project_start_time} - {project_end_time}\n"
                          f"场馆地址: {venue_name} {venue_address}",
                    visible=True)]
    except Exception as e:
        return [gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(value=e, visible=True)]


def onSubmitAll(ticket_number, ticket_info, people, people_buyer, address):
    try:
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
    except Exception as e:
        logging.info(e)
        return gr.update(value="生产错误，仔细看看你可能有哪里漏填的", visible=True)


def start_go(tickets_info, time_start, interval, mode, total_attempts):
    global isRunning, geetest_validate, geetest_seccode
    global gt
    global challenge
    result = ""
    request_result = {"errno": "未知状态码", "msg": "配置文件有错"}
    isRunning = True
    left_time = total_attempts
    while isRunning:
        try:
            _request = BiliRequest(cookies_config_path=cookies_config_path)
            tickets_info = json.loads(tickets_info)
            token_payload = {"count": tickets_info["count"], "screen_id": tickets_info["screen_id"], "order_type": 1,
                             "project_id": tickets_info["project_id"], "sku_id": tickets_info["sku_id"], "token": "",
                             "newRisk": True}
            request_result_normal = _request.post(
                url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                data=token_payload)
            request_result = request_result_normal.json()
            logging.info(f"prepare header: {request_result_normal.headers}")
            logging.info(f"prepare: {request_result}")

            code = int(request_result["code"])
            ## https://github.com/fsender/Bilibili_show_ticket_auto_order/blob/18b3cf6cb539167153f1d2dd847006c9794ac9af/api.py#L237
            if code == -401:
                _url = "https://api.bilibili.com/x/gaia-vgate/v1/register"
                _payload = urlencode(request_result["data"]["ga_data"]["riskParams"])
                _data = _request.post(_url, _payload).json()
                gt = _data["data"]["geetest"]["gt"]
                challenge = _data["data"]["geetest"]["challenge"]
                token = _data["data"]["token"]
                # https://passport.bilibili.com/x/passport-login/captcha?source=main_web
                # challenge = "7e4a9557299685fb82c41972b63a42fc"
                # gt = "ac597a4506fee079629df5d8b66dd4fe"
                yield [gr.update(value="进行验证码验证", visible=True), gr.update(), gr.update(),
                       gr.update(visible=True), gr.update(value=gt), gr.update(value=challenge)]
                while geetest_validate == "" or geetest_seccode == "":
                    continue
                logging.info(f"geetest_validate: {geetest_validate},geetest_seccode: {geetest_seccode}")
                _url = "https://api.bilibili.com/x/gaia-vgate/v1/validate"
                csrf = _request.cookieManager.get_cookies_value("bili_jct")

                _payload = {
                    "challenge": challenge,
                    "token": token,
                    "seccode": geetest_seccode,
                    "csrf": csrf,
                    "validate": geetest_validate
                }
                _data = _request.post(_url, urlencode(_payload)).json()
                geetest_validate = ""
                geetest_seccode = ""
                if _data["code"] == 0:
                    logging.info("极验GeeTest认证 成功")
                else:
                    logging.info("极验GeeTest验证失败。")
                    yield [gr.update(value="极验GeeTest验证失败。重新验证", visible=True), gr.update(), gr.update(),
                           gr.update(),
                           gr.update(), gr.update()]
                    continue
                request_result = _request.post(
                    url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                    data=token_payload).json()
            tickets_info["token"] = request_result["data"]["token"]
            request_result = _request.get(
                url=f"https://show.bilibili.com/api/ticket/order/confirmInfo?token={tickets_info['token']}&voucher=&project_id={tickets_info['project_id']}").json()
            logging.info(f"confirmInfo: {request_result}")
            tickets_info["pay_money"] = request_result["data"]["pay_money"]
            tickets_info["timestamp"] = int(time.time()) * 100
            payload = format_dictionary_to_string(tickets_info)
            if time_start != '':
                time_difference = datetime.strptime(time_start, "%Y-%m-%dT%H:%M").timestamp() - time.time()
                if time_difference > 0:
                    logging.info(f'等待中')
                    yield [gr.update(value="等待中", visible=True), gr.update(visible=False), gr.update(), gr.update(),
                           gr.update(), gr.update()]
                    time.sleep(time_difference)  # 等待到指定的开始时间
            while isRunning:
                request_result = _request.post(
                    url=f"https://show.bilibili.com/api/ticket/order/createV2?project_id={tickets_info['project_id']}",
                    data=payload).json()
                errno = int(request_result["errno"])
                left_time_str = '无限' if mode == 0 else left_time
                logging.info(
                    f'错误码:{errno} 错误码解析: {errnoDict.get(errno, "未知错误码")}, 请求体: {request_result} 剩余次数: {left_time_str}')
                yield [gr.update(
                    value=f"正在抢票，具体情况查看终端控制台。\n 剩余次数: {left_time_str} 当前状态码: {errno}, 当前错误信息：{errnoDict.get(errno, '未知错误码')}",
                    visible=True), gr.update(visible=True), gr.update(), gr.update(), gr.update(), gr.update()]
                if errno == 0:
                    qrcode_url = get_qrcode_url(_request, request_result["data"]["token"], tickets_info['project_id'],
                                                request_result["data"]['orderId'])
                    qr_gen = qrcode.QRCode()
                    qr_gen.add_data(qrcode_url)
                    qr_gen.make(fit=True)
                    qr_gen_image = qr_gen.make_image()
                    yield [gr.update(value="生成付款二维码"), gr.update(),
                           gr.update(value=qr_gen_image.get_image(), visible=True), gr.update(), gr.update(),
                           gr.update()]
                time.sleep(interval / 1000.0)
                if mode == 1:
                    left_time -= 1
                    if left_time <= 0:
                        break
            yield [gr.update(value="抢票结束", visible=True), gr.update(visible=False), gr.update(), gr.update(),
                   gr.update(), gr.update()]
        except Exception as e:
            errno = request_result["errno"]
            left_time_str = '无限' if mode == 0 else left_time
            logging.info(e)
            logging.info(
                f'错误码:{errno} 错误码解析: {errnoDict.get(errno, "未知错误码")}, 请求体: {request_result},剩余次数: {left_time_str}')
            yield [
                gr.update(value=f"错误, 错误码:{errno} 错误码解析: {errnoDict.get(errno, '未知错误码')}", visible=True),
                gr.update(visible=False), gr.update(), gr.update(), gr.update(), gr.update()]
            time.sleep(interval / 1000.0)


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
    short_js = """                <script
                        src="http://libs.baidu.com/jquery/1.10.2/jquery.min.js"
                        rel="external nofollow">
                </script>
                <script src="https://static.geetest.com/static/js/gt.0.4.9.js"></script>
       """
    with gr.Blocks(head=short_js) as demo:
        gr.HTML("""
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome to My GitHub</title>
    <style>
        body {
            margin: 0;
            padding: 0;
        }
        .header {
            color: #fff;
            padding: 20px;
            text-align: center;
        }
        .header h1 {
            margin: 0;
            font-size: 36px;
        }
        .header p {
            font-size: 18px;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="header">
         <h1>B站会员购抢票🌈</h1>
        <p>⚠️此项目仅用于个人参考学习，切勿进行盈利，所造成的后果与本人无关。</p>
    </div>
</body>
</html> """)
        with gr.Tab("配置") as setting_tab:
            info_ui = gr.TextArea(info="此窗口为输出信息", label="输出信息", interactive=False, visible=False)
            with gr.Column() as first:
                ticket_id_ui = gr.Textbox(label="票ID", interactive=True,
                                          info="例如：要抢的网址是https://show.bilibili.com/platform/detail.html?id=84096\n"
                                               "就要填写 84096 ")
                ticket_id_btn = gr.Button("提交票id")
                with gr.Column(visible=False) as inner:
                    with gr.Row():
                        ticket_number_ui = gr.Number(label="票数目", value=1)
                        ticket_info_ui = gr.Dropdown(label="选票", interactive=True, type="index")
                    with gr.Row():
                        people_ui = gr.CheckboxGroup(label="实名人", interactive=True, type="index",
                                                     info="用于身份证实名认证，请确保曾经在b站填写过购买人（哔哩哔哩客户端-会员购-个人中心-购票人信息）的实名信息，否则这个表单不会有任何信息")
                        people_buyer_ui = gr.Dropdown(label="联系人", interactive=True, type="index",
                                                      info="选一个作为联系人，请确保曾经在b站填写过购买人的实名信息，否则这个表单不会有任何信息")
                        address_ui = gr.Dropdown(label="地址", interactive=True, type="index",
                                                 info="请确保曾经在b站填写过地址，否则这个表单不会有任何信息")

                    config_btn = gr.Button("生成配置")
                    config_output_ui = gr.Textbox(label="生成配置文件", show_copy_button=True, info="右上角粘贴",
                                                  visible=False)
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

                with gr.Row():
                    interval_ui = gr.Number(label="抢票间隔", value=1000, minimum=1,
                                            info="设置抢票任务之间的时间间隔（单位：毫秒），建议不要设置太小")
                    mode_ui = gr.Radio(label="抢票模式", choices=["无限", "有限"], value="无限",
                                       info="选择抢票的模式",
                                       type="index", interactive=True)
                    total_attempts_ui = gr.Number(label="总过次数", value=100, minimum=1, info="设置抢票的总次数",
                                                  visible=False)

                mode_ui.change(fn=lambda x: gr.update(visible=True) if x == 1 else gr.update(visible=False),
                               inputs=[mode_ui], outputs=total_attempts_ui)
                with gr.Row():
                    go_btn = gr.Button("开始抢票")
                    stop_btn = gr.Button("停止", visible=False)

                with gr.Row():
                    go_ui = gr.TextArea(info="此窗口为临时输出，具体请见控制台", label="输出信息", interactive=False,
                                        visible=False,
                                        show_copy_button=True, max_lines=10)
                    qr_image = gr.Image(label="使用微信或者支付宝扫码支付", visible=False)

                with gr.Row(visible=False) as gt_row:
                    gt_html_btn = gr.Button("点击打开抢票验证码（请勿多点！！）")
                    gt_html_finish_btn = gr.Button("完成验证码后点此此按钮")

                    gt_html = gr.HTML(value="""
                       <div>
                       <label for="datetime">如何点击无效说明，获取验证码失败，请勿多点</label>
                        <div id="captcha">
                        </div>
                    </div>""", label="验证码")
                # data
                time_tmp = gr.Textbox(visible=False)
                geetest_validate_ui = gr.Textbox(visible=False)
                geetest_seccode_ui = gr.Textbox(visible=False)
                gt_ui = gr.Textbox(visible=False)
                challenge_ui = gr.Textbox(visible=False)

                gt_html_finish_btn.click(None, None, geetest_validate_ui,
                                         js='() => {return captchaObj.getValidate().geetest_validate}')
                gt_html_finish_btn.click(None, None, geetest_seccode_ui,
                                         js='() => {return captchaObj.getValidate().geetest_seccode}')


                def update_geetest_validate(x):
                    global geetest_validate
                    geetest_validate = x


                def update_geetest_seccode(x):
                    global geetest_seccode
                    geetest_seccode = x


                geetest_validate_ui.change(fn=update_geetest_validate, inputs=geetest_validate_ui, outputs=None)
                geetest_seccode_ui.change(fn=update_geetest_seccode, inputs=geetest_seccode_ui, outputs=None)

                gt_html_btn.click(fn=None, inputs=[gt_ui, challenge_ui], outputs=None,
                                  js=f"""(x,y) => {{      initGeetest({{
                        gt: x,
                        challenge: y,
                        offline: false,
                        new_captcha: true,
                        product: "popup",
                        width: "300px",
                        https: true
                    }}, function (captchaObj) {{
               window.captchaObj = captchaObj;
                        captchaObj.appendTo('#captcha');
                    }})}}""")

                go_btn.click(fn=None, inputs=None, outputs=time_tmp,
                             js='(x) => {return (document.getElementById("datetime")).value;}')


                def stop():
                    global isRunning
                    isRunning = False
                    return [gr.update(value="抢票结束", visible=True), gr.update(visible=False),
                            gr.update(), gr.update()]


                go_btn.click(fn=start_go, inputs=[ticket_ui, time_tmp, interval_ui, mode_ui, total_attempts_ui],
                             outputs=[go_ui, stop_btn, qr_image, gt_row, gt_ui, challenge_ui], )
                stop_btn.click(fn=stop, inputs=None, outputs=[go_ui, stop_btn, qr_image, gt_row], )

                # 运行应用
    demo.launch()
