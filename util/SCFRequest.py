from concurrent.futures import as_completed
from concurrent.futures.thread import ThreadPoolExecutor

import loguru
import requests

from config import configDB


def getTencentUrls():
    try:
        url_list = configDB.get("tencent::createOrder::url")
        urls = url_list.splitlines()
        return urls
    except Exception as e:
        loguru.logger.error(f"获取腾讯云函数url列表失败：{e}")
        return []


def createOrder(url_list, cookieStr, payload, project_id):
    requestBody = {
        "cookie": cookieStr,
        "project_id": project_id,
        "payload": payload,
    }

    def fetch_url(url):
        try:
            response = requests.get(url)
            response.raise_for_status()
            return url, response.status_code, response.json()
        except Exception as e:
            return url, None, str(e)

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(fetch_url, url): url for url in url_list}
        for future in as_completed(future_to_url):
            url, status_code, result = future.result()
            if status_code == 200:
                print(f"{url} 正常 - 结果{result}")  # Print a snippet of the result
            else:
                loguru.logger.error(f"{url} 产生错误 - {result}")
        return results
