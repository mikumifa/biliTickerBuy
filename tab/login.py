import json

import gradio as gr
from loguru import logger

from config import cookies_config_path
from util.bili_request import BiliRequest

names = []


@logger.catch
def login_tab():
    gr.Markdown("""
> **补充**
>
> 在这里，你可以
> 1. 去更改账号，
> 2. 查看当前程序正在使用哪个账号
> 3. 使用配置文件切换到另一个账号
>
""")
    main_request = BiliRequest(cookies_config_path=cookies_config_path)
    username_ui = gr.Text(
        main_request.get_request_name(),
        label="账号名称",
        interactive=False,
        info="当前账号的名称",
    )
    gr.Markdown("""🏵️ 登录""")
    info_ui = gr.TextArea(
        info="此窗口为输出信息", label="输出信息", interactive=False
    )
    add_btn = gr.Button("重新登录")
    with gr.Column() as out_col:
        out_btn = gr.Button("导出")
        login_config = gr.Text(
            label="导出登录信息，复制后粘贴到其他地方即可",
            visible=False,
            interactive=False,
            show_copy_button=True
        )

        def out():
            return gr.update(value=json.dumps(main_request.cookieManager.config), visible=True)

        out_btn.click(
            fn=out,
            inputs=None,
            outputs=login_config
        )
    with gr.Column() as in_col:
        in_btn = gr.Button("导入")
        in_text_ui = gr.Text(
            label="先将登录信息粘贴到此处，然后点击导入",
            interactive=True,
        )

        def in_fn(text):
            temp = main_request.cookieManager.config
            try:
                main_request.cookieManager.config = json.loads(text)
                main_request.cookieManager.dump_config()
                name = main_request.get_request_name()
                return [f"退出重启一下来保证完全更改", gr.update(name)]
            except Exception:
                main_request.cookieManager.config = temp
                main_request.cookieManager.dump_config()
                return ["配置文件错误，未修改", gr.update()]

        in_btn.click(
            fn=in_fn,
            inputs=in_text_ui,
            outputs=[info_ui, username_ui]
        )

    def add():
        temp = main_request.cookieManager.config
        yield ["将打开浏览器，请在浏览器里面重新登录", gr.update()]
        try:
            main_request.cookieManager.get_cookies_str_force()
            name = main_request.get_request_name()
            yield [f"退出重启一下来保证完全更改", gr.update(name)]
        except Exception:
            main_request.cookieManager.config = temp
            main_request.cookieManager.dump_config()
            yield ["配置文件错误，未修改", gr.update()]

    add_btn.click(
        fn=add,
        inputs=None,
        outputs=[info_ui, username_ui]
    )
