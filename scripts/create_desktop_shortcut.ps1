$ErrorActionPreference = "Stop"

$repoPath = Split-Path -Parent $PSScriptRoot
$targetPath = Join-Path $repoPath "launch_web_ui.bat"
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "Research Hub.lnk"

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = $repoPath
$shortcut.WindowStyle = 1
$shortcut.Description = "Open local Research Hub web interface"
$shortcut.Save()

Write-Host "Shortcut created: $shortcutPath"

