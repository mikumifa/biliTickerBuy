# 自建代理指南

本文介绍如何在 Ubuntu / Debian 服务器上使用 Squid 搭建一个最基础的 HTTP 代理，供 `biliTickerBuy` 在出现风控时切换使用。

## 适用场景

- 你已经有一台可以公网访问的 Linux 服务器
- 你希望自己控制代理，而不是依赖公开代理
- 你只需要最基础的用户名密码认证 HTTP 代理

## 使用前说明

- 本文示例使用 Squid 端口 `8080`
- 文中的 `proxyuser`、`proxypass`、`服务器公网IP` 都需要替换成你自己的值
- 程序中填写代理时，格式应为：

```text
http://proxyuser:proxypass@服务器公网IP:8080
```

例如：

```text
http://alice:myStrongPass@203.0.113.10:8080
```

## 一键搭建命令

按顺序执行下面这些命令即可：

```bash
# 1. 安装 Squid 和 htpasswd 工具
sudo apt update
sudo apt install -y squid apache2-utils

# 2. 创建代理账号密码
sudo htpasswd -bc /etc/squid/passwd proxyuser proxypass

# 3. 备份原始 Squid 配置
sudo cp /etc/squid/squid.conf /etc/squid/squid.conf.bak

# 4. 写入新的 Squid 配置
sudo tee /etc/squid/squid.conf > /dev/null <<'EOF'
http_port 8080
auth_param basic program /usr/lib/squid/basic_ncsa_auth /etc/squid/passwd
auth_param basic realm Squid Proxy
acl authenticated proxy_auth REQUIRED
http_access allow authenticated
http_access deny all
EOF

# 5. 检查配置是否正确
sudo squid -k parse

# 6. 重启 Squid
sudo systemctl restart squid

# 7. 设置开机自启
sudo systemctl enable squid

# 8. 查看 Squid 状态
sudo systemctl status squid
```

## 放行防火墙端口

如果你的服务器开启了防火墙，还需要放行 `8080` 端口。

如果你使用的是 `ufw`：

```bash
sudo ufw allow 8080/tcp
sudo ufw reload
```

如果你使用的是云厂商安全组，也要记得在控制台放行 TCP `8080`。

## 验证代理是否可用

你可以在本地电脑上用 `curl` 测试：

```bash
curl -x http://proxyuser:proxypass@服务器公网IP:8080 https://api.bilibili.com/x/web-interface/nav
```

如果能返回 JSON，说明代理基本可用。

也可以直接填到 `biliTickerBuy` 的“代理设置”里，再点击“测试代理连通性”。

## 在 biliTickerBuy 中怎么填写

推荐每行填写一个代理。例如：

```text
http://proxyuser:proxypass@服务器公网IP:8080
http://备用用户名:备用密码@备用服务器IP:8080
```

如果你只有一个代理，填一行即可。

抢票流程会在检测到风控时按顺序切换到下一个代理；当前这一次请求不会在请求层立刻自动重试，下一次抢票重试才会使用新代理。若某个代理在短时间内连续失败，程序会暂时将它冷却；当所有代理都不可用时，程序会递增休息后继续尝试。留空则只使用直连。

## 常见问题

### 1. `squid -k parse` 报错

先检查以下几项：

- `/etc/squid/passwd` 是否创建成功
- `basic_ncsa_auth` 路径是否存在
- `squid.conf` 是否完整复制，没有少行

你也可以执行：

```bash
ls /usr/lib/squid/basic_ncsa_auth
cat /etc/squid/squid.conf
```

### 2. 本地无法连接代理

优先检查：

- 服务器公网 IP 是否正确
- 8080 端口是否放行
- Squid 服务是否正在运行

可执行：

```bash
sudo systemctl status squid
sudo ss -ltnp | grep 8080
```

### 3. 代理能连上，但程序测试失败

常见原因：

- 代理账号密码写错
- 服务器网络本身访问 B 站不稳定
- 代理被本地网络或运营商限制

建议先用 `curl` 单独测试，再填回程序。

## 安全建议

- 不要使用示例中的弱密码
- 不要把代理端口长期完全暴露给所有人
- 如果条件允许，建议配合安全组，仅允许你自己的出口 IP 访问
- 如果代理只给自己使用，尽量定期更换密码

## 恢复默认配置

如果你想撤销本文配置并恢复 Squid 原始配置：

```bash
sudo cp /etc/squid/squid.conf.bak /etc/squid/squid.conf
sudo systemctl restart squid
```
