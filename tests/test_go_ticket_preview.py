from tab.go import _render_ticket_preview


def test_ticket_preview_appends_buyer_document_type():
    html = _render_ticket_preview(
        {
            "detail": "测试票档",
            "buyer_info": [
                {"name": "张三", "id_type": 0},
                {"name": "李四", "id_type": 1},
            ],
        }
    )

    assert "实名：张三（身份证）、李四（护照）" in html
