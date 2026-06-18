# 安装指南

## 系统要求

| 平台    | 支持情况 | 说明                                        |
| ------- | -------- | ------------------------------------------- |
| Windows | 支持     | 推荐 Windows 10 或更高版本                  |
| Linux   | 支持     | 预构建版本要求 Ubuntu 22.04 或更高版本      |
| macOS   | 支持     | 支持 Intel 和 Apple Silicon                 |
| Docker  | 支持     | 适用于其他 Linux 发行版或无预构建版本的平台 |
| Python  | 支持     | 推荐 Python 3.11                            |

---

## 方法一：下载预构建版本

前往 [GitHub Releases](https://github.com/mikumifa/biliTickerBuy/releases)，下载与当前系统及处理器架构对应的安装包。

常见平台对应关系如下：

| 系统    | 处理器架构      | 安装包标识      |
| ------- | --------------- | --------------- |
| Windows | x86_64 / AMD64  | `windows_amd64` |
| Linux   | x86_64 / AMD64  | `linux_amd64`   |
| Linux   | ARM64 / AArch64 | `linux_arm64`   |
| macOS   | Apple Silicon   | `macos_arm64`   |
| macOS   | Intel           | `macos_intel`   |

下载完成后，解压安装包并运行其中的程序：

- Windows：`biliTickerBuy.exe`
- Linux / macOS：`biliTickerBuy`

如果安装包中包含更新脚本，也可以使用其中的脚本更新程序。

---

## 方法二：Linux / macOS 命令行安装

> Linux 预构建版本要求 Ubuntu 22.04 或更高版本。其他 Linux 发行版建议使用 Docker 或 PyPI 安装。

安装脚本会自动识别当前系统和处理器架构、下载最新版本，并创建 `btb` 启动命令。

执行以下命令：

```bash
curl -fsSL https://raw.githubusercontent.com/mikumifa/biliTickerBuy/main/install.sh | sh
```

安装完成后运行：

```bash
btb
```

如果是在服务器上运行，为了让其他设备能够访问 Web 界面，`server_name` 应配置为服务器对外访问的 IP，例如：

```bash
btb --server_name 服务器对外访问的IP
```

---

## GitHub 下载代理

Linux / macOS 安装脚本默认使用以下加速前缀下载 GitHub Release 文件：

```text
https://gh-proxy.org/
```

如果默认代理失效，可以前往 [ghproxy.link](https://ghproxy.link/) 查找其他可用前缀。

安装脚本会在代理下载失败后尝试直连 GitHub。

---

## 自定义 Linux / macOS 安装参数

安装脚本支持通过环境变量自定义 GitHub 下载代理、程序安装目录和命令目录。

| 环境变量      | 说明                                    |
| ------------- | --------------------------------------- |
| `GH_PROXY`    | GitHub 下载加速前缀，设置为空可禁用代理 |
| `INSTALL_DIR` | 程序安装目录                            |
| `BIN_DIR`     | `btb` 启动命令所在目录                  |

通过管道执行安装脚本时，需要将环境变量传递给 `sh`。

### 自定义代理

```bash
curl -fsSL https://raw.githubusercontent.com/mikumifa/biliTickerBuy/main/install.sh |
  GH_PROXY="https://其他代理前缀" sh
```

### 禁用代理并直连 GitHub

```bash
curl -fsSL https://raw.githubusercontent.com/mikumifa/biliTickerBuy/main/install.sh |
  GH_PROXY="" sh
```

### 自定义安装目录

```bash
curl -fsSL https://raw.githubusercontent.com/mikumifa/biliTickerBuy/main/install.sh |
  INSTALL_DIR="$HOME/apps/biliTickerBuy" \
  BIN_DIR="$HOME/.local/bin" \
  sh
```

### 同时自定义代理和安装目录

```bash
curl -fsSL https://raw.githubusercontent.com/mikumifa/biliTickerBuy/main/install.sh |
  GH_PROXY="https://其他代理前缀" \
  INSTALL_DIR="$HOME/apps/biliTickerBuy" \
  BIN_DIR="$HOME/.local/bin" \
  sh
```

---

## 方法三：使用 Docker

如果 GitHub Releases 中没有适用于当前系统的预构建版本，或者当前 Linux 发行版不满足预构建版本要求，可以使用 Docker 运行。

具体步骤请参考：

[Docker 部署指南](./docker-deployment.md)

使用 Docker 前，请先确认已经安装：

- Docker Engine 或 Docker Desktop
- Docker Compose

Docker 方式不会依赖宿主机中的 Python 环境，适合服务器部署或环境隔离。

---

## 方法四：使用 PyPI 安装

项目支持通过 PyPI 安装，推荐使用 Python 3.11。

确认 Python 版本：

```bash
python --version
```

安装 biliTickerBuy：

```bash
python -m pip install --upgrade bilitickerbuy
```

安装完成后运行：

```bash
btb
```

如果系统中存在多个 Python 版本，也可以明确指定 Python 3：

```bash
python3 -m pip install --upgrade bilitickerbuy
```

---

## 更新程序

### Windows 预构建版本

进入程序所在目录，运行安装包中的更新脚本：

```bat
update.bat
```

也可以前往 [GitHub Releases](https://github.com/mikumifa/biliTickerBuy/releases) 手动下载并替换为最新版本。

### Linux / macOS 命令行安装版本

再次运行安装脚本即可下载并安装最新版本：

```bash
curl -fsSL https://raw.githubusercontent.com/mikumifa/biliTickerBuy/main/install.sh | sh
```

如果安装目录中包含更新脚本，也可以运行：

```bash
./update.sh
```

### PyPI 安装版本

```bash
python -m pip install --upgrade bilitickerbuy
```

---

## 常见问题

### 下载失败

Linux / macOS 安装脚本会在代理下载失败后尝试直连 GitHub。

如果仍然失败，可以：

1. 检查当前网络是否能够访问 GitHub。
2. 更换 `GH_PROXY` 加速前缀。
3. 设置 `GH_PROXY=""` 禁用代理并尝试直连。
4. 前往 [GitHub Releases](https://github.com/mikumifa/biliTickerBuy/releases) 手动下载安装包。

禁用代理：

```bash
curl -fsSL https://raw.githubusercontent.com/mikumifa/biliTickerBuy/main/install.sh |
  GH_PROXY="" sh
```

### Linux 提示权限不足

安装脚本默认安装到用户目录，不需要使用 `sudo`。

如果手动下载了可执行文件，可以添加执行权限：

```bash
chmod +x biliTickerBuy
```

### Windows 阻止程序运行

如果 Windows Defender 或 SmartScreen 弹出安全提示，请先确认程序来自本项目的官方 GitHub 仓库。

项目官方下载地址：

[GitHub Releases](https://github.com/mikumifa/biliTickerBuy/releases)

确认文件来源可信后，再根据系统提示选择是否继续运行。

### Linux / macOS 安装后找不到 `btb`

安装脚本默认会将命令目录添加到用户的 `PATH`。

更新后的 `PATH` 通常不会立即应用到已经打开的终端。请关闭并重新打开终端，然后执行：

```bash
btb
```

也可以根据安装完成时显示的提示，使用完整路径运行程序。

### PyPI 安装后找不到命令

这通常是 Python 的脚本目录没有加入 `PATH`。

可以通过以下命令查看用户安装目录：

```bash
python -m site --user-base
```

也可以直接通过 Python 模块方式尝试启动：

```bash
python -m biliTickerBuy
```
