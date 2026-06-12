#requires -Version 5.1
<#
.SYNOPSIS
    biliTickerBuy Windows 一键安装脚本。

.DESCRIPTION
    可通过以下方式直接安装：

        irm https://raw.githubusercontent.com/mikumifa/biliTickerBuy/main/install.ps1 | iex

    也可以下载后执行：

        powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1

    本地执行时支持参数：

        .\install.ps1 -NoProxy
        .\install.ps1 -GhProxy "https://其他代理前缀"
        .\install.ps1 -InstallDir "D:\Apps\biliTickerBuy" -BinDir "D:\Apps\bin"
#>

param(
    [string]$GhProxy,
    [switch]$NoProxy,
    [string]$InstallDir,
    [string]$BinDir
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$Repo = "mikumifa/biliTickerBuy"
$PlatformKey = "windows_amd64"

function Write-Info {
    param([string]$Message)

    Write-Host "[biliTickerBuy] $Message"
}

function Write-ErrorMessage {
    param([string]$Message)

    [Console]::Error.WriteLine($Message)
}

function Get-EnvironmentValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    return [Environment]::GetEnvironmentVariable(
        $Name,
        [EnvironmentVariableTarget]::Process
    )
}

function Resolve-ProxyUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OriginalUrl,

        [AllowEmptyString()]
        [string]$Proxy
    )

    if ([string]::IsNullOrEmpty($Proxy)) {
        return $OriginalUrl
    }

    return $Proxy.TrimEnd("/") + "/" + $OriginalUrl
}

function Invoke-HttpText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    $headers = @{
        Accept       = "application/json"
        "User-Agent" = "biliTickerBuy-installer"
    }

    $params = @{
        Uri                = $Url
        Headers            = $headers
        UseBasicParsing    = $true
        TimeoutSec         = 30
        MaximumRedirection = 10
    }

    $response = Invoke-WebRequest @params
    return [string]$response.Content
}

