from base64 import urlsafe_b64encode


def generate_token(
    project_id: int, screen_id: int, order_type: int, count: int, sku_id: int
) -> str:
    """
    生成Token
    # reference: https://github.com/biliticket/transition-ticket/blob/d32fcf4399bd04b96e382ae791514867ad97612c/util/Bilibili/__init__.py#L230
    Base64: URLSafeBase64
    """

    def encrypt(char: int, encrypt_type: str) -> str:
        """
        加密
        """
        match encrypt_type:
            # 6 位 timestamp 参数
            case "timestamp":
                v1 = char.to_bytes(5, "big")
                v2 = urlsafe_b64encode(v1).decode("utf-8").rstrip("=")
                return v2[1:8]
            # 4 位 projectId 参数
            case "projectId":
                v1 = char.to_bytes(3, "big")
                v2 = urlsafe_b64encode(v1).decode("utf-8").rstrip("=")
                return v2
            # 5 位 screenId 参数
            case "screenId":
                v1 = char.to_bytes(4, "big")
                v2 = urlsafe_b64encode(v1).decode("utf-8").rstrip("=")
                return v2[1:6]
            # 1 位 orderType 参数
            case "orderType":
                v1 = char.to_bytes(2, "big")
                v2 = urlsafe_b64encode(v1).decode("utf-8").rstrip("=")
                return v2[2:3]
            # 2 位 count 参数
            case "count":
                v1 = char.to_bytes(1, "big")
                v2 = urlsafe_b64encode(v1).decode("utf-8").rstrip("=")
                return v2
            # 5 位 skuId 参数
            case "skuId":
                v1 = char.to_bytes(5, "big")
                v2 = urlsafe_b64encode(v1).decode("utf-8").rstrip("=")
                return v2[2:7]
            case _:
                return ""

    p1 = "999999"
    p2 = encrypt(project_id, "projectId")
    p3 = encrypt(screen_id, "screenId")
    p4 = encrypt(order_type, "orderType")
    p5 = encrypt(count, "count")
    p6 = encrypt(sku_id, "skuId")

    token = "w" + p1 + "A" + p2 + "A" + p3 + p4 + "A" + p5 + p6 + "."

    return token
