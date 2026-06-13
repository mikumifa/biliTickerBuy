import base64
import os
import threading
import time
from argparse import Namespace

import gradio as gr
import loguru

from app_version import get_app_version
from util import get_application_path


def exit_app_ui():
    loguru.logger.info("程序退出")
    threading.Timer(2.0, lambda: os._exit(0)).start()
    gr.Info("程序将在弹出提示后退出")


def shutdown_app_process(delay_seconds: float = 1.0) -> None:
    threading.Timer(delay_seconds, lambda: os._exit(0)).start()


def ticker_cmd(args: Namespace):
    from tab.go import go_settings_tab, go_start_tab
    from tab.log import log_tab, refresh_task_panel
    from tab.problems import problems_tab
    from tab.settings import login_tab, setting_tab
    from tab.update import update_tab
    from util.log_web import attach_log_routes
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
                <h1>biliTickerBuy</h1>  
            </div>
            <div class="btb-hero__logo" aria-label="biliTickerBuy logo">
                <img class="btb-hero__logo-image" src="{icon_url}" alt="biliTickerBuy icon">
                
            </div>
        </div>
        <div class="btb-hero__notice">
            <span class="btb-hero__notice-mark">!</span>
            <span>
                此项目完全开源免费。开源地址：
                <a href="https://github.com/mikumifa/biliTickerBuy" target="_blank">https://github.com/mikumifa/biliTickerBuy</a>。
                请勿用于盈利，否则后果自负。
            </span>
        </div>
    </section>
    """

    def refresh_all_task_panels():
        go_refresh_token, go_panel_update = refresh_task_panel()
        log_refresh_token, log_panel_update = refresh_task_panel()
        return (
            go_refresh_token,
            go_panel_update,
            log_refresh_token,
            log_panel_update,
        )

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
            var TAB_ROUTE_MAP = {
                login: 'btb-tab-login-button',
                config: 'btb-tab-config-button',
                go: 'btb-tab-go-button',
                advanced: 'btb-tab-advanced-button',
                guide: 'btb-tab-guide-button',
                update: 'btb-tab-update-button',
                logs: 'btb-tab-logs-button'
            };
            function normalizeTabHash() {
                return (window.location.hash || '').replace(/^#\\/?/, '').trim();
            }
            function findSelectedTabKey() {
                for (var key in TAB_ROUTE_MAP) {
                    var button = document.getElementById(TAB_ROUTE_MAP[key]);
                    if (button && button.getAttribute('aria-selected') === 'true') {
                        return key;
                    }
                }
                return '';
            }
            function syncHashToCurrentTab(useReplace) {
                var key = findSelectedTabKey();
                if (!key) return;
                var nextHash = '#' + key;
                if (window.location.hash === nextHash) return;
                if (useReplace) {
                    window.history.replaceState(null, '', nextHash);
                } else {
                    window.history.replaceState(null, '', nextHash);
                }
            }
            function openTabFromHash() {
                var key = normalizeTabHash();
                if (!key || !TAB_ROUTE_MAP[key]) return false;
                var button = document.getElementById(TAB_ROUTE_MAP[key]);
                if (!button) return false;
                if (button.getAttribute('aria-selected') !== 'true') {
                    button.click();
                }
                return true;
            }
            function wireTabRouting() {
                var tabsRoot = document.getElementById('btb-main-tabs');
                if (!tabsRoot) {
                    setTimeout(wireTabRouting, 250);
                    return;
                }
                if (tabsRoot.dataset.routeBound === '1') {
                    return;
                }
                tabsRoot.dataset.routeBound = '1';
                Object.keys(TAB_ROUTE_MAP).forEach(function(key) {
                    var button = document.getElementById(TAB_ROUTE_MAP[key]);
                    if (!button) return;
                    button.addEventListener('click', function() {
                        window.history.replaceState(null, '', '#' + key);
                    });
                });
                setTimeout(function() {
                    if (!openTabFromHash()) {
                        syncHashToCurrentTab(true);
                    }
                }, 60);
                window.addEventListener('hashchange', function() {
                    setTimeout(openTabFromHash, 0);
                });
            }
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
                document.addEventListener('DOMContentLoaded',function(){enhance();wireTabRouting();});
            else {setTimeout(enhance,500);setTimeout(wireTabRouting,300);}
        })();
        </script>
        """,
    ) as demo:
        with gr.Column(elem_classes="btb-app-shell"):
            gr.HTML(header)
            with gr.Tabs(elem_id="btb-main-tabs", elem_classes="btb-top-tabs"):
                with gr.Tab("账号登录", id="login", elem_id="btb-tab-login"):
                    login_tab()
                with gr.Tab("生成配置", id="config", elem_id="btb-tab-config"):
                    setting_tab()
                with gr.Tab("操作抢票", id="go", elem_id="btb-tab-go"):
                    go_task_refresh_token, go_task_panel = go_start_tab()
                with gr.Tab("高级设置", id="advanced", elem_id="btb-tab-advanced"):
                    go_settings_tab()
                with gr.Tab("项目说明", id="guide", elem_id="btb-tab-guide"):
                    problems_tab()
                with gr.Tab("软件更新", id="update", elem_id="btb-tab-update"):
                    update_tab(demo)
                with gr.Tab("日志查看", id="logs", elem_id="btb-tab-logs"):
                    log_task_refresh_token, log_task_panel = log_tab()

        demo.load(
            fn=refresh_all_task_panels,
            outputs=[
                go_task_refresh_token,
                go_task_panel,
                log_task_refresh_token,
                log_task_panel,
            ],
        )

    is_docker = os.path.exists("/.dockerenv") or os.environ.get("BTB_DOCKER") == "1"
    demo.launch(
        share=args.share or is_docker,
        inbrowser=not is_docker,
        server_name=args.server_name,
        server_port=args.port,
        prevent_thread_lock=True,
    )
    attach_log_routes(demo.app)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        loguru.logger.info("收到 Ctrl+C，正在关闭主进程...")
        shutdown_app_process()
        demo.close()
        return
