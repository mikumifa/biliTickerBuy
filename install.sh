#!/usr/bin/env sh
set -eu

REPO="mikumifa/biliTickerBuy"

UNAME_S="$(uname -s)"
UNAME_M="$(uname -m)"

# 未设置 GH_PROXY 时使用默认代理。
#
# 禁用代理：
#   GH_PROXY="" sh install.sh
#
# 指定代理：
#   GH_PROXY="https://gh-proxy.org" sh install.sh
GH_PROXY="${GH_PROXY-https://gh-proxy.org}"

INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/biliTickerBuy}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
LAUNCHER_PATH="$BIN_DIR/btb"

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

VERSION_INFO_URL="https://github.com/$REPO/releases/latest/download/version-info.json"
VERSION_INFO_URL="$(resolve_url "$VERSION_INFO_URL")"

http_get() {
  url="$1"
  output="${2:-}"

  if command -v curl >/dev/null 2>&1; then
    if [ -n "$output" ]; then
      partial_output="${output}.part"

      rm -f "$partial_output"

      if curl \
        --fail \
        --location \
        --progress-bar \
        --connect-timeout 15 \
        --retry 2 \
        --header 'Accept: application/octet-stream' \
        --header 'User-Agent: biliTickerBuy-installer' \
        --output "$partial_output" \
        "$url"
      then
        mv -f "$partial_output" "$output"
        return 0
      fi

      rm -f "$partial_output"
      return 1
    fi

    curl \
      --fail \
      --location \
      --silent \
      --show-error \
      --connect-timeout 15 \
      --retry 2 \
      --header 'Accept: application/json' \
      --header 'User-Agent: biliTickerBuy-installer' \
      "$url"

    return $?
  fi

  if command -v wget >/dev/null 2>&1; then
    if [ -n "$output" ]; then
      partial_output="${output}.part"

      rm -f "$partial_output"

      if wget \
        --output-document="$partial_output" \
        --timeout=15 \
        --tries=2 \
        --header='Accept: application/octet-stream' \
        --header='User-Agent: biliTickerBuy-installer' \
        "$url"
      then
        mv -f "$partial_output" "$output"
        return 0
      fi

      rm -f "$partial_output"
      return 1
    fi

    wget \
      --quiet \
      --output-document=- \
      --timeout=15 \
      --tries=2 \
      --header='Accept: application/json' \
      --header='User-Agent: biliTickerBuy-installer' \
      "$url"

    return $?
  fi

  echo "缺少必要命令：curl 或 wget" >&2
  return 1
}

request_version_info() {
  # version-info.json 优先直连。
  if version_info_json="$(http_get "$VERSION_INFO_URL" 2>/dev/null)"; then
    printf '%s' "$version_info_json"
    return 0
  fi

  if [ -n "${GH_PROXY:-}" ]; then
    proxy_url="$(resolve_url "$VERSION_INFO_URL")"

    echo "[biliTickerBuy] 版本信息直连失败，正在尝试代理..." >&2

    if version_info_json="$(http_get "$proxy_url")"; then
      printf '%s' "$version_info_json"
      return 0
    fi
  fi

  echo "获取版本信息失败：$VERSION_INFO_URL" >&2
  return 1
}

parse_version_info() {
  version_info_json="$1"
  platform_key="$2"

  RELEASE_TAG="$(
    printf '%s\n' "$version_info_json" |
      sed -n \
        's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' |
      head -n 1
  )"

  platform_block="$(
    printf '%s\n' "$version_info_json" |
      awk -v target="\"${platform_key}\"" '
        index($0, target) {
          in_block = 1
        }

        in_block {
          print

          if ($0 ~ /^[[:space:]]*}[,]?[[:space:]]*$/) {
            exit
          }
        }
      '
  )"

  ASSET_NAME="$(
    printf '%s\n' "$platform_block" |
      sed -n \
        's/^[[:space:]]*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' |
      head -n 1
  )"

  ASSET_SHA256="$(
    printf '%s\n' "$platform_block" |
      sed -n \
        's/^[[:space:]]*"sha256"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' |
      head -n 1
  )"

  ASSET_SIZE="$(
    printf '%s\n' "$platform_block" |
      sed -n \
        's/^[[:space:]]*"size"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' |
      head -n 1
  )"

  if [ -z "$RELEASE_TAG" ]; then
    echo "version-info.json 中缺少 version 字段。" >&2
    return 1
  fi

  if [ -z "$platform_block" ]; then
    echo "version-info.json 中未找到平台：$platform_key" >&2
    return 1
  fi

  if [ -z "$ASSET_NAME" ]; then
    echo "version-info.json 中缺少 ${platform_key}.name。" >&2
    return 1
  fi

  if [ -z "$ASSET_SHA256" ]; then
    echo "version-info.json 中缺少 ${platform_key}.sha256。" >&2
    return 1
  fi

  if [ -z "$ASSET_SIZE" ]; then
    echo "version-info.json 中缺少 ${platform_key}.size。" >&2
    return 1
  fi

  return 0
}

