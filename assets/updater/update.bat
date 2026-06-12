@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

set "REPO=mikumifa/biliTickerBuy"
set "PLATFORM_KEY=windows_amd64"
set "INSTALL_DIR=%~dp0"
if "%INSTALL_DIR:~-1%"=="\" set "INSTALL_DIR=%INSTALL_DIR:~0,-1%"
set "WORK_DIR=%INSTALL_DIR%\updates"
set "TEMP_ZIP=%WORK_DIR%\update.zip"
set "TEMP_EXTRACT=%WORK_DIR%\extract"
set "META_FILE=%WORK_DIR%\release-meta.txt"
set "API_URL=https://api.github.com/repos/%REPO%/releases/latest"
set "ENV_INSTALL_FILE=%INSTALL_DIR%\.env.install"

if exist "%ENV_INSTALL_FILE%" (
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /r /v "^[ ]*# ^[ ]*$" "%ENV_INSTALL_FILE%"`) do (
    if /i "%%A"=="GH_PROXY" set "GH_PROXY=%%B"
  )
)

if defined GH_PROXY (
  if "!GH_PROXY:~-1!"=="/" (
    set "API_URL=!GH_PROXY!!API_URL!"
  ) else (
    set "API_URL=!GH_PROXY!/!API_URL!"
  )
)

echo [biliTickerBuy] Checking latest release for %PLATFORM_KEY%...
where powershell >nul 2>nul || (
  echo 未找到 PowerShell，无法执行更新。
  exit /b 1
)

mkdir "%WORK_DIR%" >nul 2>nul
if exist "%TEMP_EXTRACT%" rmdir /s /q "%TEMP_EXTRACT%"
mkdir "%TEMP_EXTRACT%" >nul 2>nul
if exist "%META_FILE%" del /f /q "%META_FILE%" >nul 2>nul

set "RELEASE_TAG="
set "ASSET_URL="

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$headers = @{ 'User-Agent'='biliTickerBuy-updater' };" ^
  "$apiUrl = '%API_URL%';" ^
  "try { $release = Invoke-RestMethod -Headers $headers -Uri $apiUrl } catch { $release = Invoke-RestMethod -Headers $headers -Uri 'https://api.github.com/repos/%REPO%/releases/latest' };" ^
  "$asset = $release.assets | Where-Object { $_.name -like '*_%PLATFORM_KEY%_*' } | Select-Object -First 1;" ^
  "if (-not $asset) { throw 'Latest release does not contain the expected Windows package.' }" ^
  "$assetUrl = $asset.browser_download_url;" ^
  "$proxy = $env:GH_PROXY;" ^
  "if ($proxy) { if (-not $proxy.EndsWith('/')) { $proxy += '/' }; $assetUrl = $proxy + $assetUrl }" ^
  "$content = 'RELEASE_TAG=' + $release.tag_name + '|' + 'ASSET_URL=' + $assetUrl;" ^
  "[System.IO.File]::WriteAllText('%META_FILE%', $content, [System.Text.Encoding]::ASCII)"
if errorlevel 1 (
  echo 获取版本信息失败。
  echo 请根据网络情况尝试取消 GH_PROXY，或更换为其他可用加速前缀。
  echo 可在安装目录的 .env.install 中配置，例如：GH_PROXY=https://gh-proxy.org
  echo 可用前缀可前往 https://ghproxy.link/ 查找。
  exit /b 1
)

if not exist "%META_FILE%" (
  echo 生成版本信息失败。
  exit /b 1
)

for /f "usebackq tokens=1,2 delims=|" %%A in ("%META_FILE%") do (
  for /f "tokens=1,* delims==" %%C in ("%%A") do (
    if /i "%%C"=="RELEASE_TAG" set "RELEASE_TAG=%%D"
  )
  for /f "tokens=1,* delims==" %%C in ("%%B") do (
    if /i "%%C"=="ASSET_URL" set "ASSET_URL=%%D"
  )
)

if not defined ASSET_URL (
  echo 未能解析到可用的更新包地址。
  exit /b 1
)

if exist "%TEMP_ZIP%" (
  echo [biliTickerBuy] 检测到已下载的更新包，正在校验...

  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "Add-Type -AssemblyName System.IO.Compression.FileSystem;" ^
    "$zip = [System.IO.Compression.ZipFile]::OpenRead('%TEMP_ZIP%');" ^
    "$zip.Dispose()"
    
  if errorlevel 1 (
    echo [biliTickerBuy] 已下载的文件不是有效 ZIP，将重新下载。
    del /f /q "%TEMP_ZIP%" >nul 2>nul
  ) else (
    echo [biliTickerBuy] 已下载的更新包校验通过，跳过下载。
  )
)

if not exist "%TEMP_ZIP%" (
  echo [biliTickerBuy] 正在下载 !RELEASE_TAG!...

  where curl.exe >nul 2>nul
  if not errorlevel 1 (
    curl.exe ^
      --fail ^
      --location ^
      --retry 3 ^
      --retry-delay 2 ^
      --progress-bar ^
      -H "User-Agent: biliTickerBuy-updater" ^
      -H "Accept: application/octet-stream" ^
      -o "%TEMP_ZIP%" ^
      "%ASSET_URL%"

    if errorlevel 1 (
      echo 下载失败：%ASSET_URL%
      if exist "%TEMP_ZIP%" del /f /q "%TEMP_ZIP%" >nul 2>nul
      exit /b 1
    )
  ) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$ErrorActionPreference='Stop';" ^
      "Invoke-WebRequest -UseBasicParsing -Headers @{ 'User-Agent'='biliTickerBuy-updater'; 'Accept'='application/octet-stream' } -Uri '%ASSET_URL%' -OutFile '%TEMP_ZIP%'"

    if errorlevel 1 (
      echo 下载失败：%ASSET_URL%
      if exist "%TEMP_ZIP%" del /f /q "%TEMP_ZIP%" >nul 2>nul
      exit /b 1
    )
  )
)

echo [biliTickerBuy] 正在验证更新包...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Add-Type -AssemblyName System.IO.Compression.FileSystem;" ^
  "$zip = [System.IO.Compression.ZipFile]::OpenRead('%TEMP_ZIP%');" ^
  "if ($zip.Entries.Count -eq 0) { throw 'ZIP archive is empty.' };" ^
  "$zip.Dispose()"

if errorlevel 1 (
  echo 更新包不是有效的 ZIP 文件。
  echo 下载地址：%ASSET_URL%
  echo 这通常是因为 GitHub 代理返回了错误页面。
  del /f /q "%TEMP_ZIP%" >nul 2>nul
  exit /b 1
)

echo [biliTickerBuy] 正在解压更新包...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Expand-Archive -LiteralPath '%TEMP_ZIP%' -DestinationPath '%TEMP_EXTRACT%' -Force"

if errorlevel 1 (
  echo 解压更新包失败。
  del /f /q "%TEMP_ZIP%" >nul 2>nul
  exit /b 1
)

echo [biliTickerBuy] 正在解压更新包...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; Expand-Archive -Path '%TEMP_ZIP%' -DestinationPath '%TEMP_EXTRACT%' -Force"
if errorlevel 1 exit /b 1

if not exist "%TEMP_EXTRACT%\biliTickerBuy.exe" (
  echo 解压后的更新包中缺少 biliTickerBuy.exe
  exit /b 1
)

echo [biliTickerBuy] 正在等待主程序退出...

set /a WAIT_COUNT=0

:WAIT_APP_EXIT
tasklist /fi "imagename eq biliTickerBuy.exe" /nh 2>nul | find /i "biliTickerBuy.exe" >nul

if not errorlevel 1 (
  set /a WAIT_COUNT+=1

  if !WAIT_COUNT! geq 30 (
    echo 主程序长时间未退出，尝试强制关闭...
    taskkill /f /im biliTickerBuy.exe >nul 2>nul
    timeout /t 2 /nobreak >nul
    goto REPLACE_APP
  )

  timeout /t 1 /nobreak >nul
  goto WAIT_APP_EXIT
)

:REPLACE_APP
echo [biliTickerBuy] 正在替换本地文件...

set "SOURCE_EXE=%TEMP_EXTRACT%\biliTickerBuy.exe"
set "TARGET_EXE=%INSTALL_DIR%\biliTickerBuy.exe"
set "NEW_EXE=%INSTALL_DIR%\biliTickerBuy.exe.new"
set "OLD_EXE=%INSTALL_DIR%\biliTickerBuy.exe.old"

if not exist "%SOURCE_EXE%" (
  echo 解压后的更新包中缺少 biliTickerBuy.exe。
  pause
  exit /b 1
)

echo [DEBUG] 更新来源：%SOURCE_EXE%
echo [DEBUG] 更新目标：%TARGET_EXE%

set "SOURCE_HASH="
set "TARGET_HASH_BEFORE="
set "TARGET_HASH_AFTER="

for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command ^
  "(Get-FileHash -LiteralPath '%SOURCE_EXE%' -Algorithm SHA256).Hash"`) do (
  set "SOURCE_HASH=%%H"
)

