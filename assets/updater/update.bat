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
if errorlevel 1 exit /b 1

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
  echo [biliTickerBuy] 检测到已下载的更新包，跳过下载："%TEMP_ZIP%"
) else (
  echo [biliTickerBuy] 正在下载 !RELEASE_TAG!...
  where curl.exe >nul 2>nul
  if not errorlevel 1 (
    curl.exe -L --progress-bar -H "User-Agent: biliTickerBuy-updater" -o "%TEMP_ZIP%" "%ASSET_URL%"
    if errorlevel 1 exit /b 1
  ) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$ErrorActionPreference='Stop'; Invoke-WebRequest -Headers @{ 'User-Agent'='biliTickerBuy-updater' } -Uri '%ASSET_URL%' -OutFile '%TEMP_ZIP%'"
    if errorlevel 1 exit /b 1
  )
)

echo [biliTickerBuy] 正在解压更新包...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; Expand-Archive -Path '%TEMP_ZIP%' -DestinationPath '%TEMP_EXTRACT%' -Force"
if errorlevel 1 exit /b 1

if not exist "%TEMP_EXTRACT%\biliTickerBuy.exe" (
  echo 解压后的更新包中缺少 biliTickerBuy.exe
  exit /b 1
)

echo [biliTickerBuy] 正在替换本地文件...
copy /y "%TEMP_EXTRACT%\biliTickerBuy.exe" "%INSTALL_DIR%\biliTickerBuy.exe" >nul
if errorlevel 1 (
  echo 无法替换 biliTickerBuy.exe。
  echo 请先关闭正在运行的 biliTickerBuy，然后重新执行 update.bat。
  pause
  exit /b 1
)
if exist "%TEMP_EXTRACT%\update.bat" copy /y "%TEMP_EXTRACT%\update.bat" "%INSTALL_DIR%\update.bat" >nul
if exist "%TEMP_EXTRACT%\.env.install" copy /y "%TEMP_EXTRACT%\.env.install" "%INSTALL_DIR%\.env.install" >nul
if exist "%TEMP_ZIP%" del /f /q "%TEMP_ZIP%" >nul 2>nul
if exist "%META_FILE%" del /f /q "%META_FILE%" >nul 2>nul
if exist "%TEMP_EXTRACT%" rmdir /s /q "%TEMP_EXTRACT%" >nul 2>nul

echo [biliTickerBuy] 已更新到 !RELEASE_TAG!。
echo 请手动重新启动程序。
pause
