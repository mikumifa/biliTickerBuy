import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_argument('--headless')
driver = webdriver.Chrome(options=opts)
driver.get('http://127.0.0.1:7860')
time.sleep(5)
try:
    script = "return document.querySelector('[data-testid=\"dropdown\"]').outerHTML;"
    html = driver.execute_script(script)
    print("DROPDOWN HTML:")
    print(html)
    
    script2 = "return document.querySelector('.options') ? document.querySelector('.options').outerHTML : 'no options';"
    html2 = driver.execute_script(script2)
    print("OPTIONS HTML:")
    print(html2)
except Exception as e:
    print(e)
driver.quit()
