import json
import tkinter as tk
from tkinter import ttk
import datetime
import threading
import time
import logging
from time import sleep
from requests import utils
from selenium import webdriver
from selenium.common import WebDriverException
from tkcalendar import DateEntry

from common import format_dictionary_to_string
from config import cookies_config_path, issue_please_text
from util.BiliRequest import BiliRequest
from tkinter import scrolledtext

from util.webUtil import WebUtil


class TicketGrabbingApp:
    def __init__(self, master):
        self.master = master
        self.master.title("抢票配置")
        self._request = BiliRequest(cookies_config_path=cookies_config_path)
        self.webUtil = WebUtil(self._request.cookieManager.config)

        # Left Frame for Configuration File
        self.config_frame = ttk.LabelFrame(master, text="粘贴配置文件")
        self.config_frame.grid(row=0, column=0, padx=10, pady=10, sticky=tk.NSEW)

        self.config_text = tk.Text(self.config_frame, height=10, width=40)
        self.config_text.pack(padx=10, pady=10)

        # Right Frame for Ticket Grabbing Options
        self.options_frame = ttk.LabelFrame(master, text="抢票配置选项")
        self.options_frame.grid(row=0, column=1, padx=10, pady=10, sticky=tk.NSEW)

        # Options
        self.start_time_label = ttk.Label(self.options_frame,
                                          text="从哪个时间开始定时抢票, 不输入具体时间就是现在立刻抢票:")
        self.start_time_label.grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)

        # Entry widget for specifying the date
        # DateEntry for selecting the date
        self.start_date_entry = DateEntry(self.options_frame, width=12, background='darkblue',
                                          foreground='white', borderwidth=2, date_pattern='y/mm/dd')
        self.start_date_entry.grid(row=0, column=1, padx=10, pady=5, sticky=tk.W)

        # Entry widgets for specifying hours, minutes, and seconds
        self.hour_entry = ttk.Entry(self.options_frame, width=3)
        self.hour_entry.grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.hour_label = ttk.Label(self.options_frame, text="时")
        self.hour_label.grid(row=0, column=3, pady=5, sticky=tk.W)

        self.minute_entry = ttk.Entry(self.options_frame, width=3)
        self.minute_entry.grid(row=0, column=4, padx=5, pady=5, sticky=tk.W)
        self.minute_label = ttk.Label(self.options_frame, text="分")
        self.minute_label.grid(row=0, column=5, pady=5, sticky=tk.W)

        self.second_entry = ttk.Entry(self.options_frame, width=3)
        self.second_entry.grid(row=0, column=6, padx=5, pady=5, sticky=tk.W)
        self.second_label = ttk.Label(self.options_frame, text="秒")
        self.second_label.grid(row=0, column=7, pady=5, sticky=tk.W)

        #        b站没见到分控 不用延迟, 直接猛猛的强
        #         self.sleeptime_label = ttk.Label(self.options_frame, text="设置抢票间隔, 不写默认间隔1s:")
        #         self.sleeptime_label.grid(row=1, column=1, pady=5, sticky=tk.W)
        #         self.sleeptime_entry = ttk.Entry(self.options_frame, width=3)
        #         self.sleeptime_entry.grid(row=1, column=2, padx=5, pady=5, sticky=tk.W)
        #         self.sleeptimeLast_label = ttk.Label(self.options_frame, text="秒")
        #         self.sleeptimeLast_label.grid(row=1, column=3, pady=5, sticky=tk.W)

        self.tryTime_label = ttk.Label(self.options_frame,
                                       text="设置抢票尝试次数, 不写默认10次, 写-1表示一直持续下去(可以用来捡漏??):")
        self.tryTime_label.grid(row=1, column=0, pady=5, sticky=tk.W)
        self.tryTime_entry = ttk.Entry(self.options_frame, width=12)
        self.tryTime_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        self.tryTimeLast_label = ttk.Label(self.options_frame, text="次")
        self.tryTimeLast_label.grid(row=1, column=2, pady=5, sticky=tk.W)

        # self.thread_count_label = ttk.Label(self.options_frame, text="使用抢票的线程个数:")
        # self.thread_count_label.grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)
        # self.thread_count_entry = ttk.Entry(self.options_frame)
        # self.thread_count_entry.grid(row=1, column=1, padx=10, pady=5, sticky=tk.W)

        self.status_label = scrolledtext.ScrolledText(master, wrap=tk.WORD, width=100, height=10)
        self.status_label.grid(row=2, column=0, columnspan=2, pady=10)

        # Submit Button
        self.submit_button = ttk.Button(master, text="开始抢票", command=self.start_grabbing)
        self.submit_button.grid(row=3, column=0, columnspan=2, pady=10)

        # Current Time Display
        self.current_time_label = ttk.Label(master, text="")
        self.current_time_label.grid(row=4, column=0, columnspan=2, pady=10)
        self.isStartCrabbing = False

        # Time Difference Label
        self.time_difference_label = ttk.Label(master, text="")
        self.time_difference_label.grid(row=5, column=0, columnspan=2, pady=10)

        # Update current time every second
        self.update_current_time()

    def display_time_difference(self):
        # Get the selected date and time
        selected_date = self.start_date_entry.get_date()
        selected_time = None
        try:
            selected_time = datetime.time(
                int(self.hour_entry.get()),
                int(self.minute_entry.get()),
                int(self.second_entry.get())
            )
        except Exception as e:
            return
        selected_datetime = datetime.datetime.combine(selected_date, selected_time)
        # Calculate the time difference
        current_datetime = datetime.datetime.now()
        time_difference = selected_datetime - current_datetime
        # Display the time difference
        self.time_difference_label.config(text=f"距离抢票开始还有：{time_difference}")

    def start_grabbing(self):

        config_content = self.config_text.get("1.0", tk.END).strip()
        config_content = json.loads(config_content)
        start_date_str = self.start_date_entry.get()
        hours = self.hour_entry.get()
        minutes = self.minute_entry.get()
        seconds = self.second_entry.get()
        # thread_count = self.thread_count_entry.get()
        thread_count = 1
        # Validate inputs and start grabbing in a new thread

        if hours == '' and minutes == '' and seconds == '':
            grabbing_thread = threading.Thread(target=self.grab_tickets,
                                               args=(config_content, datetime.datetime.now(), thread_count))
            grabbing_thread.start()
            return

        try:

            hours, minutes, seconds, thread_count = map(int, (hours, minutes, seconds, thread_count))
            if not (0 <= hours <= 23) or not (0 <= minutes <= 59) or not (0 <= seconds <= 59):
                raise ValueError("Invalid time values. Please use 24-hour format.")
            if not config_content:
                error_message = "配置文件为空，请粘贴有效的配置内容。"
                result = {"success": False, "status": f"{error_message}"}
                self.display_status(result)
                logging.error(result)
                return
                # Parse date string into datetime.date object
            start_date = datetime.datetime.strptime(start_date_str, "%Y/%m/%d").date()
            # Combine date and time
            start_datetime = datetime.datetime.combine(start_date, datetime.time(hours, minutes, seconds))
            # Start grabbing in a new thread
            grabbing_thread = threading.Thread(target=self.grab_tickets,
                                               args=(config_content, start_datetime, thread_count))
            grabbing_thread.start()
        except ValueError as e:
            error_message = f"输入错误, 有空没输入, 或者输入错误(不能有空格)"
            result = {"success": False, "status": f"{error_message}"}
            self.display_status(result)
            logging.error(result)

    def grab_tickets(self, config_content, start_datetime, thread_count):
        self.isStartCrabbing = True

        tryTimeLeft = 10 if self.tryTime_entry.get() == "" else int(self.tryTime_entry.get())
        while True:
            try:
                current_datetime = datetime.datetime.now()
                time_difference = start_datetime - current_datetime
                if time_difference.total_seconds() > 0:
                    continue
                # Start Process token tel buyer pay_money timestamp
                # token
                token_payload = {
                    "count": config_content["count"],
                    "screen_id": config_content["screen_id"],
                    "order_type": 1,
                    "project_id": config_content["project_id"],
                    "sku_id": config_content["sku_id"],
                    "token": "",
                }
                res = self._request.post(
                    url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={config_content['project_id']}",
                    data=token_payload)
                logging.info(f"res.text: {res.text}")
                if "token" not in res.json()["data"]:
                    result = {"success": False, "status": f"抢票失败：{str(res.json())}, 还剩下{tryTimeLeft}次"}
                    self.display_status(result)

                    tryTimeLeft -= 1
                    if tryTimeLeft == 0:
                        result = {"success": False,
                                  "status": f"失败次数过多, 自动停止, 可能是抢票时机还没到?? {issue_please_text}"}
                        self.display_status(result)
                        break
                    continue

                ## 到此处, 就算网不好, 必然有token

                ## 确定有token时候, 再去检查时候有验证码
                if res.json()["data"]["shield"]["verifyMethod"]:
                    result = {"success": False, "status": f"遇到验证码：{res.json()['data']['shield']['naUrl']}"}
                    self.display_status(result)
                    naUrl = res.json()["data"]["shield"]["naUrl"]
                    self.webUtil.driver.get(naUrl)
                config_content["token"] = res.json()["data"]["token"]
                ## 已经完成验证码 ,下面应该不断的处理订单的生成

                while True:
                    try:
                        order_info = self._request.get(
                            url=f"https://show.bilibili.com/api/ticket/order/confirmInfo?token={config_content['token']}&voucher=&project_id={config_content['project_id']}").json()
                        contact_info = order_info["data"].get("contact_info", {})
                        # tel buyer
                        if config_content["tel"] == "" and contact_info:
                            config_content["tel"] = contact_info["tel"]
                            config_content["buyer"] = config_content["username"]

                        # pay_money
                        config_content["pay_money"] = order_info["data"]["pay_money"]
                        # timestamp
                        config_content["timestamp"] = int(time.time()) * 100

                        payload = format_dictionary_to_string(config_content)

                        #  已完成所有信息的填写
                        creat_request_result = self._request.post(
                            url=f"https://show.bilibili.com/api/ticket/order/createV2?project_id={config_content['project_id']}",
                            data=payload).json()
                        if "token" not in creat_request_result:
                            # 在申请订单环节产生的所有错误都应当重新申请
                            result = {"success": False,
                                      "status": f"休息3秒,抢票失败：{creat_request_result['msg']}"}
                            self.display_status(result)
                            raise Exception
                        result = {"success": True, "status": f"抢票请求发送{str(creat_request_result)}"}
                        self.display_status(result)
                        # 如果返回结果里面有token, 那么成功, 应当return
                        return
                    except Exception as e:
                        sleep(3)
                        continue

            except Exception as e:
                result = {"success": False, "status": f"抢票失败：{str(e)}"}
                self.display_status(result)

    def display_status(self, result):
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_line = f"{current_time} - {'成功' if result['success'] else '失败'}: {result['status']}\n"
        self.status_label.insert(tk.END, status_line)

    def update_current_time(self):
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        if self.isStartCrabbing:
            self.display_time_difference()
        self.current_time_label.config(text=f"当前时间：{current_time}")
        self.master.after(1000, self.update_current_time)  # Update every second


if __name__ == "__main__":
    root = tk.Tk()
    app = TicketGrabbingApp(root)
    root.mainloop()
