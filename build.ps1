# 一键打包：把源码打包成 Windows 桌面 EXE（PyInstaller）
# 用法：powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host '==> 安装运行依赖 ...'
python -m pip install -r requirements.txt pyinstaller

Write-Host '==> 开始打包（下载包管家智能搜索版-v17.spec）...'
python -m PyInstaller --noconfirm --clean "下载包管家智能搜索版-v17.spec"

$exe = Join-Path $root 'dist\下载包管家智能搜索版-v17.exe'
if (Test-Path $exe) {
    Write-Host ''
    Write-Host "打包成功: $exe"
    Write-Host '（绿色版，可直接发给用户双击运行；也可上传到 GitHub Releases 供下载）'
} else {
    Write-Host '打包可能未成功，请检查上方 PyInstaller 输出。' -ForegroundColor Red
    exit 1
}