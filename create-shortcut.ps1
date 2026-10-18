$ErrorActionPreference = 'Stop'
$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktop '下载包管家.lnk'
$script = Join-Path $appDir 'desktop.py'
$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
$pyw = (Get-Command pyw.exe -ErrorAction SilentlyContinue).Source
$ws = New-Object -ComObject WScript.Shell
$link = $ws.CreateShortcut($linkPath)
if ($pythonw) {
  # pythonw.exe 是窗口版解释器：双击快捷方式不会出现黑色命令行窗口
  $link.TargetPath = $pythonw
  $link.Arguments = '"' + $script + '"'
} elseif ($pyw) {
  $link.TargetPath = $pyw
  $link.Arguments = '-3 "' + $script + '"'
} else {
  Write-Warning '没找到 pythonw.exe / pyw.exe，改用 启动下载包管家桌面版.bat'
  $link.TargetPath = Join-Path $appDir '启动下载包管家桌面版.bat'
}
$link.WorkingDirectory = $appDir
$link.Description = 'Download Package Manager'
$link.IconLocation = $env:SystemRoot + '\System32\shell32.dll,45'
$link.Save()
Write-Output $linkPath
