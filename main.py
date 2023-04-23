import datetime
import time
import winsound
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


TargetTime = "2023-04-16 16:39:00.00000000"  # 设置抢购时间
WebDriver = webdriver.Chrome()
WebDriver.get(
    "https://show.bilibili.com/platform/detail.html?id=72320&from=pc_ticketlist")  # 输入目标购买页面
time.sleep(1)
# 等待页面加载完成
wait = WebDriverWait(WebDriver, 1)
print("进入购票页面成功")
WebDriver.find_element(By.CLASS_NAME, "nav-header-register").click()
print("请在10s内登录")
duration = 10000  # 持续时间为 10 秒钟，单位为毫秒
freq = 440  # 播放频率为 440 Hz
winsound.Beep(freq, duration)  # 播放系统嗡嗡声


while True:
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    print(now + "     " + TargetTime)
    if now >= TargetTime:
        WebDriver.refresh()
        break

while True:
    try:
        element = wait.until(EC.visibility_of_element_located(
            (By.XPATH, '/html/body/div/div[2]/div[2]/div[2]/div[4]/ul[1]/li[2]/div[1]')))
        element.click()
        # 等待抢票按钮出现并可点击
        element = wait.until(EC.element_to_be_clickable(
            (By.CLASS_NAME, 'product-buy.enable')))
        # 点击抢票按钮
        element.click()
        # time.sleep(5)
        print("进入购买页面成功")
    except BaseException as e:
        WebDriver.refresh()
        continue

    try:
        WebDriver.find_element(By.CLASS_NAME, "confirm-paybtn.active").click()
        print("订单创建完成，请在一分钟内付款")


        duration = 10000  # 持续时间为 10 秒钟，单位为毫秒
        freq = 440  # 播放频率为 440 Hz
        winsound.Beep(freq, duration)  # 播放系统嗡嗡声

        # time.sleep(60)
    except:
        print("无法点击创建订单")
