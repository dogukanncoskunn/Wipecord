# Creates a Wipecord shortcut on the Desktop (and, with -StartMenu, in the
# Start Menu). The shortcut launches the app with pythonw.exe from the local
# venv, so no console window appears.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install-shortcut.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install-shortcut.ps1 -StartMenu

param([switch]$StartMenu)

$ErrorActionPreference = "Stop"
$root     = Split-Path -Parent $PSScriptRoot
$pythonw  = Join-Path $root ".venv\Scripts\pythonw.exe"
$launcher = Join-Path $root "run.pyw"
$icon     = Join-Path $root "assets\wipecord.ico"

if (-not (Test-Path $pythonw)) {
    throw "venv not found at $pythonw`nRun first:  python -m venv .venv ; .venv\Scripts\pip install -r requirements.txt"
}

function New-WipecordShortcut([string]$Path) {
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($Path)
    $sc.TargetPath       = $pythonw
    $sc.Arguments        = "`"$launcher`""
    $sc.WorkingDirectory = $root
    if (Test-Path $icon) { $sc.IconLocation = $icon }
    $sc.Description       = "Wipecord - local Discord message deleter"
    $sc.Save()
    Write-Host "Created: $Path"
}

New-WipecordShortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "Wipecord.lnk")

if ($StartMenu) {
    $programs = [Environment]::GetFolderPath("Programs")
    New-WipecordShortcut (Join-Path $programs "Wipecord.lnk")
}

Write-Host "Done. Double-click the Wipecord icon to launch."
