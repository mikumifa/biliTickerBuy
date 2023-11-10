import logging
import tkinter as tk
from tkinter import ttk
import logging
import time

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
    token = res.json()["data"]["token"]
    order_info = _request.get(
        url=f"https://show.bilibili.com/api/ticket/order/confirmInfo?token={token}&voucher=&project_id={projectId}")
    ts = int(time.time())
    contact_info = order_info.json()["data"]["contact_info"]
    order_config = {}
    if not contact_info:
        buyer_info = []
        res = _request.get(url=f"https://show.bilibili.com/api/ticket/buyer/list?is_default&projectId={projectId}")
        print(res.text)
        root = tk.Toplevel()

        def update_buyer_info(x):
            nonlocal buyer_info
            buyer_info = x

        selectProfileTable = SelectProfileTable(root, res.json(), max_selections=buy_info["count"],
                                                onSubmitPersons=update_buyer_info)
        root.mainloop()
        #  "isBuyerInfoVerified": true,
        # "isBuyerValid": true
        for buyer in buyer_info:
            buyer["isBuyerInfoVerified"] = "true"
            buyer["isBuyerValid"] = "true"

        order_config = {
            "count": buy_info["count"],
            "screen_id": buy_info["ticket"]["screen_id"],
            "project_id": buy_info["project_id"],
            "sku_id": buy_info["ticket"]["id"],
            "token": token,
            "order_type": 1,
            "pay_money": order_info.json()["data"]["pay_money"],
            "timestamp": ts,
            "buyer_info": buyer_info
        }
        logging.info(order_config)
    else:
        order_config = {
            "count": buy_info["count"],
            "screen_id": buy_info["ticket"]["screen_id"],
            "project_id": buy_info["project_id"],
            "sku_id": buy_info["ticket"]["id"],
            "token": token,
            "order_type": 1,
            "pay_money": order_info.json()["data"]["pay_money"],
            "timestamp": ts,
            "buyer": contact_info["username"],
            "tel": contact_info["tel"]
        }
        logging.info(order_config)

    ## test Create Order
    # creat_request_result = _request.post(
    #     url=f"https://show.bilibili.com/api/ticket/order/createV2?project_id={projectId}", data=order_config).json()
    # logging.info(creat_request_result)
    ##

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
        self.submit_button.pack(pady=10)

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


if __name__ == "__main__":
    root = tk.Tk()
    app = TicketOptionsApp(root)
    root.mainloop()
