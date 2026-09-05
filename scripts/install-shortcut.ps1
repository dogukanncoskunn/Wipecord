# Creates a Wipecord shortcut on the Desktop (and, with -StartMenu, in the
# Start Menu).
#
# If a built exe exists (dist\Wipecord.exe, from scripts\build-exe.ps1) the
# shortcut launches that, so Task Manager and Explorer show the app's own icon.
# Otherwise it falls back to running the source with pythonw.exe from the venv,
# which still has no console window.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install-shortcut.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install-shortcut.ps1 -StartMenu

param([switch]$StartMenu)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$exe  = Join-Path $root "dist\Wipecord.exe"
$icon = Join-Path $root "assets\wipecord.ico"

if (Test-Path $exe) {
    $target = $exe
    $arguments = ""
    $workdir = Split-Path -Parent $exe
    $iconLocation = $exe          # the exe carries the icon
} else {
    $pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
    if (-not (Test-Path $pythonw)) {
        throw "No build and no venv found.`nBuild the exe (scripts\build-exe.ps1) or set up the venv (python -m venv .venv ; .venv\Scripts\pip install -r requirements.txt)."
    }
    $target = $pythonw
    $arguments = "`"$(Join-Path $root 'run.pyw')`""
    $workdir = $root
    $iconLocation = $icon
}

function New-WipecordShortcut([string]$Path) {
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($Path)
    $sc.TargetPath       = $target
    $sc.Arguments        = $arguments
    $sc.WorkingDirectory = $workdir
    if (Test-Path $iconLocation) { $sc.IconLocation = $iconLocation }
    $sc.Description       = "Wipecord - local Discord message deleter"
    $sc.Save()
    Write-Host "Created: $Path  ->  $target"
}

New-WipecordShortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "Wipecord.lnk")

if ($StartMenu) {
    New-WipecordShortcut (Join-Path ([Environment]::GetFolderPath("Programs")) "Wipecord.lnk")
}

# Nudge Explorer to refresh cached shortcut icons.
try { & ie4uinit.exe -show } catch {}

Write-Host "Done. Double-click the Wipecord icon to launch."
