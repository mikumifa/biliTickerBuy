```sh
#!/usr/bin/env sh
set -eu

REPO="mikumifa/biliTickerBuy"
UNAME_S="$(uname -s)"
UNAME_M="$(uname -m)"

# 未设置 GH_PROXY 时使用默认代理。
# 显式设置 GH_PROXY="" 时禁用代理：
# GH_PROXY="" sh install.sh
GH_PROXY="${GH_PROXY-https://gh-proxy.org}"

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/biliTickerBuy}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
LAUNCHER_PATH="$BIN_DIR/btb"
API_URL="https://api.github.com/repos/$REPO/releases/latest"

PATH_MARKER_BEGIN="# >>> biliTickerBuy PATH >>>"
PATH_MARKER_END="# <<< biliTickerBuy PATH <<<"

case "$UNAME_S:$UNAME_M" in
  Linux:x86_64|Linux:amd64)
    PLATFORM_KEY="linux_amd64"
    ;;
  Linux:aarch64|Linux:arm64)
    PLATFORM_KEY="linux_arm64"
    ;;
  Darwin:arm64|Darwin:aarch64)
    PLATFORM_KEY="macos_arm64"
    ;;
  Darwin:x86_64|Darwin:amd64)
    PLATFORM_KEY="macos_intel"
    ;;
  *)
    echo "当前平台暂不支持该安装脚本：$UNAME_S/$UNAME_M" >&2
    exit 1
    ;;
esac

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "缺少必要命令：$1" >&2
    exit 1
  }
}

resolve_url() {
  original_url="$1"

  case "${GH_PROXY:-}" in
    "")
      printf '%s\n' "$original_url"
      ;;
    */)
      printf '%s%s\n' "$GH_PROXY" "$original_url"
      ;;
    *)
      printf '%s/%s\n' "$GH_PROXY" "$original_url"
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
        --connect-timeout 15 \
        --retry 2 \
        --header 'User-Agent: biliTickerBuy-installer' \
        --output "$output" \
        "$url"
    else
      curl \
        --fail \
        --location \
        --silent \
        --show-error \
        --connect-timeout 15 \
        --retry 2 \
        --header 'User-Agent: biliTickerBuy-installer' \
        "$url"
    fi
  elif command -v wget >/dev/null 2>&1; then
    if [ -n "$output" ]; then
      wget \
        --output-document="$output" \
        --timeout=15 \
        --tries=2 \
        --header='User-Agent: biliTickerBuy-installer' \
        "$url"
    else
      wget \
        --quiet \
        --output-document=- \
        --timeout=15 \
        --tries=2 \
        --header='User-Agent: biliTickerBuy-installer' \
        "$url"
    fi
  else
    echo "缺少必要命令：curl 或 wget" >&2
    return 1
  fi
}

request_release_json() {
  # GitHub API 必须优先直连。
  # gh-proxy.org 等代理主要用于 github.com Release 文件下载，
  # 通常不支持 api.github.com。
  if release_json="$(http_get "$API_URL")"; then
    printf '%s' "$release_json"
    return 0
  fi

  echo "获取 GitHub Release 信息失败：$API_URL" >&2
  echo "GitHub 下载代理通常无法代理 api.github.com。" >&2
  echo "请检查当前网络是否能够访问 GitHub API。" >&2
  return 1
}

download_release_asset() {
  asset_url="$1"
  output="$2"

  # Release 文件优先通过 GH_PROXY 下载。
  if [ -n "${GH_PROXY:-}" ]; then
    proxy_url="$(resolve_url "$asset_url")"

    echo "[biliTickerBuy] 正在通过代理下载..." >&2

    if http_get "$proxy_url" "$output"; then
      return 0
    fi

    echo "[biliTickerBuy] 代理下载失败，正在尝试直连..." >&2
    rm -f "$output"
  fi

  if http_get "$asset_url" "$output"; then
    return 0
  fi

  rm -f "$output"
  return 1
}

print_network_help() {
  echo "请根据网络情况尝试取消 GH_PROXY，或更换其他可用加速前缀。" >&2
  echo "禁用代理：" >&2
  echo '  GH_PROXY="" sh install.sh' >&2
  echo "指定代理：" >&2
  echo '  GH_PROXY="https://gh-proxy.org" sh install.sh' >&2
  echo "可用前缀可前往 https://ghproxy.link/ 查找。" >&2
}

append_path_block() {
  rc_file="$1"
  shell_name="$2"

  [ -n "$rc_file" ] || return 0

  mkdir -p "$(dirname "$rc_file")"
  [ -f "$rc_file" ] || : >"$rc_file"

  if grep -Fq "$PATH_MARKER_BEGIN" "$rc_file" 2>/dev/null; then
    return 0
  fi

  {
    printf '\n%s\n' "$PATH_MARKER_BEGIN"
    printf '# biliTickerBuy installer (%s)\n' "$shell_name"
    printf 'export PATH="%s:$PATH"\n' "$BIN_DIR"
    printf '%s\n' "$PATH_MARKER_END"
  } >>"$rc_file"
}

apply_shell_path() {
  append_path_block "$HOME/.bashrc" "bash"
  append_path_block "$HOME/.zshrc" "zsh"
}

find_package_binary() {
  find "$EXTRACT_DIR" \
    -mindepth 1 \
    -maxdepth 3 \
    -type f \
    -name biliTickerBuy \
    -print \
    2>/dev/null |
    head -n 1
}

require_cmd unzip

TMP_DIR="$(mktemp -d)"
ZIP_PATH="$TMP_DIR/biliTickerBuy.zip"
EXTRACT_DIR="$TMP_DIR/extract"

mkdir -p "$EXTRACT_DIR"

cleanup() {
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT HUP INT TERM

echo "[biliTickerBuy] 正在检查最新版本..."

if ! RELEASE_JSON="$(request_release_json)"; then
  print_network_help
  exit 1
fi

# 将各个 asset 对象拆分到独立行，然后匹配当前平台。
# 这里保留轻量级 sed 解析方式，避免强制依赖 jq。
ASSET_URL="$(
  printf '%s' "$RELEASE_JSON" |
    tr -d '\n' |
    sed 's/},{/},\
{/g' |
    grep "\"name\":\"[^\"]*_${PLATFORM_KEY}_[^\"]*\"" |
    sed -n 's/.*"browser_download_url":"\([^"]*\)".*/\1/p' |
    head -n 1
)" || true

RELEASE_TAG="$(
  printf '%s' "$RELEASE_JSON" |
    tr -d '\n' |
    sed -n 's/.*"tag_name":"\([^"]*\)".*/\1/p' |
    head -n 1
)" || true

if [ -z "$ASSET_URL" ]; then
  echo "最新版本中未找到当前平台 ${PLATFORM_KEY} 对应的安装包。" >&2
  exit 1
fi

if [ -z "$RELEASE_TAG" ]; then
  echo "解析最新版本号失败。" >&2
  exit 1
fi

echo "[biliTickerBuy] 最新版本：$RELEASE_TAG"
echo "[biliTickerBuy] 正在下载安装包..."

if ! download_release_asset "$ASSET_URL" "$ZIP_PATH"; then
  echo "安装包下载失败：$ASSET_URL" >&2
  print_network_help
  exit 1
fi

if [ ! -s "$ZIP_PATH" ]; then
  echo "下载到的安装包为空：$ZIP_PATH" >&2
  exit 1
fi

echo "[biliTickerBuy] 正在解压安装包..."

if ! unzip -oq "$ZIP_PATH" -d "$EXTRACT_DIR"; then
  echo "安装包解压失败。" >&2
  exit 1
fi

# 兼容两种压缩包结构：
#
# 1. 文件位于压缩包根目录：
#    biliTickerBuy
#    update.sh
#    .env.install
#
# 2. 文件位于顶层目录：
#    biliTickerBuy/
#      biliTickerBuy
#      update.sh
#      .env.install

if [ -f "$EXTRACT_DIR/biliTickerBuy" ]; then
  PACKAGE_DIR="$EXTRACT_DIR"
elif [ -f "$EXTRACT_DIR/biliTickerBuy/biliTickerBuy" ]; then
  PACKAGE_DIR="$EXTRACT_DIR/biliTickerBuy"
else
  BINARY_PATH="$(find_package_binary)"

  if [ -z "$BINARY_PATH" ] || [ ! -f "$BINARY_PATH" ]; then
    echo "安装包内容不符合预期，未找到 biliTickerBuy 可执行文件。" >&2
    echo "安装包内容如下：" >&2
    find "$EXTRACT_DIR" -maxdepth 3 -print >&2
    exit 1
  fi

  PACKAGE_DIR="$(dirname "$BINARY_PATH")"
fi

mkdir -p "$(dirname "$INSTALL_DIR")"
mkdir -p "$BIN_DIR"

# 先安装到临时目录，全部复制成功后再替换正式目录。
INSTALL_DIR_NEW="${INSTALL_DIR}.new"
INSTALL_DIR_OLD="${INSTALL_DIR}.old"

rm -rf "$INSTALL_DIR_NEW" "$INSTALL_DIR_OLD"
mkdir -p "$INSTALL_DIR_NEW"

if ! cp -R "$PACKAGE_DIR/." "$INSTALL_DIR_NEW/"; then
  echo "复制安装文件失败。" >&2
  rm -rf "$INSTALL_DIR_NEW"
  exit 1
fi

if [ ! -f "$INSTALL_DIR_NEW/biliTickerBuy" ]; then
  echo "安装目录中缺少 biliTickerBuy 可执行文件。" >&2
  rm -rf "$INSTALL_DIR_NEW"
  exit 1
fi

chmod +x "$INSTALL_DIR_NEW/biliTickerBuy"

if [ -f "$INSTALL_DIR_NEW/update.sh" ]; then
  chmod +x "$INSTALL_DIR_NEW/update.sh"
fi

# 将安装成功的 Release 版本写入安装目录，
# 供 update.sh 后续判断是否需要更新。
printf '%s\n' "$RELEASE_TAG" >"$INSTALL_DIR_NEW/.version"

if [ -e "$INSTALL_DIR" ]; then
  if ! mv "$INSTALL_DIR" "$INSTALL_DIR_OLD"; then
    echo "无法备份现有安装目录：$INSTALL_DIR" >&2
    rm -rf "$INSTALL_DIR_NEW"
    exit 1
  fi
fi

if ! mv "$INSTALL_DIR_NEW" "$INSTALL_DIR"; then
  echo "无法替换安装目录：$INSTALL_DIR" >&2

  if [ -e "$INSTALL_DIR_OLD" ]; then
    mv "$INSTALL_DIR_OLD" "$INSTALL_DIR" 2>/dev/null || true
  fi

  exit 1
fi

rm -rf "$INSTALL_DIR_OLD"

LAUNCHER_NEW="${LAUNCHER_PATH}.new"

cat >"$LAUNCHER_NEW" <<EOF
#!/usr/bin/env sh
exec "$INSTALL_DIR/biliTickerBuy" "\$@"
EOF

chmod +x "$LAUNCHER_NEW"

if ! mv -f "$LAUNCHER_NEW" "$LAUNCHER_PATH"; then
  rm -f "$LAUNCHER_NEW"
  echo "创建启动命令失败：$LAUNCHER_PATH" >&2
  exit 1
fi

apply_shell_path

echo "[biliTickerBuy] 安装完成：$INSTALL_DIR"
echo "[biliTickerBuy] 当前版本：$RELEASE_TAG"
echo "[biliTickerBuy] 启动命令：$LAUNCHER_PATH"

case ":$PATH:" in
  *":$BIN_DIR:"*)
    ;;
  *)
    echo "[biliTickerBuy] 已将 PATH 配置写入 ~/.bashrc 和 ~/.zshrc。"
    echo "请重新打开终端，或执行："
    echo "export PATH=\"$BIN_DIR:\$PATH\""
    ;;
esac
```
