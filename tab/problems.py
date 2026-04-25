import gradio as gr


def problems_tab():
    html_content = """
    <div style="display: flex; flex-direction: column; gap: 24px;">
        <div class="btb-card btb-card-amber">
            <div class="btb-card-head" style="margin-bottom: 16px;">
                <h3 style="display: flex; align-items: center; gap: 8px;">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
                    抢票经验分享
                </h3>
            </div>
            <ul style="margin: 0; padding-left: 20px; line-height: 1.8; color: var(--text-secondary);">
                <li>抢票前，不要去提前抢还没有发售的票，会被B站封掉一段时间导致错过抢票。</li>
                <li>使用不同的多个账号抢票可以提高成功率。</li>
                <li>程序能保证用最快的速度发送订单请求，但是不保证这一次订单请求能够成功。所以不要完全依靠程序。</li>
                <li>现在各个平台抢票和秒杀机制都是进抽签池抽签，网速快发请求多快在拥挤的时候基本上没有效果。此时就要看你有没有足够的设备和账号来提高中签率。</li>
            </ul>
        </div>
        
        <div>
            <h3 style="margin-bottom: 16px; color: var(--text-primary);">项目资源</h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;">
                <a href="https://github.com/mikumifa/biliTickerBuy" target="_blank" class="btb-card btb-card-sky" style="text-decoration: none; display: flex; align-items: center; gap: 16px;">
                    <div style="background: var(--bg-surface); padding: 10px; border-radius: 12px; box-shadow: var(--shadow-subtle); color: var(--text-primary);">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>
                    </div>
                    <div>
                        <div style="font-weight: 600; color: var(--text-primary);">项目地址</div>
                        <div style="font-size: 12px; color: var(--text-secondary);">mikumifa/biliTickerBuy</div>
                    </div>
                </a>
                
                <a href="https://github.com/mikumifa/biliTickerBuy/discussions" target="_blank" class="btb-card" style="text-decoration: none; display: flex; align-items: center; gap: 16px;">
                    <div style="background: var(--bg-surface); padding: 10px; border-radius: 12px; box-shadow: var(--shadow-subtle); color: var(--text-primary);">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>
                    </div>
                    <div>
                        <div style="font-weight: 600; color: var(--text-primary);">讨论区 (Discussions)</div>
                        <div style="font-size: 12px; color: var(--text-secondary);">分享经验、交流心得</div>
                    </div>
                </a>
                
                <a href="https://github.com/mikumifa/biliTickerBuy/issues" target="_blank" class="btb-card btb-card-rose" style="text-decoration: none; display: flex; align-items: center; gap: 16px;">
                    <div style="background: var(--bg-surface); padding: 10px; border-radius: 12px; box-shadow: var(--shadow-subtle); color: var(--text-primary);">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    </div>
                    <div>
                        <div style="font-weight: 600; color: var(--text-primary);">问题反馈 (Issues)</div>
                        <div style="font-size: 12px; color: var(--text-secondary);">漏洞反馈与需求建议</div>
                    </div>
                </a>
                
                <a href="https://github.com/mikumifa/biliTickerBuy/wiki/%E6%8A%A2%E7%A5%A8%E8%AF%B4%E6%98%8E" target="_blank" class="btb-card" style="text-decoration: none; display: flex; align-items: center; gap: 16px;">
                    <div style="background: var(--bg-surface); padding: 10px; border-radius: 12px; box-shadow: var(--shadow-subtle); color: var(--text-primary);">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
                    </div>
                    <div>
                        <div style="font-weight: 600; color: var(--text-primary);">文档说明 (Wiki)</div>
                        <div style="font-size: 12px; color: var(--text-secondary);">查看抢票说明书</div>
                    </div>
                </a>
            </div>
        </div>
    </div>
    """
    gr.HTML(html_content)
