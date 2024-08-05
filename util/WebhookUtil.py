import json
import requests
import loguru

def send_webhook(url, payload):
    """
    发送Webhook通知。
    
    参数:
    - url (str): Webhook的URL。
    - payload (dict): 要发送的数据，包含标题和描述等。
    
    返回:
    - None
    """
    headers = {
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # 如果发生错误，则抛出HTTPError异常
        loguru.logger.info("Webhook消息发送成功")
    except requests.exceptions.HTTPError as http_err:
        loguru.logger.error(f"HTTP错误发生: {http_err}")
    except Exception as err:
        loguru.logger.error(f"消息发送失败: {err}")
