# Docker 部署指南

本文说明如何使用 GitHub Container Registry 中已经构建好的镜像部署 `biliTickerBuy`。

当前镜像仓库地址：

- GitHub Packages: `https://github.com/mikumifa/biliTickerBuy/pkgs/container/bilitickerbuy`
- GHCR 镜像名：`ghcr.io/mikumifa/bilitickerbuy`

## 前置要求

- 已安装 Docker Engine 或 Docker Desktop
- 如果使用 `docker compose`，需要安装 Docker Compose

## 方式一：使用 docker run

### 最小启动

直接运行：

```bash
docker run -d \
  --name bilitickerbuy \
  -p 7860:7860 \
  -e BTB_SERVER_NAME=0.0.0.0 \
  -e GRADIO_SERVER_PORT=7860 \
  ghcr.io/mikumifa/bilitickerbuy:latest
```

启动后访问：

```text
http://服务器IP:7860
```

### 带持久化挂载启动

长期使用建议挂载配置、Cookies、日志和运行目录：

```bash
docker run -d \
  --name bilitickerbuy \
  -p 7860:7860 \
  -e BTB_SERVER_NAME=0.0.0.0 \
  -e GRADIO_SERVER_PORT=7860 \
  -e GRADIO_NUM_PORTS=100 \
  -e BTB_CONFIG_PATH=/app/data/config.json \
  -e BTB_COOKIES_PATH=/app/data/cookies.json \
  -e BTB_LOG_DIR=/app/data/btb_logs \
  -v $(pwd)/data:/app/data \
  ghcr.io/mikumifa/bilitickerbuy:latest
```

Windows PowerShell 示例：

```powershell
docker run -d `
  --name bilitickerbuy `
  -p 7860:7860 `
  -e BTB_SERVER_NAME=0.0.0.0 `
  -e GRADIO_SERVER_PORT=7860 `
  -e GRADIO_NUM_PORTS=100 `
  -e BTB_CONFIG_PATH=/app/data/config.json `
  -e BTB_COOKIES_PATH=/app/data/cookies.json `
  -e BTB_LOG_DIR=/app/data/btb_logs `
  -v ${PWD}/data:/app/data `
  ghcr.io/mikumifa/bilitickerbuy:latest
```

查看日志：

```bash
docker logs -f bilitickerbuy
```

停止并删除容器：

```bash
docker rm -f bilitickerbuy
```

## 方式二：使用 docker compose

如果你希望长期运行并持久化配置，建议使用 `docker compose`。

示例 `compose.yaml`：

```yaml
services:
  bilitickerbuy:
    image: ghcr.io/mikumifa/bilitickerbuy:latest
    container_name: bilitickerbuy
    restart: unless-stopped
    ports:
      - "7860:7860"
    environment:
      BTB_SERVER_NAME: 0.0.0.0
      GRADIO_SERVER_PORT: 7860
      GRADIO_NUM_PORTS: 100
      BTB_CONFIG_PATH: /app/data/config.json
      BTB_COOKIES_PATH: /app/data/cookies.json
      BTB_LOG_DIR: /app/data/btb_logs
    volumes:
      - ./data:/app/data
```

启动：

```bash
docker compose up -d
```

查看日志：

```bash
docker compose logs -f
```

停止：

```bash
docker compose down
```

## 常用环境变量

可按需在 `docker run` 或 `docker compose` 中设置以下变量：

| 环境变量             | 说明                     | 默认值                                                     |
| -------------------- | ------------------------ | ---------------------------------------------------------- |
| `BTB_SERVER_NAME`    | Web 服务监听地址         | `0.0.0.0`                                                  |
| `GRADIO_SERVER_PORT` | Web 服务端口             | `7860`                                                     |
| `GRADIO_NUM_PORTS`   | Gradio 可用端口池大小    | `100`                                                      |
| `BTB_CONFIG_PATH`    | 配置文件路径             | 默认 `/app/config.json`，Docker 推荐 `/app/data/config.json`   |
| `BTB_COOKIES_PATH`   | Cookies 文件路径         | 默认 `/app/cookies.json`，Docker 推荐 `/app/data/cookies.json` |
| `BTB_LOG_DIR`        | 日志目录                 | 默认 `/app/btb_logs`，Docker 推荐 `/app/data/btb_logs`         |
| `BTB_SHARE`          | 是否启用 Gradio 公网分享 | `false`                                                    |
| `BTB_PUSHPLUSTOKEN`  | PushPlus 通知 token      | 空                                                         |
| `BTB_BARKTOKEN`      | Bark 通知 token          | 空                                                         |
| `BTB_NTFY_URL`       | ntfy 推送地址            | 空                                                         |
| `BTB_NTP_SERVERS`     | NTP 服务器列表            | 空，为空时默认依次使用 `ntp.aliyun.com,ntp.tencent.com,cn.ntp.org.cn,time.cloudflare.com` |

## 更新镜像

如果要更新到最新镜像：

```bash
docker pull ghcr.io/mikumifa/bilitickerbuy:latest
docker rm -f bilitickerbuy
docker run -d \
  --name bilitickerbuy \
  -p 7860:7860 \
  -e BTB_SERVER_NAME=0.0.0.0 \
  -e GRADIO_SERVER_PORT=7860 \
  -e GRADIO_NUM_PORTS=100 \
  -e BTB_CONFIG_PATH=/app/data/config.json \
  -e BTB_COOKIES_PATH=/app/data/cookies.json \
  -e BTB_LOG_DIR=/app/data/btb_logs \
  -v $(pwd)/data:/app/data \
  ghcr.io/mikumifa/bilitickerbuy:latest
```

如果你使用固定版本，把 `latest` 替换成目标版本标签即可，例如：

```bash
ghcr.io/mikumifa/bilitickerbuy:v2.15.8
```

如果使用的是 `docker compose`，修改镜像标签后执行：

```bash
docker compose pull
docker compose up -d
```

## 常见问题

### 无法访问页面

优先检查：

- 容器是否正常运行：`docker ps`
- 日志中是否有报错：`docker logs -f bilitickerbuy`
- 宿主机防火墙是否放行了 `7860`
- 云服务器安全组是否放行了 `7860`

### 配置和登录状态丢失

如果没有挂载 `config.json`、`cookies.json`、`btb_logs`、`btb_runs`，删除容器后这些内容会一起丢失。长期部署时建议使用 `docker compose`，或者至少在 `docker run` 中加上数据卷挂载。

### 报错 `IsADirectoryError: /app/config.json`

这通常说明你把一个目录挂载到了本应是文件的配置路径上。

修复方式：

1. 删除错误创建的目录
2. 重新创建 `config.json` 和 `cookies.json` 空文件
3. 改用整目录挂载 `./data:/app/data`
4. 把 `BTB_CONFIG_PATH` 设置为 `/app/data/config.json`
5. 把 `BTB_COOKIES_PATH` 设置为 `/app/data/cookies.json`

### 报错 `gradio.exceptions.InvalidPathError`

这通常说明你把持久化文件放在了 `/data` 这种不在 Gradio 默认允许范围内的目录。

最直接的修复是把数据目录挂到 `/app/data`，因为 `/app` 就是应用当前工作目录：

```bash
-e BTB_CONFIG_PATH=/app/data/config.json \
-e BTB_COOKIES_PATH=/app/data/cookies.json \
-e BTB_LOG_DIR=/app/data/btb_logs \
-v $(pwd)/data:/app/data \
```

### 想使用其他标签

可在 GitHub Packages 页面查看当前可用标签：

`https://github.com/mikumifa/biliTickerBuy/pkgs/container/bilitickerbuy`
