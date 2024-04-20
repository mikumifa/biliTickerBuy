import time


def get_qrcode_url(_request, token, project_id, order_id):
    url = "https://show.bilibili.com/api/ticket/order/createstatus?token=" + token + "&timestamp=" + str(
        int(round(time.time() * 1000))) + "&project_id=" + str(project_id) + "&orderId=" + str(order_id)
    data = _request.get(url).json()
    if data["errno"] == 0:
        return data["data"]["payParam"]["code_url"]
    else:
        return None
