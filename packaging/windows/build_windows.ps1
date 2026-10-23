param(
    [ValidateSet('Debug','Release')][string]$Mode = 'Debug',
    [switch]$SkipInstall
)
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$Venv = Join-Path $Root '.venv-windows-build-20261009'
$Python = Join-Path $Venv 'Scripts/python.exe'
$Evidence = Join-Path $Root 'artifacts/windows_packaging_20261009'
New-Item -ItemType Directory -Path $Evidence -Force | Out-Null
Set-Location -LiteralPath $Root

function Check-Exit([string]$Action) {
    if ($LASTEXITCODE -ne 0) { throw "$Action failed with exit code $LASTEXITCODE" }
}
function Reset-GeneratedDirectory([string]$Target, [string]$Parent) {
    $resolved = [IO.Path]::GetFullPath($Target)
    $allowed = [IO.Path]::GetFullPath($Parent).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing directory cleanup outside generated parent: $resolved"
    }
    if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}
if (-not (Test-Path -LiteralPath $Python)) {
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3.9 -m venv $Venv }
    else { & python -m venv $Venv }
    Check-Exit 'Create build virtual environment'
}
& $Python -c "import sys,struct; assert sys.version_info[:3]==(3,9,13) and struct.calcsize('P')==8, 'Build requires CPython 3.9.13 x64'"
Check-Exit 'Reference interpreter check'
if (-not $SkipInstall) {
    & $Python -m pip install -r (Join-Path $PSScriptRoot 'requirements-build.txt')
    Check-Exit 'Install pinned build dependencies'
    & $Python -m pip install --no-build-isolation --no-deps .
    Check-Exit 'Install current RUPA source'
}
& $Python -m pip freeze | Out-File -LiteralPath (Join-Path $Evidence 'build_environment.txt') -Encoding utf8
& $Python -c "import numpy,pandas,scipy,sklearn; assert (numpy.__version__,pandas.__version__,scipy.__version__,sklearn.__version__)==('1.26.4','1.4.4','1.13.1','1.6.1')"
Check-Exit 'Scientific dependency version check'
if ($Mode -eq 'Release') {
    $gate = Join-Path $Evidence 'debug_gui_acceptance.json'
    if (-not (Test-Path -LiteralPath $gate)) { throw 'Run and record debug GUI acceptance before release build' }
    $decision = Get-Content -LiteralPath $gate -Raw | ConvertFrom-Json
    $debug = Join-Path $Root 'dist/RUPA-debug/RUPA-debug.exe'
    if ($decision.status -ne 'PASS' -or (Get-FileHash -LiteralPath $debug -Algorithm SHA256).Hash -ne $decision.exe_sha256) {
        throw 'Debug GUI acceptance is missing or does not match this debug EXE'
    }
}
$Name = if ($Mode -eq 'Debug') { 'RUPA-debug' } else { 'RUPA' }
$Work = Join-Path $Root ('build/windows-' + $Mode.ToLowerInvariant())
$DistParent = Join-Path $Root 'dist'
$Distribution = Join-Path $DistParent $Name
Reset-GeneratedDirectory $Work (Join-Path $Root 'build')
Reset-GeneratedDirectory $Distribution $DistParent
$env:RUPA_BUILD_DEBUG = if ($Mode -eq 'Debug') { '1' } else { '0' }
$savedPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    # Windows PowerShell 5 treats native stderr INFO lines as ErrorRecords.
    & $Python -m PyInstaller --noconfirm --clean --distpath $DistParent --workpath $Work (Join-Path $PSScriptRoot 'RUPA.spec') 2>&1 |
        Tee-Object -FilePath (Join-Path $Evidence ($Mode.ToLowerInvariant() + '_build.log'))
} finally { $ErrorActionPreference = $savedPreference }
Check-Exit 'PyInstaller'
$exe = Join-Path $Distribution ($Name + '.exe')
if (-not (Test-Path -LiteralPath $exe)) { throw 'Expected EXE was not produced' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README_Quick_Start.html'),(Join-Path $PSScriptRoot 'NOTICE.txt') -Destination $Distribution
& $Python (Join-Path $PSScriptRoot 'collect_licenses.py') (Join-Path $Distribution '_internal/third_party_licenses')
Check-Exit 'Collect component license texts'
$bytes = (Get-ChildItem -LiteralPath $Distribution -Recurse -File | Measure-Object Length -Sum).Sum
[PSCustomObject]@{
    mode=$Mode; path=$exe; exe_sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
    distribution_bytes=$bytes; size_mib=[Math]::Round($bytes/1MB,2)
} | ConvertTo-Json | Tee-Object -FilePath (Join-Path $Evidence ($Mode.ToLowerInvariant() + '_build_summary.json'))
