import tkinter as tk
from tkinter import ttk

from config import cookies_config_path
from util.BiliRequest import BiliRequest
from util.JsonUtil import ProfileInfo, AddrInfo


class SelectProfileTable:
    def __init__(self, master, data, addr_data, max_selections,onSubmitPersons,onSubmitAddr):
        self.profileInfo = ProfileInfo(data)
        self.addrInfo = AddrInfo(addr_data)
        self.master = master
        self.onSubmitPersons = onSubmitPersons
        self.onSubmitAddr = onSubmitAddr
        self.master.title("选择收货地址")
        self.persons = self.profileInfo.get_persons()
        self.addrs = self.addrInfo.get_addrs()
        self.max_selections = max_selections
        self.selected_indices = set()
        self.addr_indices=set()

        # select person
        self.listbox = tk.Listbox(master, selectmode=tk.MULTIPLE, width=50)
        self.listbox.grid(row=0, column=0, padx=10, pady=10, sticky=tk.W)
        for person in self.persons:
            name = person['name']
            self.listbox.insert(tk.END, f"{name}")
            self.listbox.itemconfig(tk.END, {'fg': "black"})

        # select address
        self.addr_listbox = tk.Listbox(master, selectmode=tk.SINGLE, width=50)
        self.addr_listbox.grid(row=1, column=0, padx=10, pady=10, sticky=tk.W)
        for addr in self.addrs:
            name = addr['name']
            addr_name = addr['addr']

            self.addr_listbox.insert(tk.END, f"收货人：{name}， 地址： {addr_name}")
            self.addr_listbox.itemconfig(tk.END, {'fg': "black"})

        self.detail_text = tk.Text(master, height=10, width=40)
        self.detail_text.grid(row=0, column=1, padx=10, pady=10, sticky=tk.W)

        self.addr_text=tk.Text(master, height=10, width=40)
        self.addr_text.grid(row=1, column=1, padx=10, pady=10, sticky=tk.W)

        self.submit_button = ttk.Button(master, text="提交", command=self.submit_booking)
        self.submit_button.grid(row=2, column=0, columnspan=2, pady=10)

        self.displayed_number_label = tk.Label(master, text="")
        self.displayed_number_label.grid(row=2, column=0, pady=10)

        self.listbox.bind('<<ListboxSelect>>', self.display_ticket_details)
        self.addr_listbox.bind('<<ListboxSelect>>', self.display_address_details)


    def display_ticket_details(self,event):
        selected_indices = self.listbox.curselection()
        if selected_indices:
            self.selected_indices = set(selected_indices)
            details = ""
            for index in selected_indices:
                selected_ticket = self.persons[index]
                details += f"名字: {selected_ticket['name']}\n" \
                           f"电话: {selected_ticket['tel']}\n" \
                           f"身份证: {selected_ticket['personal_id']}\n\n"
            self.detail_text.delete(1.0, tk.END)
            self.detail_text.insert(tk.END, details)

    def display_address_details(self,event):
        addr_indices = self.addr_listbox.curselection()
        if addr_indices:
            self.addr_indices = set(addr_indices)
            details = ""
            for index in addr_indices:
                selected_ticket = self.addrs[index]
                details += f"名字: {selected_ticket['name']}\n" \
                           f"电话: {selected_ticket['phone']}\n" \
                           f"地址: {selected_ticket['prov'] + selected_ticket['city'] + selected_ticket['area'] + selected_ticket['addr']}\n\n"

            self.addr_text.delete(1.0, tk.END)
            self.addr_text.insert(tk.END, details)

    def submit_booking(self):
        if len(self.selected_indices) == self.max_selections:
            persons = [self.persons[index] for index in self.selected_indices]
            addr=[self.addrs[index] for index in self.addr_indices]
            self.onSubmitPersons(persons)
            self.onSubmitAddr(addr)
            self.master.destroy()
            self.master.quit()  # Exit the mainloop
        else:
            msg = f"请选择 {self.max_selections} 人"
            self.displayed_number_label.config(text=msg)


if __name__ == "__main__":
    payload = {}
    _request = BiliRequest(cookies_config_path=cookies_config_path)
    res = _request.get(url="https://show.bilibili.com/api/ticket/buyer/list?is_default&projectId=74924")
    print(res.text)
    addr_res = _request.get(url="https://show.bilibili.com/api/ticket/addr/list")
    print(addr_res.text)

    root = tk.Tk()
    app = SelectProfileTable(root, res.json(), addr_res.json(), max_selections=3,onSubmitPersons=lambda x: print(x))
    root.mainloop()
