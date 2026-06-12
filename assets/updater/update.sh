#!/usr/bin/env sh
set -eu

REPO="mikumifa/biliTickerBuy"
UNAME_S="$(uname -s)"
UNAME_M="$(uname -m)"

case "$UNAME_S:$UNAME_M" in
  Linux:x86_64|Linux:amd64)
    PLATFORM_KEY="linux_amd64"
    BINARY_NAME="biliTickerBuy"
    ;;
  Linux:aarch64|Linux:arm64)
    PLATFORM_KEY="linux_arm64"
    BINARY_NAME="biliTickerBuy"
    ;;
  Darwin:arm64|Darwin:aarch64)
    PLATFORM_KEY="macos_arm64"
    BINARY_NAME="biliTickerBuy"
    ;;
  Darwin:x86_64|Darwin:amd64)
    PLATFORM_KEY="macos_intel"
    BINARY_NAME="biliTickerBuy"
    ;;
  *)
    echo "当前平台暂不支持自动更新：$UNAME_S/$UNAME_M" >&2
    exit 1
    ;;
esac

INSTALL_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
WORK_DIR="$INSTALL_DIR/updates"
TEMP_ZIP="$WORK_DIR/update.zip"
TEMP_EXTRACT="$WORK_DIR/extract"
API_URL="https://api.github.com/repos/$REPO/releases/latest"
ENV_INSTALL_FILE="$INSTALL_DIR/.env.install"

# 环境变量优先级：
# 1. 当前 shell 中的 GH_PROXY
# 2. .env.install 中的 GH_PROXY
# 3. 默认代理
GH_PROXY_FROM_ENV="${GH_PROXY-}"

if [ -f "$ENV_INSTALL_FILE" ]; then
  # shellcheck disable=SC1090
  . "$ENV_INSTALL_FILE"
fi

if [ -n "$GH_PROXY_FROM_ENV" ]; then
  GH_PROXY="$GH_PROXY_FROM_ENV"
else
  GH_PROXY="${GH_PROXY:-https://gh-proxy.org}"
fi

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "缺少必要命令：$1" >&2
    exit 1
  }
}

resolve_url() {
  case "${GH_PROXY:-}" in
    "")
      printf '%s\n' "$1"
      ;;
    */)
      printf '%s%s\n' "$GH_PROXY" "$1"
      ;;
    *)
      printf '%s/%s\n' "$GH_PROXY" "$1"
      ;;
  esac
}

http_get() {
  url="$1"
  output="${2:-}"

  if command -v curl >/dev/null 2>&1; then
    if [ -n "$output" ]; then
      curl \
        --fail \
        --location \
        --progress-bar \
        --header 'User-Agent: biliTickerBuy-updater' \
        --output "$output" \
        "$url"
    else
      curl \
        --fail \
        --location \
        --silent \
        --show-error \
        --header 'User-Agent: biliTickerBuy-updater' \
        "$url"
    fi
  elif command -v wget >/dev/null 2>&1; then
    if [ -n "$output" ]; then
      wget \
        --output-document="$output" \
        --header='User-Agent: biliTickerBuy-updater' \
        "$url"
    else
      wget \
        --quiet \
        --output-document=- \
        --header='User-Agent: biliTickerBuy-updater' \
        "$url"
    fi
  else
    echo "缺少必要命令：curl 或 wget" >&2
    return 1
  fi
}

request_release_json() {
  # GitHub API 优先直连。部分 GitHub 下载代理不支持 api.github.com。
  if release_json="$(http_get "$API_URL" 2>/dev/null)"; then
    printf '%s' "$release_json"
    return 0
  fi

  if [ -z "${GH_PROXY:-}" ]; then
    echo "获取 GitHub Release 信息失败：$API_URL" >&2
    return 1
  fi

  proxy_api_url="$(resolve_url "$API_URL")"
  echo "[biliTickerBuy] GitHub API 直连失败，正在尝试代理..." >&2

  if release_json="$(http_get "$proxy_api_url")"; then
    printf '%s' "$release_json"
    return 0
  fi

  echo "获取 GitHub Release 信息失败。" >&2
  return 1
}

print_network_help() {
  echo "请根据网络情况尝试取消 GH_PROXY，或更换为其他可用加速前缀。" >&2
  echo "可在安装目录的 .env.install 中配置，例如：" >&2
  echo "GH_PROXY=https://gh-proxy.org" >&2
  echo "若要禁用代理，可执行：" >&2
  echo "GH_PROXY= ./update.sh" >&2
  echo "可用前缀可前往 https://ghproxy.link/ 查找。" >&2
}

find_package_binary() {
  # 优先检查压缩包根目录，随后递归查找。
  if [ -f "$TEMP_EXTRACT/$BINARY_NAME" ]; then
    printf '%s\n' "$TEMP_EXTRACT/$BINARY_NAME"
    return 0
  fi

  find "$TEMP_EXTRACT" \
    -type f \
    -name "$BINARY_NAME" \
    -print \
    2>/dev/null |
    head -n 1
}

copy_optional_file() {
  file_name="$1"
  source_file="$PACKAGE_DIR/$file_name"

  if [ -f "$source_file" ]; then
    cp "$source_file" "$INSTALL_DIR/$file_name"
  fi
}

require_cmd unzip

mkdir -p "$WORK_DIR"