validate_version_info() {
  case "$RELEASE_TAG" in
    ""|*[!0-9A-Za-z._+-]*)
      echo "version-info.json 中的版本号格式无效：$RELEASE_TAG" >&2
      return 1
      ;;
  esac

  case "$ASSET_NAME" in
    *.zip)
      ;;
    *)
      echo "安装包文件名不是 ZIP：$ASSET_NAME" >&2
      return 1
      ;;
  esac

  # 防止路径穿越。
  case "$ASSET_NAME" in
    */*|*\\*|.|..)
      echo "version-info.json 中的文件名不安全：$ASSET_NAME" >&2
      return 1
      ;;
  esac

  case "$ASSET_SHA256" in
    *[!0-9a-fA-F]*)
      echo "SHA256 格式无效：$ASSET_SHA256" >&2
      return 1
      ;;
  esac

  if [ "${#ASSET_SHA256}" -ne 64 ]; then
    echo "SHA256 长度无效：$ASSET_SHA256" >&2
    return 1
  fi

  case "$ASSET_SIZE" in
    ""|*[!0-9]*)
      echo "安装包大小格式无效：$ASSET_SIZE" >&2
      return 1
      ;;
  esac

  return 0
}

is_valid_zip() {
  zip_file="$1"

  [ -s "$zip_file" ] || return 1

  zip_signature="$(
    LC_ALL=C od -An -tx1 -N4 "$zip_file" 2>/dev/null |
      tr -d ' \n'
  )"

  case "$zip_signature" in
    504b0304|504b0506|504b0708)
      ;;
    *)
      return 1
      ;;
  esac

  unzip -tq "$zip_file" >/dev/null 2>&1
}

print_invalid_download() {
  downloaded_file="$1"
  source_url="$2"

  echo "下载到的文件不是有效 ZIP：$source_url" >&2

  if [ ! -f "$downloaded_file" ]; then
    return 0
  fi

  file_size="$(
    wc -c <"$downloaded_file" 2>/dev/null |
      tr -d ' '
  )"

  echo "文件大小：${file_size:-未知} 字节" >&2

  if command -v file >/dev/null 2>&1; then
    file_type="$(file -b "$downloaded_file" 2>/dev/null || true)"
    echo "文件类型：${file_type:-未知}" >&2
  fi

  echo "响应内容开头：" >&2

  LC_ALL=C head -c 300 "$downloaded_file" 2>/dev/null |
    tr '\000-\010\013\014\016-\037' ' ' >&2 || true

  printf '\n' >&2
}

download_release_asset() {
  asset_url="$1"
  output="$2"

  rm -f "$output" "${output}.part"

  if [ -n "${GH_PROXY:-}" ]; then
    proxy_url="$(resolve_url "$asset_url")"

    echo "[biliTickerBuy] 正在通过代理下载..."
    echo "[biliTickerBuy] 下载地址：$proxy_url"

    if http_get "$proxy_url" "$output"; then
      if is_valid_zip "$output"; then
        return 0
      fi

      print_invalid_download "$output" "$proxy_url"
    else
      echo "[biliTickerBuy] 代理下载失败。" >&2
    fi

    echo "[biliTickerBuy] 代理未返回有效安装包，正在尝试直连..."
    rm -f "$output" "${output}.part"
  fi

  echo "[biliTickerBuy] 正在直连 GitHub 下载..."
  echo "[biliTickerBuy] 下载地址：$asset_url"

  if http_get "$asset_url" "$output"; then
    if is_valid_zip "$output"; then
      return 0
    fi

    print_invalid_download "$output" "$asset_url"
  fi

  rm -f "$output" "${output}.part"
  return 1
}

get_file_size() {
  file_path="$1"

  case "$UNAME_S" in
    Darwin)
      stat -f '%z' "$file_path"
      ;;
    *)
      stat -c '%s' "$file_path"
      ;;
  esac
}

calculate_sha256() {
  file_path="$1"

  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file_path" |
      awk '{print $1}'
    return 0
  fi

  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file_path" |
      awk '{print $1}'
    return 0
  fi

  if command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$file_path" |
      sed 's/^.*= //'
    return 0
  fi

  echo "缺少 SHA256 校验命令：sha256sum、shasum 或 openssl。" >&2
  return 1
}

verify_download() {
  downloaded_file="$1"
  expected_size="$2"
  expected_sha256="$3"

  actual_size="$(get_file_size "$downloaded_file")"

  if [ "$actual_size" != "$expected_size" ]; then
    echo "安装包大小校验失败。" >&2
    echo "预期大小：$expected_size 字节" >&2
    echo "实际大小：$actual_size 字节" >&2
    return 1
  fi

  actual_sha256="$(calculate_sha256 "$downloaded_file")" || return 1

  actual_sha256="$(
    printf '%s' "$actual_sha256" |
      tr 'A-F' 'a-f'
  )"

  expected_sha256="$(
    printf '%s' "$expected_sha256" |
      tr 'A-F' 'a-f'
  )"

  if [ "$actual_sha256" != "$expected_sha256" ]; then
    echo "安装包 SHA256 校验失败。" >&2
    echo "预期 SHA256：$expected_sha256" >&2
    echo "实际 SHA256：$actual_sha256" >&2
    return 1
  fi

  return 0
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

print_network_help() {
  echo "请根据网络情况尝试取消 GH_PROXY，或更换其他可用加速前缀。" >&2
  echo "禁用代理：" >&2
  echo '  GH_PROXY="" sh install.sh' >&2
  echo "指定代理：" >&2
  echo '  GH_PROXY="https://gh-proxy.org" sh install.sh' >&2
  echo "可用前缀可前往 https://ghproxy.link/ 查找。" >&2
}

cleanup() {
  rm -rf "$TMP_DIR"
}

require_cmd unzip
require_cmd od
require_cmd awk
require_cmd sed
require_cmd grep
require_cmd find

TMP_DIR="$(mktemp -d)"
ZIP_PATH="$TMP_DIR/biliTickerBuy.zip"
EXTRACT_DIR="$TMP_DIR/extract"

mkdir -p "$EXTRACT_DIR"

trap cleanup EXIT HUP INT TERM

echo "[biliTickerBuy] 正在检查最新版本..."

if ! VERSION_INFO_JSON="$(request_version_info)"; then
  print_network_help
  exit 1
fi

if ! parse_version_info "$VERSION_INFO_JSON" "$PLATFORM_KEY"; then
  exit 1
fi

if ! validate_version_info; then
  exit 1
fi

ASSET_URL="https://github.com/$REPO/releases/download/$RELEASE_TAG/$ASSET_NAME"

echo "[biliTickerBuy] 最新版本：$RELEASE_TAG"
echo "[biliTickerBuy] 当前平台：$PLATFORM_KEY"
echo "[biliTickerBuy] 安装包：$ASSET_NAME"
echo "[biliTickerBuy] 预期大小：$ASSET_SIZE 字节"

if ! download_release_asset "$ASSET_URL" "$ZIP_PATH"; then
  echo "安装包下载失败：$ASSET_URL" >&2
  print_network_help
  exit 1
fi

echo "[biliTickerBuy] 正在校验安装包..."

if ! verify_download "$ZIP_PATH" "$ASSET_SIZE" "$ASSET_SHA256"; then
  rm -f "$ZIP_PATH"
  echo "安装包完整性校验失败，已删除下载文件。" >&2
  exit 1
fi

if ! is_valid_zip "$ZIP_PATH"; then
  rm -f "$ZIP_PATH"
  echo "下载到的文件不是有效 ZIP 安装包。" >&2
  exit 1
fi

echo "[biliTickerBuy] 安装包校验通过。"
echo "[biliTickerBuy] 正在解压安装包..."

if ! unzip -oq "$ZIP_PATH" -d "$EXTRACT_DIR"; then
  echo "安装包解压失败：$ZIP_PATH" >&2
  exit 1
fi

# 兼容以下两种压缩包结构：
#
# 1. 文件直接位于根目录：
#
#    biliTickerBuy
#    update.sh
#    .env.install
#
# 2. 文件位于顶层目录：
#
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

echo "[biliTickerBuy] 找到安装文件：$PACKAGE_DIR"

mkdir -p "$(dirname "$INSTALL_DIR")"
mkdir -p "$BIN_DIR"

INSTALL_DIR_NEW="${INSTALL_DIR}.new"
INSTALL_DIR_OLD="${INSTALL_DIR}.old"

rm -rf "$INSTALL_DIR_NEW"
rm -rf "$INSTALL_DIR_OLD"

mkdir -p "$INSTALL_DIR_NEW"

echo "[biliTickerBuy] 正在复制安装文件..."

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

if ! printf '%s\n' "$RELEASE_TAG" >"$INSTALL_DIR_NEW/.version"; then
  echo "写入版本文件失败。" >&2
  rm -rf "$INSTALL_DIR_NEW"
  exit 1
fi

if [ -e "$INSTALL_DIR" ]; then
  if ! mv "$INSTALL_DIR" "$INSTALL_DIR_OLD"; then
    echo "无法备份现有安装目录：$INSTALL_DIR" >&2
    rm -rf "$INSTALL_DIR_NEW"
    exit 1
  fi
fi

if ! mv "$INSTALL_DIR_NEW" "$INSTALL_DIR"; then
  echo "无法替换安装目录：$INSTALL_DIR" >&2

  rm -rf "$INSTALL_DIR_NEW"

  if [ -e "$INSTALL_DIR_OLD" ]; then
    if ! mv "$INSTALL_DIR_OLD" "$INSTALL_DIR"; then
      echo "警告：恢复旧安装目录失败：$INSTALL_DIR_OLD" >&2
    fi
  fi

  exit 1
fi

rm -rf "$INSTALL_DIR_OLD"

LAUNCHER_NEW="${LAUNCHER_PATH}.new"

rm -f "$LAUNCHER_NEW"

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