if exist "%TARGET_EXE%" (
  for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command ^
    "(Get-FileHash -LiteralPath '%TARGET_EXE%' -Algorithm SHA256).Hash"`) do (
    set "TARGET_HASH_BEFORE=%%H"
  )
)

echo [DEBUG] 更新包哈希：!SOURCE_HASH!
if defined TARGET_HASH_BEFORE (
  echo [DEBUG] 当前版本哈希：!TARGET_HASH_BEFORE!
)

if defined TARGET_HASH_BEFORE if /i "!SOURCE_HASH!"=="!TARGET_HASH_BEFORE!" (
  echo [biliTickerBuy] 当前程序与更新包完全相同，无需替换。
  goto UPDATE_SUCCESS
)

if exist "%NEW_EXE%" del /f /q "%NEW_EXE%" >nul 2>nul
if exist "%OLD_EXE%" del /f /q "%OLD_EXE%" >nul 2>nul

copy /b /y "%SOURCE_EXE%" "%NEW_EXE%" >nul
if errorlevel 1 (
  echo 无法把新版程序复制到安装目录。
  pause
  exit /b 1
)

set /a REPLACE_COUNT=0

:RETRY_REPLACE
set /a REPLACE_COUNT+=1

if exist "%TARGET_EXE%" (
  move /y "%TARGET_EXE%" "%OLD_EXE%" >nul 2>nul

  if errorlevel 1 (
    if !REPLACE_COUNT! geq 10 (
      echo 无法移动旧版程序，文件可能仍被占用。
      echo 请手动确认 biliTickerBuy.exe 是否已完全退出。
      del /f /q "%NEW_EXE%" >nul 2>nul
      pause
      exit /b 1
    )

    echo [biliTickerBuy] 程序仍被占用，正在重试 !REPLACE_COUNT!/10...
    taskkill /f /im biliTickerBuy.exe >nul 2>nul
    timeout /t 1 /nobreak >nul
    goto RETRY_REPLACE
  )
)

move /y "%NEW_EXE%" "%TARGET_EXE%" >nul 2>nul
if errorlevel 1 (
  echo 无法启用新版 biliTickerBuy.exe，正在恢复旧版本...

  if exist "%OLD_EXE%" (
    move /y "%OLD_EXE%" "%TARGET_EXE%" >nul 2>nul
  )

  pause
  exit /b 1
)

if not exist "%TARGET_EXE%" (
  echo 替换后目标程序不存在，正在恢复旧版本...

  if exist "%OLD_EXE%" (
    move /y "%OLD_EXE%" "%TARGET_EXE%" >nul 2>nul
  )

  pause
  exit /b 1
)

for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command ^
  "(Get-FileHash -LiteralPath '%TARGET_EXE%' -Algorithm SHA256).Hash"`) do (
  set "TARGET_HASH_AFTER=%%H"
)

