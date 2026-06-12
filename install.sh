#!/usr/bin/env sh
set -eu

REPO="mikumifa/biliTickerBuy"
UNAME_S="$(uname -s)"
UNAME_M="$(uname -m)"
GH_PROXY="${GH_PROXY:-}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/biliTickerBuy}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
LAUNCHER_PATH="$BIN_DIR/btb"
API_URL="https://api.github.com/repos/$REPO/releases/latest"
PATH_MARKER_BEGIN="# >>> biliTickerBuy PATH >>>"
PATH_MARKER_END="# <<< biliTickerBuy PATH <<<"

case "$UNAME_S:$UNAME_M" in
  Linux:x86_64|Linux:amd64) PLATFORM_KEY="linux_amd64" ;;
  Linux:aarch64|Linux:arm64) PLATFORM_KEY="linux_arm64" ;;
  Darwin:arm64|Darwin:aarch64) PLATFORM_KEY="macos_arm64" ;;
  Darwin:x86_64|Darwin:amd64) PLATFORM_KEY="macos_intel" ;;
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
      if ! curl --fail --location --progress-bar -H 'User-Agent: biliTickerBuy-installer' -o "$output" "$url"; then
        echo "下载失败：$url" >&2
        echo "请根据网络情况尝试取消 GH_PROXY，或更换为其他可用加速前缀，例如 https://ghproxy.link/" >&2
        exit 1
      fi
    else
      if ! curl --fail --location --silent --show-error -H 'User-Agent: biliTickerBuy-installer' "$url"; then
        echo "请求失败：$url" >&2
        echo "请根据网络情况尝试取消 GH_PROXY，或更换为其他可用加速前缀，例如 https://ghproxy.link/" >&2
        exit 1
      fi
    fi
  elif command -v wget >/dev/null 2>&1; then
    if [ -n "$output" ]; then
      if ! wget -O "$output" --header='User-Agent: biliTickerBuy-installer' "$url"; then
        echo "下载失败：$url" >&2
        echo "请根据网络情况尝试取消 GH_PROXY，或更换为其他可用加速前缀，例如 https://ghproxy.link/" >&2
        exit 1
      fi
    else
      if ! wget -qO- --header='User-Agent: biliTickerBuy-installer' "$url"; then
        echo "请求失败：$url" >&2
        echo "请根据网络情况尝试取消 GH_PROXY，或更换为其他可用加速前缀，例如 https://ghproxy.link/" >&2
        exit 1
      fi
    fi
  else
    echo "缺少必要命令：curl 或 wget" >&2
    exit 1
  fi
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
  append_path_block "${HOME}/.bashrc" "bash"
  append_path_block "${HOME}/.zshrc" "zsh"
}

require_cmd unzip
TMP_DIR="$(mktemp -d)"
ZIP_PATH="$TMP_DIR/biliTickerBuy.zip"
EXTRACT_DIR="$TMP_DIR/extract"
mkdir -p "$EXTRACT_DIR"
trap 'rm -rf "$TMP_DIR"' EXIT INT TERM

echo "[biliTickerBuy] 正在检查最新版本..."
RELEASE_JSON="$(http_get "$(resolve_url "$API_URL")")"
ASSET_URL="$(printf '%s' "$RELEASE_JSON" | tr -d '\n' | sed 's/},{/},\
{/g' | grep "\"name\":\"[^\"]*_${PLATFORM_KEY}_[^\"]*\"" | sed -n 's/.*"browser_download_url":"\([^"]*\)".*/\1/p' | head -n 1)"
RELEASE_TAG="$(printf '%s' "$RELEASE_JSON" | sed -n 's/.*"tag_name":"\([^"]*\)".*/\1/p' | head -n 1)"

[ -n "$ASSET_URL" ] || {
  echo "最新版本中未找到当前平台 ${PLATFORM_KEY} 对应的安装包" >&2
  exit 1
}
[ -n "$RELEASE_TAG" ] || {
  echo "解析最新版本号失败" >&2
  exit 1
}

echo "[biliTickerBuy] 正在下载 ${RELEASE_TAG}..."
http_get "$(resolve_url "$ASSET_URL")" "$ZIP_PATH"

echo "[biliTickerBuy] 正在解压安装包..."
unzip -oq "$ZIP_PATH" -d "$EXTRACT_DIR"

if [ ! -d "$EXTRACT_DIR/biliTickerBuy" ]; then
  echo "安装包内容不符合预期，缺少 biliTickerBuy 目录。" >&2
  exit 1
fi

mkdir -p "$(dirname "$INSTALL_DIR")" "$BIN_DIR"
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -R "$EXTRACT_DIR/biliTickerBuy/." "$INSTALL_DIR/"

if [ -f "$INSTALL_DIR/update.sh" ]; then
  chmod +x "$INSTALL_DIR/update.sh"
fi
if [ -f "$INSTALL_DIR/biliTickerBuy" ]; then
  chmod +x "$INSTALL_DIR/biliTickerBuy"
fi

cat >"$LAUNCHER_PATH" <<EOF
#!/usr/bin/env sh
exec "$INSTALL_DIR/biliTickerBuy" "\$@"
EOF
chmod +x "$LAUNCHER_PATH"
apply_shell_path

echo "[biliTickerBuy] 安装完成：$INSTALL_DIR"
echo "[biliTickerBuy] 启动命令：$LAUNCHER_PATH"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo "[biliTickerBuy] 已写入 PATH 到 ~/.bashrc 和 ~/.zshrc（如存在）。"
    echo "请重新打开终端，或执行：export PATH=\"$BIN_DIR:\$PATH\""
    ;;
esac
