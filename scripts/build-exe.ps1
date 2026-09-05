# Build the standalone Wipecord.exe with PyInstaller.
#
#   powershell -ExecutionPolicy Bypass -File scripts\build-exe.ps1
#
# Output: dist\Wipecord.exe  (single file, no console, our icon embedded).
# The exe carries the app icon, so it shows in Task Manager and Explorer.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

& $py -m PyInstaller --noconfirm --clean --windowed --onefile `
    --name Wipecord `
    --icon (Join-Path $root "assets\wipecord.ico") `
    --add-data "$(Join-Path $root 'assets\wipecord.ico');assets" `
    --add-data "$(Join-Path $root 'assets\wordmark.png');assets" `
    --collect-all customtkinter `
    (Join-Path $root "run.pyw")

Write-Host "`nBuilt: $(Join-Path $root 'dist\Wipecord.exe')"
