import logging
import time
import tkinter as tk

from config import configure_global_logging
from menu.TicketOptions import TicketOptionsApp

if __name__ == '__main__':
    configure_global_logging()
    root = tk.Tk()
    numberInputApp = TicketOptionsApp(root)
    root.mainloop()
