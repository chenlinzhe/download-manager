$ErrorActionPreference = 'Stop'
$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktop '下载包管家.lnk'
$ws = New-Object -ComObject WScript.Shell
$link = $ws.CreateShortcut($linkPath)
$link.TargetPath = Join-Path $appDir '启动下载包管家桌面版.bat'
$link.WorkingDirectory = $appDir
$link.Description = 'Download Package Manager'
$link.IconLocation = $env:SystemRoot + '\System32\shell32.dll,45'
$link.Save()
Write-Output $linkPath