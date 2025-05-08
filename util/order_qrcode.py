import time


def get_qrcode_url(_request, order_id) -> str:
    url = f"https://show.bilibili.com/api/ticket/order/getPayParam?order_id={order_id}"
    data = _request.get(url).json()
    if data["errno"] == 0:
        return data["data"]["code_url"]
    raise ValueError("获取二维码失败")
