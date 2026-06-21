from task.buy import _format_reprepare_reason


def test_format_reprepare_reason_includes_cause():
    assert _format_reprepare_reason("token过期") == "重新准备订单，原因：token过期"
