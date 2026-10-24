# Build the Windows onedir distribution.
# Usage (from anywhere):  powershell -ExecutionPolicy Bypass -File scripts/build.ps1
$ErrorActionPreference = "Continue"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$Python = $env:PYTHON
if (-not $Python) {
    $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $Python) {
    throw "Python 3.10+ was not found. Install it or set the PYTHON environment variable."
}
$PythonDir = Split-Path $Python -Parent
$env:PATH = "$PythonDir\Library\bin;$PythonDir\DLLs;$env:PATH"

Write-Host "[1/4] Compile"
& $Python -m compileall -q notebook_power_monitor
if ($LASTEXITCODE -ne 0) { throw "compileall failed" }

Write-Host "[2/4] Tests"
& $Python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "unit tests failed" }

Write-Host "[3/4] Icon"
& $Python scripts\generate_icon.py
if ($LASTEXITCODE -ne 0) { throw "icon generation failed" }

if (Test-Path (Join-Path $Root "dist")) {
    Remove-Item (Join-Path $Root "dist") -Recurse -Force
}

Write-Host "[4/4] PyInstaller"
$Args = @(
    "-m", "PyInstaller",
    "--noconfirm", "--clean", "--onedir", "--windowed",
    "--name", "NotebookPowerMonitor",
    "--icon", (Join-Path $Root "notebook_power_monitor\assets\app.ico"),
    "--manifest", (Join-Path $Root "packaging\windows\app.manifest"),
    "--version-file", (Join-Path $Root "packaging\windows\version_info.txt"),
    "--add-data", ((Join-Path $Root "notebook_power_monitor\assets") + ";assets"),
    "--hidden-import", "wmi",
    "--hidden-import", "pythoncom",
    "--hidden-import", "pywintypes",
    "--hidden-import", "win32com",
    "--hidden-import", "win32com.client",
    "--hidden-import", "pystray._win32",
    "--hidden-import", "uuid",
    "--paths", $Root,
    "--distpath", (Join-Path $Root "dist"),
    "--workpath", (Join-Path $Root "build"),
    "--specpath", (Join-Path $Root "build"),
    (Join-Path $Root "run.py")
)

# Some Python distributions need the Tcl/Tk/FFI DLLs copied explicitly.  Add
# them only when they exist so the script also works with a standard python.org
# installation where PyInstaller's own hooks are sufficient.
foreach ($name in @("tk86t.dll", "tcl86t.dll", "ffi.dll")) {
    $candidate = Join-Path $PythonDir "Library\bin\$name"
    if (Test-Path $candidate) {
        $Args += @("--add-binary", "$candidate;.")
    }
}

& $Python @Args
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

& $Python scripts\finalize_build.py
if ($LASTEXITCODE -ne 0) { throw "final rename failed" }
Write-Host ""
Write-Host "Build complete. EXE:"
Get-ChildItem (Join-Path $Root "dist") -Recurse -Filter "*.exe" |
    Select-Object -First 1 FullName, Length, LastWriteTime
