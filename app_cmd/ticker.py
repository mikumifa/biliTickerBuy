import base64
import os
import threading
from argparse import Namespace

import gradio as gr
import loguru

from app_version import get_app_version
from util import get_application_path


def exit_app_ui():
    loguru.logger.info("程序退出")
    threading.Timer(2.0, lambda: os._exit(0)).start()
    gr.Info("程序将在弹出提示后退出")


def ticker_cmd(args: Namespace):
    from tab.go import go_tab
    from tab.log import log_tab
    from tab.problems import problems_tab
    from tab.settings import setting_tab
    from tab.update import update_tab
    from util import LOG_DIR
    from util.LogConfig import loguru_config

    loguru_config(LOG_DIR, "app.log", enable_console=True, file_colorize=False)
    assets_dir = os.path.join(get_application_path(), "assets")
    icon_path = os.path.join(assets_dir, "icon.ico")
    css_path = os.path.join(assets_dir, "style.css")
    icon_url = ""
    if os.path.exists(icon_path):
        with open(icon_path, "rb") as icon_file:
            icon_url = "data:image/x-icon;base64," + base64.b64encode(
                icon_file.read()
            ).decode("ascii")

    app_version = get_app_version()

    header = f"""
    <section class="btb-hero">
        <div class="btb-hero__eyebrow">BiliTickerBuy · v{app_version}</div>
        <div class="btb-hero__grid">
            <div>
                <h1>B站会员购抢票</h1>
            </div>
            <div class="btb-hero__logo" aria-label="biliTickerBuy logo">
                <img class="btb-hero__logo-image" src="{icon_url}" alt="biliTickerBuy icon">
                
            </div>
        </div>
        <div class="btb-hero__notice">
            <span class="btb-hero__notice-mark">!</span>
            <span>
                此项目完全开源免费，
                <a href="https://github.com/mikumifa/biliTickerBuy" target="_blank">项目地址</a>。
                请勿用于盈利，使用后果自负。
            </span>
        </div>
    </section>
    """

    with gr.Blocks(
        title="biliTickerBuy",
        css=css_path,
        head="""
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600;700&family=Noto+Serif+SC:wght@600&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
        <script>
        (function(){
            function enhance(){
                var root=document.getElementById('btb-time-start');
                if(!root){setTimeout(enhance,300);return;}
                var input=root.querySelector('input[type="text"],textarea');
                if(!input){setTimeout(enhance,300);return;}
                if(root.dataset.enhanced) return;
                root.dataset.enhanced='1';
                var ghost=document.createElement('input');
                ghost.type='datetime-local';ghost.step='1';
                ghost.className='btb-picker-ghost';ghost.tabIndex=-1;
                var btn=document.createElement('button');
                btn.type='button';btn.className='btb-picker-trigger';
                btn.title='打开日历选择器';
                btn.innerHTML='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>';
                var wrapper=document.createElement('div');
                wrapper.className='btb-picker-wrap';
                wrapper.style.position='relative';
                wrapper.style.display='block';
                wrapper.style.width='100%';
                input.parentNode.insertBefore(wrapper,input);
                wrapper.appendChild(input);
                wrapper.appendChild(ghost);
                wrapper.appendChild(btn);
                btn.addEventListener('click',function(e){
                    e.preventDefault();e.stopPropagation();
                    if(input.value){
                        try{ghost.value=input.value.trim().replace(' ','T');}catch(ex){}
                    }
                    ghost.showPicker();
                });
                ghost.addEventListener('input',function(){
                    var v=this.value;if(!v)return;
                    var dt=v.replace('T',' ');
                    if(dt.length===16)dt+=':00';
                    var setter=Object.getOwnPropertyDescriptor(
                        Object.getPrototypeOf(input),'value'
                    ).set;
                    setter.call(input,dt);
                    input.dispatchEvent(new Event('input',{bubbles:true}));
                });
            }
            if(document.readyState==='loading')
                document.addEventListener('DOMContentLoaded',enhance);
            else setTimeout(enhance,500);
        })();
        </script>
        """,
    ) as demo:
        with gr.Column(elem_classes="btb-app-shell"):
            gr.HTML(header)
            with gr.Tabs(elem_classes="btb-top-tabs"):
                with gr.Tab("生成配置"):
                    setting_tab()
                with gr.Tab("操作抢票"):
                    go_tab(demo)
                with gr.Tab("项目说明"):
                    problems_tab()
                with gr.Tab("软件更新"):
                    update_tab(demo)
                with gr.Tab("日志查看"):
                    log_tab()

    is_docker = os.path.exists("/.dockerenv") or os.environ.get("BTB_DOCKER") == "1"
    demo.launch(
        share=args.share or is_docker,
        inbrowser=not is_docker,
        server_name=args.server_name,
        server_port=args.port,
    )