echo [DEBUG] 替换后哈希：!TARGET_HASH_AFTER!

if /i not "!SOURCE_HASH!"=="!TARGET_HASH_AFTER!" (
  echo 替换后的文件与更新包不一致，正在回滚...

  del /f /q "%TARGET_EXE%" >nul 2>nul

  if exist "%OLD_EXE%" (
    move /y "%OLD_EXE%" "%TARGET_EXE%" >nul 2>nul
  )

  pause
  exit /b 1
)

if exist "%OLD_EXE%" del /f /q "%OLD_EXE%" >nul 2>nul

:UPDATE_SUCCESS
if exist "%TEMP_EXTRACT%\update.bat" (
  copy /y "%TEMP_EXTRACT%\update.bat" "%INSTALL_DIR%\update.bat.next" >nul 2>nul
)

if exist "%TEMP_EXTRACT%\.env.install" (
  copy /y "%TEMP_EXTRACT%\.env.install" "%INSTALL_DIR%\.env.install" >nul 2>nul
)

if exist "%TEMP_ZIP%" del /f /q "%TEMP_ZIP%" >nul 2>nul
if exist "%META_FILE%" del /f /q "%META_FILE%" >nul 2>nul
if exist "%TEMP_EXTRACT%" rmdir /s /q "%TEMP_EXTRACT%" >nul 2>nul

echo [biliTickerBuy] 已成功更新到 !RELEASE_TAG!
pause
exit /b 0