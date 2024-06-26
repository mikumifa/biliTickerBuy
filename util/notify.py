import os
import platform


def pushOSMsg(title, message):
    plt = platform.system()
    if plt == "Darwin":
        command = '''
        osascript -e 'display notification "{message}" with title "{title}"'
        '''
    elif plt == "Linux":
        command = f'''
        notify-send "{title}" "{message}"
        '''
    elif plt == "Windows":
        import win10toast
        win10toast.ToastNotifier().show_toast(title, message, duration=3, icon_path='')
        return
    else:
        return
    os.system(command)