# 不复用旧更新包，避免上一次失败留下的 ZIP 被误认为最新版。
rm -f "$TEMP_ZIP"
rm -rf "$TEMP_EXTRACT"
mkdir -p "$TEMP_EXTRACT"

echo "[biliTickerBuy] 正在检查最新版本..."

if ! RELEASE_JSON="$(request_release_json)"; then
  print_network_help
  exit 1
fi

# 将每个 asset 对象拆到单独一行，再匹配当前平台。
ASSET_URL="$(
  printf '%s' "$RELEASE_JSON" |
    tr -d '\n' |
    sed 's/},{/},\
{/g' |
    grep "\"name\":\"[^\"]*_${PLATFORM_KEY}_[^\"]*\"" |
    sed -n 's/.*"browser_download_url":"\([^"]*\)".*/\1/p' |
    head -n 1
)"

RELEASE_TAG="$(
  printf '%s' "$RELEASE_JSON" |
    tr -d '\n' |
    sed -n 's/.*"tag_name":"\([^"]*\)".*/\1/p' |
    head -n 1
)"

if [ -z "$ASSET_URL" ]; then
  echo "最新版本中未找到当前平台 ${PLATFORM_KEY} 对应的更新包。" >&2
  exit 1
fi

if [ -z "$RELEASE_TAG" ]; then
  echo "解析最新版本号失败。" >&2
  exit 1
fi

DOWNLOAD_URL="$(resolve_url "$ASSET_URL")"

echo "[biliTickerBuy] 正在下载 ${RELEASE_TAG}..."

if ! http_get "$DOWNLOAD_URL" "$TEMP_ZIP"; then
  echo "下载失败：$DOWNLOAD_URL" >&2
  print_network_help
  exit 1
fi

if [ ! -s "$TEMP_ZIP" ]; then
  echo "下载到的更新包为空：$TEMP_ZIP" >&2
  exit 1
fi

echo "[biliTickerBuy] 正在解压更新包..."

if ! unzip -oq "$TEMP_ZIP" -d "$TEMP_EXTRACT"; then
  echo "更新包解压失败：$TEMP_ZIP" >&2
  echo "临时文件已保留在：$WORK_DIR" >&2
  exit 1
fi

PACKAGE_BINARY="$(find_package_binary)"

if [ -z "$PACKAGE_BINARY" ] || [ ! -f "$PACKAGE_BINARY" ]; then
  echo "解压后的更新包中缺少 $BINARY_NAME 可执行文件。" >&2
  echo "更新包内容如下：" >&2
  find "$TEMP_EXTRACT" -maxdepth 4 -print >&2
  echo "临时文件已保留在：$WORK_DIR" >&2
  exit 1
fi

PACKAGE_DIR="$(dirname "$PACKAGE_BINARY")"

echo "[biliTickerBuy] 找到程序文件：$PACKAGE_BINARY"
echo "[biliTickerBuy] 正在替换本地文件..."

# 先复制到临时路径，再通过 mv 替换，尽量避免产生半写入文件。
NEW_BINARY="$INSTALL_DIR/.${BINARY_NAME}.new"

rm -f "$NEW_BINARY"

if ! cp "$PACKAGE_BINARY" "$NEW_BINARY"; then
  echo "复制新版本程序失败。" >&2
  echo "临时文件已保留在：$WORK_DIR" >&2
  exit 1
fi

chmod +x "$NEW_BINARY"

if ! mv -f "$NEW_BINARY" "$INSTALL_DIR/$BINARY_NAME"; then
  rm -f "$NEW_BINARY"
  echo "替换文件失败。" >&2
  echo "请先关闭正在运行的 biliTickerBuy，然后重新执行 update.sh。" >&2
  echo "临时文件已保留在：$WORK_DIR" >&2
  exit 1
fi

# 更新包内的附加文件应与主程序位于同一目录。
#
# 使用临时文件更新 update.sh，避免直接覆盖当前正在执行的脚本。
if [ -f "$PACKAGE_DIR/update.sh" ]; then
  UPDATE_SCRIPT_NEW="$INSTALL_DIR/.update.sh.new"

  if cp "$PACKAGE_DIR/update.sh" "$UPDATE_SCRIPT_NEW"; then
    chmod +x "$UPDATE_SCRIPT_NEW"

    if ! mv -f "$UPDATE_SCRIPT_NEW" "$INSTALL_DIR/update.sh"; then
      rm -f "$UPDATE_SCRIPT_NEW"
      echo "警告：update.sh 更新失败，但主程序已成功更新。" >&2
    fi
  else
    echo "警告：无法复制新版 update.sh，但主程序已成功更新。" >&2
  fi
fi

# 不覆盖用户已经配置好的 .env.install。
if [ ! -f "$ENV_INSTALL_FILE" ] && [ -f "$PACKAGE_DIR/.env.install" ]; then
  if ! cp "$PACKAGE_DIR/.env.install" "$ENV_INSTALL_FILE"; then
    echo "警告：无法安装默认 .env.install。" >&2
  fi
fi

# 可按需要复制与主程序同目录的其他运行文件。
# 当前只明确更新主程序和更新脚本，避免误覆盖用户数据与配置。

rm -f "$TEMP_ZIP"
rm -rf "$TEMP_EXTRACT"

echo "[biliTickerBuy] 已更新到 ${RELEASE_TAG}。"
echo "请手动重新启动程序。"