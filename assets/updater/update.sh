#!/usr/bin/env sh
set -eu

REPO="mikumifa/biliTickerBuy"
UNAME_S="$(uname -s)"
UNAME_M="$(uname -m)"

case "$UNAME_S:$UNAME_M" in
  Linux:x86_64|Linux:amd64) PLATFORM_KEY="linux_amd64" ;;
  Linux:aarch64|Linux:arm64) PLATFORM_KEY="linux_arm64" ;;
  Darwin:arm64|Darwin:aarch64) PLATFORM_KEY="macos_arm64" ;;
  Darwin:x86_64|Darwin:amd64) PLATFORM_KEY="macos_intel" ;;
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

[ -f "$ENV_INSTALL_FILE" ] && . "$ENV_INSTALL_FILE"
GH_PROXY="${GH_PROXY:-https://gh-proxy.org}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "缺少必要命令：$1" >&2
    exit 1
  }
}

resolve_url() {
  case "${GH_PROXY}" in
    "")
      printf '%s\n' "$1"
      ;;
    */)
      printf '%s%s\n' "${GH_PROXY}" "$1"
      ;;
    *)
      printf '%s/%s\n' "${GH_PROXY}" "$1"
      ;;
  esac
}

http_get() {
  url="$1"
  output="${2:-}"
  if command -v curl >/dev/null 2>&1; then
    if [ -n "$output" ]; then
      if ! curl --fail --location --progress-bar -H 'User-Agent: biliTickerBuy-updater' -o "$output" "$url"; then
        echo "下载失败：$url" >&2
        echo "请根据网络情况尝试取消 GH_PROXY，或更换为其他可用加速前缀。" >&2
        echo "可在安装目录的 .env.install 中配置，例如：GH_PROXY=https://gh-proxy.org" >&2
        echo "可用前缀可前往 https://ghproxy.link/ 查找。" >&2
        exit 1
      fi
    else
      if ! curl --fail --location --silent --show-error -H 'User-Agent: biliTickerBuy-updater' "$url"; then
        echo "请求失败：$url" >&2
        echo "请根据网络情况尝试取消 GH_PROXY，或更换为其他可用加速前缀。" >&2
        echo "可在安装目录的 .env.install 中配置，例如：GH_PROXY=https://gh-proxy.org" >&2
        echo "可用前缀可前往 https://ghproxy.link/ 查找。" >&2
        exit 1
      fi
    fi
  elif command -v wget >/dev/null 2>&1; then
    if [ -n "$output" ]; then
      if ! wget -O "$output" --header='User-Agent: biliTickerBuy-updater' "$url"; then
        echo "下载失败：$url" >&2
        echo "请根据网络情况尝试取消 GH_PROXY，或更换为其他可用加速前缀。" >&2
        echo "可在安装目录的 .env.install 中配置，例如：GH_PROXY=https://gh-proxy.org" >&2
        echo "可用前缀可前往 https://ghproxy.link/ 查找。" >&2
        exit 1
      fi
    else
      if ! wget -qO- --header='User-Agent: biliTickerBuy-updater' "$url"; then
        echo "请求失败：$url" >&2
        echo "请根据网络情况尝试取消 GH_PROXY，或更换为其他可用加速前缀。" >&2
        echo "可在安装目录的 .env.install 中配置，例如：GH_PROXY=https://gh-proxy.org" >&2
        echo "可用前缀可前往 https://ghproxy.link/ 查找。" >&2
        exit 1
      fi
    fi
  else
    echo "缺少必要命令：curl 或 wget" >&2
    exit 1
  fi
}

require_cmd unzip
mkdir -p "$WORK_DIR"
rm -rf "$TEMP_EXTRACT"
mkdir -p "$TEMP_EXTRACT"

RELEASE_JSON="$(http_get "$(resolve_url "$API_URL")")"
ASSET_URL="$(printf '%s' "$RELEASE_JSON" | tr -d '\n' | sed 's/},{/},\
{/g' | grep "\"name\":\"[^\"]*_${PLATFORM_KEY}_[^\"]*\"" | sed -n 's/.*"browser_download_url":"\([^"]*\)".*/\1/p' | head -n 1)"
RELEASE_TAG="$(printf '%s' "$RELEASE_JSON" | sed -n 's/.*"tag_name":"\([^"]*\)".*/\1/p' | head -n 1)"

[ -n "$ASSET_URL" ] || {
  echo "最新版本中未找到当前平台 ${PLATFORM_KEY} 对应的更新包" >&2
  exit 1
}

[ -n "$RELEASE_TAG" ] || {
  echo "解析最新版本号失败" >&2
  exit 1
}

if [ -f "$TEMP_ZIP" ]; then
  echo "[biliTickerBuy] 检测到已下载的更新包，跳过下载：$TEMP_ZIP"
else
  echo "[biliTickerBuy] 正在下载 ${RELEASE_TAG}..."
  http_get "$(resolve_url "$ASSET_URL")" "$TEMP_ZIP"
fi

echo "[biliTickerBuy] 正在解压更新包..."
unzip -oq "$TEMP_ZIP" -d "$TEMP_EXTRACT"

if [ -d "$TEMP_EXTRACT/biliTickerBuy" ]; then
  if ! cp -R "$TEMP_EXTRACT/biliTickerBuy/." "$INSTALL_DIR/"; then
    echo "替换文件失败，请先关闭正在运行的 biliTickerBuy，然后重新执行 update.sh。" >&2
    exit 1
  fi
elif [ -f "$TEMP_EXTRACT/biliTickerBuy.exe" ]; then
  if ! cp "$TEMP_EXTRACT/biliTickerBuy.exe" "$INSTALL_DIR/"; then
    echo "替换文件失败，请先关闭正在运行的 biliTickerBuy，然后重新执行 update.sh。" >&2
    exit 1
  fi
else
  echo "解压后的更新包中缺少预期文件。" >&2
  exit 1
fi

if [ -f "$TEMP_EXTRACT/update.sh" ]; then
  cp "$TEMP_EXTRACT/update.sh" "$INSTALL_DIR/"
  chmod +x "$INSTALL_DIR/update.sh"
fi
if [ -f "$TEMP_EXTRACT/.env.install" ]; then
  cp "$TEMP_EXTRACT/.env.install" "$INSTALL_DIR/"
fi
rm -f "$TEMP_ZIP"
rm -rf "$TEMP_EXTRACT"

echo "[biliTickerBuy] 更新完成。"
echo "请手动重新启动程序。"
