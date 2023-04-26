import datetime
import time
import pyttsx3
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

engine = pyttsx3.init()
day = 1
buy_url = "https://show.bilibili.com/platform/detail.html?id=72320&from=pc_ticketlist"
tick_xpath = f'/html/body/div/div[2]/div[2]/div[2]/div[4]/ul[1]/li[2]/div[{day}]'
# buy_url = "https://show.bilibili.com/platform/detail.html?id=71352&from=pc_ticketlist"
# tick_xpath = ''
# 加载配置文件
with open('./config.json', 'r') as f:
    config = json.load(f)


def voice(message):
    engine.setProperty('volume', 1.0)
    engine.say(message)
    engine.runAndWait()
    engine.stop()
    voice(message)


TargetTime = "2023-04-16 16:39:00.00000000"  # 设置抢购时间
WebDriver = webdriver.Chrome()
wait = WebDriverWait(WebDriver, 0.5)
if len(config["bilibili_cookies"]) == 0:
    WebDriver.get(
        buy_url)  # 输入目标购买页面
    WebDriver.maximize_window()
    time.sleep(1)
    WebDriver.find_element(By.CLASS_NAME, "nav-header-register").click()
    print("请登录")
    while True:
        try:
            WebDriver.find_element(By.CLASS_NAME, "nav-header-register")
        except:
            break
    time.sleep(5)
    config["bilibili_cookies"] = WebDriver.get_cookies()
    with open('./config.json', 'w') as f:
        json.dump(config, f, indent=4)
else:
    WebDriver.get(
        buy_url)  # 输入目标购买页面
    for cookie in config["bilibili_cookies"]:  # 利用cookies登录账号
        my_cookie = {
            'domain': cookie['domain'],
            'name': cookie['name'],
            'value': cookie['value'],
            'path': cookie['path'],
        }
        if 'expiry' in cookie:
            cookie['expiry'] = cookie['expiry']
        if 'httpOnly' in cookie:
            cookie['httpOnly'] = cookie['httpOnly']
        if 'sameSite' in cookie:
            cookie['sameSite'] = cookie['sameSite']
        if 'secure' in cookie:
            cookie['secure'] = cookie['secure']

        WebDriver.add_cookie(
            my_cookie
        )
        WebDriver.maximize_window()

while True:
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    print(now + "     " + TargetTime)
    if now >= TargetTime:
        WebDriver.refresh()
        break

while True:
    try:
        if tick_xpath != "":
            element = wait.until(EC.visibility_of_element_located(
                (By.XPATH, tick_xpath)))
            element.click()
        # 等待抢票按钮出现并可点击
        element = wait.until(EC.element_to_be_clickable(
            (By.CLASS_NAME, 'product-buy.enable')))
        # 点击抢票按钮
        element.click()
        # time.sleep(5)
        print("进入购买页面成功")
        break
    except:
        WebDriver.refresh()
        continue


element = None
while element is None:
    try:
        element = WebDriver.find_element(By.XPATH, '//*[@id="app"]/div[2]/div/div[5]/div[2]')
    except:
        continue
element.click()
print("订单创建完成，请在一分钟内付款")
voice('抢到票了，速归！')
time.sleep(60)
