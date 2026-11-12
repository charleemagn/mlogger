param(
    [switch]$BundlePython,
    [string]$PythonVersion = "3.13.9",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$root = Split-Path -Parent $PSScriptRoot
if (-not $Output) { $Output = Join-Path $root "dist\MLogger" }
$build = Join-Path $PSScriptRoot "bin\Release"

dotnet build (Join-Path $PSScriptRoot "MLogger.Desktop.csproj") -c Release --nologo -v q
if ($LASTEXITCODE -ne 0) { throw "dotnet build failed" }

if (Test-Path $Output) {
    $existing = @(Get-ChildItem $Output -Force)
    if ($existing.Count -gt 0 -and -not (Test-Path (Join-Path $Output "MLogger.exe"))) {
        throw "Refusing to overwrite '$Output': it is not an MLogger build folder."
    }
    Remove-Item $Output -Recurse -Force
}
New-Item -ItemType Directory -Force $Output | Out-Null

foreach ($file in "MLogger.exe", "MLogger.exe.config", "Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll", "WebView2Loader.dll") {
    Copy-Item (Join-Path $build $file) $Output
}
Copy-Item (Join-Path $root "LICENSE") $Output

$app = Join-Path $Output "app"
New-Item -ItemType Directory $app | Out-Null
foreach ($item in "start.py", "LICENSE", "server", "ui", "monitor", "diagnostics", "importers", "i18n", "sdk", "demo") {
    Copy-Item (Join-Path $root $item) $app -Recurse
}
Get-ChildItem $app -Recurse -Directory -Force | Where-Object { $_.Name -eq "__pycache__" -or $_.Name -like "*.egg-info" } | Remove-Item -Recurse -Force

if ($BundlePython) {
    $archive = Join-Path ([IO.Path]::GetTempPath()) "python-$PythonVersion-embed-amd64.zip"
    $url = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
    Write-Host "Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing
    Expand-Archive -Path $archive -DestinationPath (Join-Path $Output "python") -Force
    Remove-Item $archive -Force
}

$zip = Join-Path (Split-Path -Parent $Output) "MLogger-win-x64.zip"
Add-Type -AssemblyName System.IO.Compression.FileSystem
for ($attempt = 1; ; $attempt++) {
    if (Test-Path $zip) { Remove-Item $zip -Force }
    try {
        [IO.Compression.ZipFile]::CreateFromDirectory($Output, $zip, [IO.Compression.CompressionLevel]::Optimal, $true)
        break
    }
    catch {
        if ($attempt -ge 5) { throw }
        Start-Sleep -Seconds 3
    }
}

$size = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "Folder:  $Output"
Write-Host "Archive: $zip ($size MB)"
if (-not $BundlePython) {
    Write-Host "Python is not bundled: the app will use the Python installed on the computer. Add -BundlePython for a self-contained build."
}
