<div align="center">
  <a href="https://github.com/mikumifa/biliTickerBuy" target="_blank">
    <img width="160" src="assets/icon.ico" alt="logo">
  </a>
  <h2 id="koishi">biliTickerBuy</h1>

<p>
  <!-- GitHub Downloads -->
  <a href="https://github.com/mikumifa/biliTickerBuy/releases">
    <img src="https://img.shields.io/github/downloads/mikumifa/biliTickerBuy/total" alt="GitHub all releases">
  </a>
  <!-- GitHub Release Version -->
  <a href="https://github.com/mikumifa/biliTickerBuy/releases">
    <img src="https://img.shields.io/github/v/release/mikumifa/biliTickerBuy" alt="GitHub release (with filter)">
  </a>
  <!-- GitHub Issues -->
  <a href="https://github.com/mikumifa/biliTickerBuy/issues">
    <img src="https://img.shields.io/github/issues/mikumifa/biliTickerBuy" alt="GitHub issues">
  </a>
  <!-- GitHub Stars -->
  <a href="https://github.com/mikumifa/biliTickerBuy/stargazers">
    <img src="https://img.shields.io/github/stars/mikumifa/biliTickerBuy" alt="GitHub Repo stars">
  </a>
</p>
<a href="https://trendshift.io/repositories/11145" target="_blank"><img src="https://trendshift.io/api/badge/repositories/11145" alt="mikumifa%2FbiliTickerBuy | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

这是一个开源免费，简单易用的 B 站会员购辅助工具

</div>

## 💻 快速安装

方法一: 从 github 上[下载](https://github.com/mikumifa/biliTickerBuy/releases)

方法二: 如果没有您使用系统的已构建版本，请前往[指南](https://github.com/mikumifa/biliTickerBuy/wiki/Docker%E8%BF%90%E8%A1%8C%E6%96%B9%E6%B3%95)

方法三: 仓库支持通过 `pip install bilitickerbuy` 安装，安装后可以直接使用 `btb` 命令运行。示例：

```bash
# 直接启动ui
btb
# 根据配置文件购票
btb buy ./your_config.json
```

## 👀 使用说明书

前往飞书： https://n1x87b5cqay.feishu.cn/wiki/Eg4xwt3Dbiah02k1WqOcVk2YnMd

## ❗ 项目问题

程序使用问题： [点此链接前往 discussions](https://github.com/mikumifa/biliTickerBuy/discussions)

反馈程序 BUG 或者提新功能建议： [点此链接向项目提出反馈 BUG](https://github.com/mikumifa/biliTickerBuy/issues/new/choose)

## 📩 免责声明

本项目遵循 MIT License 许可协议，仅供个人学习与研究使用。请勿将本项目用于任何商业牟利行为，亦严禁用于任何形式的代抢、违法行为或违反相关平台规则的用途。由此产生的一切后果均由使用者自行承担，与本人无关。

若您 fork 或使用本项目，请务必遵守相关法律法规与目标平台规则。

## 💡 关于访问频率与并发控制

本项目在设计时严格遵循「非侵入式」原则，避免对目标服务器（如 Bilibili）造成任何干扰。

所有网络请求的时间间隔均由用户自行配置，默认值模拟正常用户的手动操作速度。程序默认单线程运行，无并发任务。遇到请求失败时，程序会进行有限次数的重试，并在重试之间加入适当的延时，避免形成高频打点。项目完全依赖平台公开接口及网页结构，不含风控规避、API 劫持等破坏性手段。

## 🛡️ 平台尊重声明

本程序设计时已尽可能控制请求频率，避免对 Bilibili 服务器造成任何明显负载或影响。项目仅作为学习用途，不具备大规模、高并发的能力，亦无任何恶意行为或干扰服务的企图。

如本项目中存在侵犯 Bilibili 公司合法权益的内容，请通过邮箱 [1055069518@qq.com](mailto:1055069518@qq.com) 与我联系，我将第一时间下架相关内容并删除本仓库。对此造成的不便，我深表歉意，感谢您的理解与包容。

## 🤩 项目贡献者

<a href="https://github.com/mikumifa/biliTickerBuy/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=mikumifa/biliTickerBuy&preview=true&max=&columns=" />
</a>
<br /><br />

## ⭐️ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=mikumifa/biliTickerBuy&type=Date)](https://www.star-history.com/#mikumifa/biliTickerBuy&Date)
