import time


def get_qrcode_url(_request, order_id):
    url = f"https://show.bilibili.com/api/ticket/order/getPayParam?order_id={order_id}"
    data = _request.get(url).json()
    try:
        if data["errno"] == 0:
            return data["data"]["code_url"]
        else:
            raise Exception
    except Exception:
        return None