function Invoke-HttpDownload {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,

        [Parameter(Mandatory = $true)]
        [string]$OutputPath
    )

    $partialPath = "$OutputPath.part"

    Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $partialPath -Force -ErrorAction SilentlyContinue

    try {
        $curl = Get-Command "curl.exe" -ErrorAction SilentlyContinue

        if ($null -ne $curl) {
            & $curl.Source `
                --fail `
                --location `
                --progress-bar `
                --connect-timeout 15 `
                --retry 2 `
                --header "Accept: application/octet-stream" `
                --header "User-Agent: biliTickerBuy-installer" `
                --output $partialPath `
                $Url

            if ($LASTEXITCODE -ne 0) {
                throw "curl 下载失败，退出代码：$LASTEXITCODE"
            }
        }
        else {
            $headers = @{
                Accept       = "application/octet-stream"
                "User-Agent" = "biliTickerBuy-installer"
            }

            $params = @{
                Uri                = $Url
                Headers            = $headers
                OutFile            = $partialPath
                UseBasicParsing    = $true
                TimeoutSec         = 60
                MaximumRedirection = 10
            }

            Invoke-WebRequest @params
        }

        if (-not (Test-Path -LiteralPath $partialPath -PathType Leaf)) {
            throw "下载完成后未找到临时文件。"
        }

        Move-Item -LiteralPath $partialPath -Destination $OutputPath -Force
        return $true
    }
    catch {
        Remove-Item -LiteralPath $partialPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue

        Write-ErrorMessage "下载失败：$Url"
        Write-ErrorMessage $_.Exception.Message

        return $false
    }
}

function Test-ValidZip {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ZipPath
    )

    if (-not (Test-Path -LiteralPath $ZipPath -PathType Leaf)) {
        return $false
    }

    $fileInfo = Get-Item -LiteralPath $ZipPath

    if ($fileInfo.Length -lt 4) {
        return $false
    }

    $stream = $null
    $archive = $null

    try {
        $stream = [System.IO.File]::Open(
            $ZipPath,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::Read
        )

        $signature = New-Object byte[] 4
        $readLength = $stream.Read($signature, 0, 4)

        if ($readLength -ne 4) {
            return $false
        }

        $signatureHex = (
            $signature |
                ForEach-Object { $_.ToString("x2") }
        ) -join ""

        if ($signatureHex -notin @(
            "504b0304",
            "504b0506",
            "504b0708"
        )) {
            return $false
        }

        $stream.Position = 0

        Add-Type -AssemblyName System.IO.Compression.FileSystem

        $archive = New-Object System.IO.Compression.ZipArchive(
            $stream,
            [System.IO.Compression.ZipArchiveMode]::Read,
            $false
        )

        $null = $archive.Entries.Count
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($null -ne $archive) {
            $archive.Dispose()
        }

        if ($null -ne $stream) {
            $stream.Dispose()
        }
    }
}

function Show-InvalidDownload {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DownloadedFile,

        [Parameter(Mandatory = $true)]
        [string]$SourceUrl
    )

    Write-ErrorMessage "下载到的文件不是有效 ZIP：$SourceUrl"

    if (-not (Test-Path -LiteralPath $DownloadedFile -PathType Leaf)) {
        return
    }

    $fileInfo = Get-Item -LiteralPath $DownloadedFile
    Write-ErrorMessage "文件大小：$($fileInfo.Length) 字节"

    try {
        $bytes = [System.IO.File]::ReadAllBytes($DownloadedFile)
        $previewLength = [Math]::Min(300, $bytes.Length)

        if ($previewLength -gt 0) {
            $preview = [System.Text.Encoding]::UTF8.GetString(
                $bytes,
                0,
                $previewLength
            )

            $preview = [regex]::Replace(
                $preview,
                "[\x00-\x08\x0B\x0C\x0E-\x1F]",
                " "
            )

            Write-ErrorMessage "响应内容开头："
            Write-ErrorMessage $preview
        }
    }
    catch {
        Write-ErrorMessage "无法读取响应内容预览。"
    }
}

function Get-VersionInfo {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DirectUrl,

        [AllowEmptyString()]
        [string]$Proxy
    )

    try {
        return Invoke-HttpText -Url $DirectUrl
    }
    catch {
        if ([string]::IsNullOrEmpty($Proxy)) {
            throw
        }

        Write-Info "版本信息直连失败，正在尝试代理..."

        $proxyUrl = Resolve-ProxyUrl `
            -OriginalUrl $DirectUrl `
            -Proxy $Proxy

        return Invoke-HttpText -Url $proxyUrl
    }
}

function Download-ReleaseAsset {
    param(
        [Parameter(Mandatory = $true)]
        [string]$AssetUrl,

        [Parameter(Mandatory = $true)]
        [string]$OutputPath,

        [AllowEmptyString()]
        [string]$Proxy
    )

    if (-not [string]::IsNullOrEmpty($Proxy)) {
        $proxyUrl = Resolve-ProxyUrl `
            -OriginalUrl $AssetUrl `
            -Proxy $Proxy

        Write-Info "正在通过代理下载..."
        Write-Info "下载地址：$proxyUrl"

        if (Invoke-HttpDownload -Url $proxyUrl -OutputPath $OutputPath) {
            if (Test-ValidZip -ZipPath $OutputPath) {
                return $true
            }

            Show-InvalidDownload `
                -DownloadedFile $OutputPath `
                -SourceUrl $proxyUrl
        }
        else {
            Write-ErrorMessage "[biliTickerBuy] 代理下载失败。"
        }

        Write-Info "代理未返回有效安装包，正在尝试直连..."

        Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath "$OutputPath.part" -Force -ErrorAction SilentlyContinue
    }

    Write-Info "正在直连 GitHub 下载..."
    Write-Info "下载地址：$AssetUrl"

    if (Invoke-HttpDownload -Url $AssetUrl -OutputPath $OutputPath) {
        if (Test-ValidZip -ZipPath $OutputPath) {
            return $true
        }

        Show-InvalidDownload `
            -DownloadedFile $OutputPath `
            -SourceUrl $AssetUrl
    }

    Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath "$OutputPath.part" -Force -ErrorAction SilentlyContinue

    return $false
}

function Test-SafeAssetName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$AssetName
    )

    if (-not $AssetName.EndsWith(
        ".zip",
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "安装包文件名不是 ZIP：$AssetName"
    }

    if (
        $AssetName.Contains("/") -or
        $AssetName.Contains("\") -or
        $AssetName -eq "." -or
        $AssetName -eq ".."
    ) {
        throw "version-info.json 中的文件名不安全：$AssetName"
    }
}

function Test-VersionTag {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    if ($Version -notmatch "^[0-9A-Za-z._+\-]+$") {
        throw "version-info.json 中的版本号格式无效：$Version"
    }
}

function Test-Sha256Text {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Sha256
    )

    if ($Sha256 -notmatch "^[0-9a-fA-F]{64}$") {
        throw "SHA256 格式无效：$Sha256"
    }
}

function Verify-DownloadedFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DownloadedFile,

        [Parameter(Mandatory = $true)]
        [long]$ExpectedSize,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedSha256
    )

    $actualSize = (Get-Item -LiteralPath $DownloadedFile).Length

    if ($actualSize -ne $ExpectedSize) {
        Write-ErrorMessage "安装包大小校验失败。"
        Write-ErrorMessage "预期大小：$ExpectedSize 字节"
        Write-ErrorMessage "实际大小：$actualSize 字节"

        return $false
    }

    $actualSha256 = (
        Get-FileHash `
            -LiteralPath $DownloadedFile `
            -Algorithm SHA256
    ).Hash.ToLowerInvariant()

    $expectedSha256Lower = $ExpectedSha256.ToLowerInvariant()

    if ($actualSha256 -ne $expectedSha256Lower) {
        Write-ErrorMessage "安装包 SHA256 校验失败。"
        Write-ErrorMessage "预期 SHA256：$expectedSha256Lower"
        Write-ErrorMessage "实际 SHA256：$actualSha256"

        return $false
    }

    return $true
}

function Find-PackageDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExtractDirectory
    )

    $rootBinary = Join-Path $ExtractDirectory "biliTickerBuy.exe"

    if (Test-Path -LiteralPath $rootBinary -PathType Leaf) {
        return $ExtractDirectory
    }

    $nestedDirectory = Join-Path $ExtractDirectory "biliTickerBuy"
    $nestedBinary = Join-Path $nestedDirectory "biliTickerBuy.exe"

    if (Test-Path -LiteralPath $nestedBinary -PathType Leaf) {
        return $nestedDirectory
    }

    $binary = Get-ChildItem `
        -LiteralPath $ExtractDirectory `
        -Filter "biliTickerBuy.exe" `
        -File `
        -Recurse |
        Select-Object -First 1

    if ($null -eq $binary) {
        throw "安装包内容不符合预期，未找到 biliTickerBuy.exe。"
    }

    return $binary.Directory.FullName
}

function Add-DirectoryToUserPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Directory
    )

    $normalizedDirectory = $Directory.TrimEnd("\")
    $userPath = [Environment]::GetEnvironmentVariable(
        "Path",
        [EnvironmentVariableTarget]::User
    )

    if ($null -eq $userPath) {
        $userPath = ""
    }

    $pathEntries = @(
        $userPath.Split(
            ";",
            [StringSplitOptions]::RemoveEmptyEntries
        ) |
            ForEach-Object { $_.Trim().TrimEnd("\") }
    )

    $alreadyExists = $false

    foreach ($entry in $pathEntries) {
        if (
            [string]::Equals(
                $entry,
                $normalizedDirectory,
                [StringComparison]::OrdinalIgnoreCase
            )
        ) {
            $alreadyExists = $true
            break
        }
    }

    if ($alreadyExists) {
        return $false
    }

    if ([string]::IsNullOrWhiteSpace($userPath)) {
        $newUserPath = $Directory
    }
    else {
        $newUserPath = $userPath.TrimEnd(";") + ";" + $Directory
    }

    [Environment]::SetEnvironmentVariable(
        "Path",
        $newUserPath,
        [EnvironmentVariableTarget]::User
    )

    return $true
}

function Show-NetworkHelp {
    Write-ErrorMessage "请根据网络情况禁用 GH_PROXY，或更换其他可用加速前缀。"
    Write-ErrorMessage ""
    Write-ErrorMessage "禁用代理："
    Write-ErrorMessage '  set "GH_PROXY="'
    Write-ErrorMessage "  install.bat"
    Write-ErrorMessage ""
    Write-ErrorMessage "指定代理："
    Write-ErrorMessage '  set "GH_PROXY=https://gh-proxy.org"'
    Write-ErrorMessage "  install.bat"
    Write-ErrorMessage ""
    Write-ErrorMessage "可用前缀可前往 https://ghproxy.link/ 查找。"
}

if ($NoProxy) {
    $GhProxy = ""
}
elseif (-not $PSBoundParameters.ContainsKey("GhProxy")) {
    $environmentProxy = Get-EnvironmentValue -Name "GH_PROXY"

    if ($null -eq $environmentProxy) {
        $GhProxy = "https://gh-proxy.org"
    }
    else {
        $GhProxy = $environmentProxy
    }
}

if ($PSBoundParameters.ContainsKey("InstallDir")) {
    $InstallDirectory = $InstallDir
}
else {
    $InstallDirectory = Get-EnvironmentValue -Name "INSTALL_DIR"
}

if ($PSBoundParameters.ContainsKey("BinDir")) {
    $BinDirectory = $BinDir
}
else {
    $BinDirectory = Get-EnvironmentValue -Name "BIN_DIR"
}

if ([string]::IsNullOrWhiteSpace($InstallDirectory)) {
    $InstallDirectory = Join-Path $env:LOCALAPPDATA "biliTickerBuy\app"
}

if ([string]::IsNullOrWhiteSpace($BinDirectory)) {
    $BinDirectory = Join-Path $env:LOCALAPPDATA "biliTickerBuy\bin"
}

$InstallDirectory = [System.IO.Path]::GetFullPath($InstallDirectory)
$BinDirectory = [System.IO.Path]::GetFullPath($BinDirectory)

$LauncherPath = Join-Path $BinDirectory "btb.cmd"

$VersionInfoUrl = (
    "https://github.com/" +
    $Repo +
    "/releases/latest/download/version-info.json"
)

$TempDirectory = Join-Path (
    [System.IO.Path]::GetTempPath()
) (
    "biliTickerBuy-install-" +
    [Guid]::NewGuid().ToString("N")
)

$ZipPath = Join-Path $TempDirectory "biliTickerBuy.zip"
$ExtractDirectory = Join-Path $TempDirectory "extract"

$InstallDirectoryNew = "$InstallDirectory.new"
$InstallDirectoryOld = "$InstallDirectory.old"
$LauncherNew = "$LauncherPath.new"

try {
    New-Item `
        -ItemType Directory `
        -Path $TempDirectory `
        -Force |
        Out-Null

    New-Item `
        -ItemType Directory `
        -Path $ExtractDirectory `
        -Force |
        Out-Null

    Write-Info "正在检查最新版本..."

    try {
        $versionInfoText = Get-VersionInfo `
            -DirectUrl $VersionInfoUrl `
            -Proxy $GhProxy
    }
    catch {
        Write-ErrorMessage "获取版本信息失败：$VersionInfoUrl"
        Write-ErrorMessage $_.Exception.Message

        Show-NetworkHelp
        exit 1
    }

    try {
        $versionInfo = $versionInfoText | ConvertFrom-Json
    }
    catch {
        throw "version-info.json 不是有效 JSON：$($_.Exception.Message)"
    }

    $releaseTag = [string]$versionInfo.version

    if ([string]::IsNullOrWhiteSpace($releaseTag)) {
        throw "version-info.json 中缺少 version 字段。"
    }

    Test-VersionTag -Version $releaseTag

    $platformInfo = $versionInfo.PSObject.Properties[$PlatformKey].Value

    if ($null -eq $platformInfo) {
        throw "version-info.json 中未找到平台：$PlatformKey"
    }

    $assetName = [string]$platformInfo.name
    $assetSha256 = [string]$platformInfo.sha256
    $assetSizeText = [string]$platformInfo.size

    if ([string]::IsNullOrWhiteSpace($assetName)) {
        throw "version-info.json 中缺少 $PlatformKey.name。"
    }

    if ([string]::IsNullOrWhiteSpace($assetSha256)) {
        throw "version-info.json 中缺少 $PlatformKey.sha256。"
    }

    if ([string]::IsNullOrWhiteSpace($assetSizeText)) {
        throw "version-info.json 中缺少 $PlatformKey.size。"
    }

    Test-SafeAssetName -AssetName $assetName
    Test-Sha256Text -Sha256 $assetSha256

    $assetSize = 0L

    if (-not [long]::TryParse($assetSizeText, [ref]$assetSize)) {
        throw "安装包大小格式无效：$assetSizeText"
    }

    if ($assetSize -le 0) {
        throw "安装包大小必须大于 0：$assetSize"
    }

    $assetUrl = (
        "https://github.com/" +
        $Repo +
        "/releases/download/" +
        $releaseTag +
        "/" +
        $assetName
    )

    Write-Info "最新版本：$releaseTag"
    Write-Info "当前平台：$PlatformKey"
    Write-Info "安装包：$assetName"
    Write-Info "预期大小：$assetSize 字节"

    if (
        -not (
            Download-ReleaseAsset `
                -AssetUrl $assetUrl `
                -OutputPath $ZipPath `
                -Proxy $GhProxy
        )
    ) {
        Write-ErrorMessage "安装包下载失败：$assetUrl"
        Show-NetworkHelp
        exit 1
    }

    Write-Info "正在校验安装包..."

    if (
        -not (
            Verify-DownloadedFile `
                -DownloadedFile $ZipPath `
                -ExpectedSize $assetSize `
                -ExpectedSha256 $assetSha256
        )
    ) {
        Remove-Item `
            -LiteralPath $ZipPath `
            -Force `
            -ErrorAction SilentlyContinue

        throw "安装包完整性校验失败，已删除下载文件。"
    }

    if (-not (Test-ValidZip -ZipPath $ZipPath)) {
        Remove-Item `
            -LiteralPath $ZipPath `
            -Force `
            -ErrorAction SilentlyContinue

        throw "下载到的文件不是有效 ZIP 安装包。"
    }

    Write-Info "安装包校验通过。"
    Write-Info "正在解压安装包..."

    Expand-Archive `
        -LiteralPath $ZipPath `
        -DestinationPath $ExtractDirectory `
        -Force

    $packageDirectory = Find-PackageDirectory `
        -ExtractDirectory $ExtractDirectory

    Write-Info "找到安装文件：$packageDirectory"

    $installParent = Split-Path `
        -Parent `
        -Path $InstallDirectory

    New-Item `
        -ItemType Directory `
        -Path $installParent `
        -Force |
        Out-Null

    New-Item `
        -ItemType Directory `
        -Path $BinDirectory `
        -Force |
        Out-Null

    Remove-Item `
        -LiteralPath $InstallDirectoryNew `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue

    Remove-Item `
        -LiteralPath $InstallDirectoryOld `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue

    New-Item `
        -ItemType Directory `
        -Path $InstallDirectoryNew `
        -Force |
        Out-Null

    Write-Info "正在复制安装文件..."

    Copy-Item `
        -Path (Join-Path $packageDirectory "*") `
        -Destination $InstallDirectoryNew `
        -Recurse `
        -Force

    $sourceHiddenFiles = Get-ChildItem `
        -LiteralPath $packageDirectory `
        -Force |
        Where-Object {
            $_.Name.StartsWith(".")
        }

    foreach ($hiddenFile in $sourceHiddenFiles) {
        Copy-Item `
            -LiteralPath $hiddenFile.FullName `
            -Destination $InstallDirectoryNew `
            -Recurse `
            -Force
    }

    $newBinary = Join-Path $InstallDirectoryNew "biliTickerBuy.exe"

    if (-not (Test-Path -LiteralPath $newBinary -PathType Leaf)) {
        throw "安装目录中缺少 biliTickerBuy.exe。"
    }

    [System.IO.File]::WriteAllText(
        (Join-Path $InstallDirectoryNew ".version"),
        $releaseTag + [Environment]::NewLine,
        (New-Object System.Text.UTF8Encoding($false))
    )

    if (Test-Path -LiteralPath $InstallDirectory) {
        Move-Item `
            -LiteralPath $InstallDirectory `
            -Destination $InstallDirectoryOld
    }

    try {
        Move-Item `
            -LiteralPath $InstallDirectoryNew `
            -Destination $InstallDirectory
    }
    catch {
        Remove-Item `
            -LiteralPath $InstallDirectoryNew `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue

        if (Test-Path -LiteralPath $InstallDirectoryOld) {
            try {
                Move-Item `
                    -LiteralPath $InstallDirectoryOld `
                    -Destination $InstallDirectory
            }
            catch {
                Write-ErrorMessage (
                    "警告：恢复旧安装目录失败：" +
                    $InstallDirectoryOld
                )
            }
        }

        throw "无法替换安装目录：$InstallDirectory"
    }

    Remove-Item `
        -LiteralPath $InstallDirectoryOld `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue

    Remove-Item `
        -LiteralPath $LauncherNew `
        -Force `
        -ErrorAction SilentlyContinue

    $launcherContent = @"
@echo off
"$InstallDirectory\biliTickerBuy.exe" %*
"@

    [System.IO.File]::WriteAllText(
        $LauncherNew,
        $launcherContent,
        [System.Text.Encoding]::ASCII
    )

    Move-Item `
        -LiteralPath $LauncherNew `
        -Destination $LauncherPath `
        -Force

    $pathUpdated = Add-DirectoryToUserPath `
        -Directory $BinDirectory

    Write-Info "安装完成：$InstallDirectory"
    Write-Info "当前版本：$releaseTag"
    Write-Info "启动命令：$LauncherPath"

    $currentProcessPathEntries = @(
        $env:Path.Split(
            ";",
            [StringSplitOptions]::RemoveEmptyEntries
        )
    )

    $isAvailableInCurrentPath = $false

    foreach ($entry in $currentProcessPathEntries) {
        if (
            [string]::Equals(
                $entry.Trim().TrimEnd("\"),
                $BinDirectory.TrimEnd("\"),
                [StringComparison]::OrdinalIgnoreCase
            )
        ) {
            $isAvailableInCurrentPath = $true
            break
        }
    }

    if ($pathUpdated -or -not $isAvailableInCurrentPath) {
        Write-Info "已将命令目录写入当前用户 PATH：$BinDirectory"
        Write-Host ""
        Write-Host "请重新打开 CMD 或 PowerShell，然后执行："
        Write-Host ""
        Write-Host "  btb"
        Write-Host ""
        Write-Host "当前终端也可以直接执行："
        Write-Host ""
        Write-Host "  `"$LauncherPath`""
    }
    else {
        Write-Host ""
        Write-Host "运行："
        Write-Host ""
        Write-Host "  btb"
    }

    exit 0
}
catch {
    Write-ErrorMessage ""
    Write-ErrorMessage "[biliTickerBuy] 安装失败。"
    Write-ErrorMessage $_.Exception.Message

    exit 1
}
finally {
    Remove-Item `
        -LiteralPath $TempDirectory `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue

    Remove-Item `
        -LiteralPath $LauncherNew `
        -Force `
        -ErrorAction SilentlyContinue
}
```
