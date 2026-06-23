import requests

url = "http://api.youdaili.com/v1/proxy/get?app_key=&app_secret=&count=&format=&protocol=&sep=&expire=&auth=&isp=&province=&city=&only="

payload = {}
headers = {}

response = requests.request("GET", url, headers=headers, data=payload)

print(response.text)