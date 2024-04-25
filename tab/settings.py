from datetime import datetime

import gradio as gr
from loguru import logger

from config import cookies_config_path
from util.bili_request import BiliRequest

buyer_value = []
addr_value = []
ticket_value = []


def on_submit_ticket_id(num):
    global buyer_value
    global addr_value
    global ticket_value

    try:
        buyer_value = []
        addr_value = []
        ticket_value = []
        num = int(num)
        bili_request = BiliRequest(cookies_config_path=cookies_config_path)
        res = bili_request.get(
            url=f"https://show.bilibili.com/api/ticket/project/getV2?version=134&id={num}&project_id={num}"
        )
        ret = res.json()
        logger.debug(ret)

        data = ret["data"]
        ticket_str_list = []

        project_id = data["id"]
        project_name = data["name"]

        project_start_time = datetime.fromtimestamp(data["start_time"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        project_end_time = datetime.fromtimestamp(data["end_time"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        venue_info = data["venue_info"]
        venue_name = venue_info["name"]
        venue_address = venue_info["address_detail"]

        for screen in data["screen_list"]:
            screen_name = screen["name"]
            screen_id = screen["id"]
            for ticket in screen["ticket_list"]:
                ticket_desc = ticket["desc"]
                ticket_price = ticket["price"]

                ticket["screen"] = screen_name
                ticket["screen_id"] = screen_id
                ticket_can_buy = "可购买" if ticket["clickable"] else "无法购买"
                ticket_str = f"{screen_name} - {ticket_desc} - ￥{ticket_price / 100} - {ticket_can_buy}"
                ticket_str_list.append(ticket_str)
                ticket_value.append({"project_id": project_id, "ticket": ticket})

        buyer_json = bili_request.get(
            url=f"https://show.bilibili.com/api/ticket/buyer/list?is_default&projectId={project_id}"
        ).json()
        logger.debug(buyer_json)
        addr_json = bili_request.get(
            url="https://show.bilibili.com/api/ticket/addr/list"
        ).json()
        logger.debug(addr_json)

        buyer_value = buyer_json["data"]["list"]
        buyer_str_list = [
            f"{item['name']}-{item['personal_id']}" for item in buyer_value
        ]
        addr_value = addr_json["data"]["addr_list"]
        addr_str_list = [
            f"{item['addr']}-{item['name']}-{item['phone']}" for item in addr_value
        ]

        return [
            gr.update(choices=ticket_str_list),
            gr.update(choices=buyer_str_list),
            gr.update(choices=buyer_str_list),
            gr.update(choices=addr_str_list),
            gr.update(visible=True),
            gr.update(
                value=f"获取票信息成功:\n展会名称：{project_name}\n"
                      f"开展时间：{project_start_time} - {project_end_time}\n场馆地址：{venue_name} {venue_address}",
                visible=True,
            ),
        ]
    except Exception as e:
        return [
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(value=e, visible=True),
        ]


def on_submit_all(ticket_id, ticket_info, people_indices, people_buyer_index, address_index):
    try:
        # if ticket_number != len(people_indices):
        #     return gr.update(
        #         value="生成配置文件失败，保证选票数目和购买人数目一致", visible=True
        #     )
        ticket_cur = ticket_value[ticket_info]
        people_cur = [buyer_value[item] for item in people_indices]
        people_buyer_cur = buyer_value[people_buyer_index]
        if str(ticket_id) != str(ticket_cur["project_id"]):
            return [gr.update(value="当前票信息已更改，请点击“获取票信息”按钮重新获取", visible=True),
                    gr.update(value={})]
        address_cur = addr_value[address_index]
        config_dir = {
            "count": len(people_indices),
            "screen_id": ticket_cur["ticket"]["screen_id"],
            "project_id": ticket_cur["project_id"],
            "sku_id": ticket_cur["ticket"]["id"],
            "order_type": 1,
            "buyer_info": people_cur,
            "buyer": people_buyer_cur["name"],
            "tel": people_buyer_cur["tel"],
            "deliver_info": {
                "name": address_cur["name"],
                "tel": address_cur["phone"],
                "addr_id": address_cur["id"],
                "addr": address_cur["prov"]
                        + address_cur["city"]
                        + address_cur["area"]
                        + address_cur["addr"],
            },
        }
        return [gr.update(), gr.update(value=config_dir, visible=True)]
    except Exception as e:
        logger.exception(e)
        return [gr.update(value="生成错误，仔细看看你可能有哪里漏填的", visible=True), gr.update(value={})]


def setting_tab():
    gr.Markdown("""
> **补充**
>
> 保证自己在抢票前，已经配置了地址和购买人信息(就算不需要也要提前填写)
>
> - 地址 ： 会员购中心->地址管理
> - 购买人信息：会员购中心->购买人信息
""")
    info_ui = gr.TextArea(
        info="此窗口为输出信息", label="输出信息", interactive=False, visible=False
    )
    with gr.Column():
        ticket_id_ui = gr.Textbox(
            label="票 ID",
            interactive=True,
            info="例如：要抢的网址是 https://show.bilibili.com/platform/detail.html?id=84096 就要填写 84096",
        )
        ticket_id_btn = gr.Button("获取票信息")
        with gr.Column(visible=False) as inner:
            with gr.Row():
                people_ui = gr.CheckboxGroup(
                    label="身份证实名认证",
                    interactive=True,
                    type="index",
                    info="必填，在哔哩哔哩客户端-会员购-个人中心-购票人信息中添加",
                )
                ticket_info_ui = gr.Dropdown(
                    label="选票",
                    interactive=True,
                    type="index",
                    info="必填，此处的「无法购买」仅代表当前状态",
                )
            with gr.Row():
                people_buyer_ui = gr.Dropdown(
                    label="联系人",
                    interactive=True,
                    type="index",
                    info="必填，如果候选项为空请到「购票人信息」添加",
                )
                address_ui = gr.Dropdown(
                    label="地址",
                    interactive=True,
                    type="index",
                    info="必填，如果候选项为空请到「地址管理」添加",
                )

            config_btn = gr.Button("生成配置")
            config_output_ui = gr.JSON(
                label="生成配置文件（右上角复制）",
                visible=False,
            )
            config_btn.click(
                fn=on_submit_all,
                inputs=[
                    ticket_id_ui,
                    ticket_info_ui,
                    people_ui,
                    people_buyer_ui,
                    address_ui,
                ],
                outputs=[info_ui, config_output_ui]
            )

        ticket_id_btn.click(
            fn=on_submit_ticket_id,
            inputs=ticket_id_ui,
            outputs=[
                ticket_info_ui,
                people_ui,
                people_buyer_ui,
                address_ui,
                inner,
                info_ui,
            ],
        )
