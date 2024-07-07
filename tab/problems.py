import gradio as gr

def problems_tab():
    gr.Markdown("""

此处仅列举常见问题。如此处无法解决您的问题，请您参阅本项目的 [Wiki](https://github.com/mikumifa/biliTickerBuy/wiki), [Discussions](https://github.com/mikumifa/biliTickerBuy/discussions)和[Issues](https://github.com/mikumifa/biliTickerBuy/issues).

## QA 合集：
1. Q: 我能用手机运行这个项目吗？  
A: 您可以尝试使用Termux在Android手机中使用Doker来运行本项目，使用Doker部署本项目的方式请参照项目Wiki。
                
2. Q: 抢票时提示“配置文件格式错误: Expecting value...” 是什么问题？  
A: 请检查您是否上传了正确的配置文件。您应该先在`配置`选项卡中填入您要购买的票的链接，生成对应的配置文件，将该配置文件下载到本地或复制到剪贴板。随后在抢票选项卡中上传配置文件或粘贴配置文件到`填入配置`文本框中。

3. Q: 为什么我的抢票页面无法访问了/或访问时页面提示错误？  
A: 请您在脚本启动后**千万不要**关闭后台的黑框框(CMD/PowerShell窗口)。
                
4. Q: 为什么我无法获取cookie/无法登录？  
A: 有可能是您的设备需要进行新设备验证。请单独打开一个浏览器窗口并进入 [BiliBili](https://www.bilibili.com) 登录账号，进行新设备验证。随后再从脚本中进行登录来获取 cookie。
                
5. Q: 如何多开？  
A: 复制一份程序**所在文件夹内所有文件**到不同的**文件目录**，再打开相应程序。
                
6. Q: 我的电脑的时间偏差很大，我需要担心抢不到票吗？  
A: 您不需要担心这个问题，脚本会自动补偿您的时间偏差，确保您可以准时开始抢票。如果您不了解时间偏差的作用，建议不要手动修改其值。
                
7. Q: 验证码预填功能是每次抢票都可以使用吗？  
A: 并不是每次都可以使用。只有在您要抢票的票仓中有**已经开票的票种**时才可以使用。如果您在验证码预填选项中上传了还未开票的票种的配置文件，可能会触发B站的风险控制，导致无法抢票。

## 使用注意事项：
1. 由于脚本的配置文件内容没有加密，在您向他人发送配置文件的照片时请注意打码个人隐私信息；
2. 从非官方Release渠道获取的脚本有被篡改的可能，请谨慎使用；
3. 请不要在公共平台(B站，小红书，抖音等)宣传本项目

## 遇到无法解决的问题怎么办
请先在本项目的 [Wiki](https://github.com/mikumifa/biliTickerBuy/wiki), [Discussions](https://github.com/mikumifa/biliTickerBuy/discussions)和[Issues](https://github.com/mikumifa/biliTickerBuy/issues)
中进行搜索，查找是否有他人已经提出过您遇到的问题并获得了相应的解决方案。
                

如果确实没有找到相似的问题，请带上您的**打码了敏感信息**的日志(app.log)/截图，附上详细的问题及遇到问题时的操作，在项目[Discussions](https://github.com/mikumifa/biliTickerBuy/discussions)中进行提问。

         
> [Tip]  
> 如果您是买来这个程序的话，您肯定是上当受骗了，建议您尽快联系卖家进行退款！
>
> 本项目已开启[爱发电](https://afdian.net/a/mikumifa)，如果你想支持本项目可以进行赞助。

本项目免责声明详见项目地址的 readme.md.
""")