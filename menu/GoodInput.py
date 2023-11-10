import logging
import tkinter as tk
from tkinter import ttk

logging.basicConfig(level=logging.INFO)  # 设置日志级别


class NumberInputApp:
    def __init__(self, master, onSubmit):
        self.master = master
        self.master.title("数字输入")
        self.onSubmit = onSubmit

        instruction_frame = ttk.LabelFrame(master, text="输入说明")
        instruction_frame.grid(row=0, column=0, padx=10, pady=10, sticky=tk.W)

        instruction_text = ("输入商品的Id\n"
                            "例如网页https://show.bilibili.com/platform/detail.html?id=74924&from=pc_search\n"
                            "则输入74924 ,输入id的值\n")

        self.instruction_label = tk.Label(instruction_frame, text=instruction_text)
        self.instruction_label.grid(row=0, column=0, padx=10, pady=10, sticky=tk.W)

        entry_frame = ttk.Frame(master)
        entry_frame.grid(row=1, column=0, padx=10, pady=10, sticky=tk.W)

        self.number_entry = tk.Entry(entry_frame)
        self.number_entry.grid(row=0, column=0, padx=10, pady=10)

        self.submit_button = ttk.Button(entry_frame, text="提交", command=self.submit_number)
        self.submit_button.grid(row=0, column=1, padx=10, pady=10)

        self.displayed_number_label = tk.Label(master, text="")
        self.displayed_number_label.grid(row=2, column=0, pady=10)

    def submit_number(self):
        # Add your logic for handling the submitted number here
        entered_number = self.number_entry.get()
        fine, msg = self.onSubmit(entered_number)
        logging.info(f" Entered Number: {entered_number}")
        if fine:
            logging.info(f" Input over: {entered_number}")
            return
        else:
            self.displayed_number_label.config(text=msg)
        pass


if __name__ == "__main__":
    root = tk.Tk()
    app = NumberInputApp(root, lambda x: {})
    root.mainloop()
