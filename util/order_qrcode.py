import time


def get_qrcode_url(_request, token, project_id, order_id):
    url = f"https://show.bilibili.com/api/ticket/order/createstatus?token={token}"
    f"&timestamp={int(round(time.time() * 1000))}"
    f"&project_id={project_id}&orderId={order_id}"
    data = _request.get(url).json()
    if data["errno"] == 0:
        return data["data"]["payParam"]["code_url"]
    else:
        return None
