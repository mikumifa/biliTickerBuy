import logging
import time
import tkinter as tk
from tkinter import ttk

from config import cookies_config_path, issue_please_text
from menu.GoodInput import NumberInputApp
from menu.OrderConfig import OrderConfigWindow
from menu.SelectProfileTable import SelectProfileTable
from menu.SelectTicketsTable import TicketBookingApp
from menu.TicketGrabbing import TicketGrabbingApp
from util.BiliRequest import BiliRequest


def onSubmitTicket(buy_info):
    projectId = buy_info["project_id"]
    token_payload = {
        "count": buy_info["count"],
        "screen_id": buy_info["ticket"]["screen_id"],
        "order_type": 1,
        "project_id": buy_info["project_id"],
        "sku_id": buy_info["ticket"]["id"],
        "token": "",
    }
    _request = BiliRequest(cookies_config_path=cookies_config_path)
    logging.info(f"token_payload: {token_payload}")
    res = _request.post(
        url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={projectId}", data=token_payload)
    logging.info(f"res.text: {res.text}")
    token = ""
    if "token" in res.json()["data"]:
        token = res.json()["data"]["token"]

    order_info = _request.get(
        url=f"https://show.bilibili.com/api/ticket/order/confirmInfo?token={token}&voucher=&project_id={projectId}")
    contact_info = order_info.json()["data"].get("contact_info", {})
    logging.info(f"contact_info: {contact_info}")
    ts = int(time.time()) * 1000
    buyer_info = []
    delivery_info = {}
    res = _request.get(url=f"https://show.bilibili.com/api/ticket/buyer/list?is_default&projectId={projectId}")
    print(res.text)
    addr_res = _request.get(url="https://show.bilibili.com/api/ticket/addr/list")
    print(addr_res.text)
    root = tk.Toplevel()

    def update_buyer_info(x):
        nonlocal buyer_info
        buyer_info = x

    def update_addr_info(x):
        nonlocal delivery_info
        delivery_info = x[0]

    selectProfileTable = SelectProfileTable(root, res.json(), addr_res.json(), max_selections=buy_info["count"],
                                            onSubmitPersons=update_buyer_info, onSubmitAddr=update_addr_info)
    root.mainloop()
    #  "isBuyerInfoVerified": true,
    # "isBuyerValid": true
    for buyer in buyer_info:
        buyer["isBuyerInfoVerified"] = "true"
        buyer["isBuyerValid"] = "true"
    if not contact_info:
        contact_info = {}
    order_config = {
        "count": buy_info["count"],
        "screen_id": buy_info["ticket"]["screen_id"],
        "project_id": buy_info["project_id"],
        "sku_id": buy_info["ticket"]["id"],
        "token": token,
        "order_type": 1,
        "pay_money": order_info.json()["data"].get("pay_money", ""),
        "timestamp": ts,
        "buyer_info": buyer_info,
        "buyer": buyer_info[0]["name"],
        "tel": buyer_info[0]["tel"],
        "deliver_info": {"name": delivery_info["name"], "tel": delivery_info["phone"], "addr_id": delivery_info["id"],
                         "addr": delivery_info["prov"] + delivery_info["city"] + delivery_info["area"] + delivery_info[
                             "addr"]}
    }

    logging.info(order_config)
    root = tk.Toplevel()
    order_config_window = OrderConfigWindow(root, order_config)
    root.mainloop()
    return True, "成功"


def onSubmitNumber(num):
    try:
        num = int(num)
        payload = {}

        _request = BiliRequest(cookies_config_path=cookies_config_path)
        res = _request.get(
            url=f"https://show.bilibili.com/api/ticket/project/get?version=134&id={num}&project_id={num}")
        if res.json()["data"] == {}:
            raise KeyError()
        root = tk.Toplevel()
        ticketBookingApp = TicketBookingApp(root, res.json(), onSubmitTickets=onSubmitTicket)
        root.mainloop()

    except ValueError as e:
        return False, "不是数字" + issue_please_text

    except KeyError as e:
        return False, "商品id错误 " + issue_please_text

    return True, "成功"


class TicketOptionsApp:
    def __init__(self, master):
        self.master = master
        self.master.title("抢票选项")

        # Option Frame
        self.option_frame = ttk.LabelFrame(master, text="选项")
        self.option_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # Radio Buttons
        self.option_var = tk.StringVar()
        self.config_option_radio = ttk.Radiobutton(self.option_frame, text="配置&抢票选项", variable=self.option_var,
                                                   value="config")
        self.config_option_radio.grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)

        self.start_option_radio = ttk.Radiobutton(self.option_frame, text="已经生成配置文件，开始抢票选项",
                                                  variable=self.option_var, value="start")
        self.start_option_radio.grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)

        # Submit Button
        self.submit_button = ttk.Button(master, text="开始", command=self.submit_options)
        self.log_button = ttk.Button(master, text="导出日志", command=self.export_log)
        self.submit_button.pack(pady=10)
        self.log_button.pack(pady=10)

    def submit_options(self):
        selected_option = self.option_var.get()
        if selected_option == "config":
            logging.info("配置&抢票选项")
            root = tk.Toplevel()
            numberInputApp = NumberInputApp(root, onSubmit=onSubmitNumber)
            root.mainloop()
        elif selected_option == "start":
            logging.info("已经生成配置文件，开始抢票选项")
            root = tk.Toplevel()
            ticketGrabbingApp = TicketGrabbingApp(root)
            root.mainloop()
        else:
            logging.info("请选择一个选项")

    def export_log(self):
        with open("log/log.txt", 'r') as file:
            log_content = file.read()
        with open("log.txt", 'w') as file:
            # 将修改后的内容写入文件
            file.write(log_content)


if __name__ == "__main__":
    root = tk.Tk()
    app = TicketOptionsApp(root)
    root.mainloop()
