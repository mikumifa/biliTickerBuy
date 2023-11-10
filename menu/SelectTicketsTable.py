import logging
import tkinter as tk
from tkinter import ttk

from config import cookies_config_path
from util.BiliRequest import BiliRequest
from util.JsonUtil import ProjectInfo


class TicketBookingApp:
    def __init__(self, master, data, onSubmitTickets):
        self.projectInfo = ProjectInfo(data)
        self.onSubmitTickets = onSubmitTickets
        self.master = master
        self.master.title(self.projectInfo.get_name())
        # 数据
        self.ticket_data = self.projectInfo.get_screen_list()
        # 列表框
        self.listbox = tk.Listbox(master, selectmode=tk.SINGLE, width=50)
        self.listbox.grid(row=0, column=0, padx=10, pady=10, sticky=tk.W)
        self.ticket_list = []
        # 在列表框中添加票种信息
        for screen in self.ticket_data:
            screen_name = screen["name"]
            screen_id = screen["id"]
            for ticket in screen["ticket_list"]:
                ticket_desc = ticket['desc']
                ticket_price = ticket['price']

                ticket["screen"] = screen_name
                ticket["screen_id"] = screen_id
                ticket_can_buy = "可购买" if ticket['clickable'] else "无法购买"
                color = "green" if ticket['clickable'] else "red"
                self.ticket_list.append(ticket)
                self.listbox.insert(tk.END, f"{screen_name} - {ticket_desc} - ￥{ticket_price / 100} - {ticket_can_buy}")
                self.listbox.itemconfig(tk.END, {'fg': color})
                # 详细信息文本框
        self.detail_text = tk.Text(master, height=10, width=40)
        self.detail_text.grid(row=0, column=1, padx=10, pady=10, sticky=tk.W)
        # 数量标签
        self.quantity_label = ttk.Label(master, text="选择数量:")
        self.quantity_label.grid(row=1, column=0, padx=10, pady=10, sticky=tk.W)

        # 数量输入框
        self.quantity_var = tk.StringVar()
        self.quantity_entry = ttk.Entry(master, textvariable=self.quantity_var)
        self.quantity_entry.grid(row=1, column=1, padx=10, pady=10, sticky=tk.W)

        # 提交按钮
        self.submit_button = ttk.Button(master, text="提交", command=self.submit_booking)
        self.submit_button.grid(row=2, column=0, columnspan=2, pady=10)

        self.displayed_info_label = tk.Label(master, text="")
        self.displayed_info_label.grid(row=2, column=0, pady=10)
        # 列表框绑定事件
        self.listbox.bind('<<ListboxSelect>>', self.display_ticket_details)

    def display_ticket_details(self, event):
        selected_index = self.listbox.curselection()
        if selected_index:
            selected_ticket = self.ticket_list[selected_index[0]]
            ticket_details = (f"场次: {selected_ticket['screen']}\n"
                              f"票名: {selected_ticket['desc']}\n"
                              f"价格: ￥{selected_ticket['price'] / 100}")
            self.detail_text.delete(1.0, tk.END)  # 清空文本框
            self.detail_text.insert(tk.END, ticket_details)

    def submit_booking(self):
        selected_index = self.listbox.curselection()
        if selected_index:
            selected_ticket = self.ticket_list[selected_index[0]]
            quantity = self.quantity_var.get()
            try:
                quantity = int(self.quantity_var.get().strip())
            except ValueError:
                logging.warning(f"输入错误数字 {quantity}")
                return False, "输入错误的数字"
            logging.info(f"选择了 {quantity} 张 {selected_ticket['screen']} + {selected_ticket['desc']}.")
            fine, msg = self.onSubmitTickets({
                "project_id": self.projectInfo.data["id"],
                "count": quantity,
                "ticket": selected_ticket
            })
            if fine:
                pass
            else:
                self.displayed_info_label.config(text=msg)


if __name__ == "__main__":
    payload = {}
    _request = BiliRequest(cookies_config_path=cookies_config_path)
    res = _request.get(url="https://show.bilibili.com/api/ticket/project/get?version=134&id=74924&project_id=74924")
    root = tk.Tk()
    app = TicketBookingApp(root, res.json(), lambda x: {})
    root.mainloop()
