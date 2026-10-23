param([switch]$SkipInstall)

$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$Venv = Join-Path $Root '.venv-windows-build-20261009'
$Python = Join-Path $Venv 'Scripts/python.exe'
$Evidence = Join-Path $Root 'artifacts/teacher_evaluation_20261010'
$Work = Join-Path $Root 'build/windows-evaluation'
$DistParent = Join-Path $Root 'dist'
$Distribution = Join-Path $DistParent 'RUPA-Evaluation'
$Exe = Join-Path $Distribution 'RUPA-Evaluation.exe'

function Check-Exit([string]$Action) {
    if ($LASTEXITCODE -ne 0) { throw "$Action failed with exit code $LASTEXITCODE" }
}

function Reset-GeneratedDirectory([string]$Target, [string]$Parent) {
    $resolved = [IO.Path]::GetFullPath($Target)
    $allowed = [IO.Path]::GetFullPath($Parent).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing directory cleanup outside generated parent: $resolved"
    }
    if (Test-Path -LiteralPath $resolved) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Pinned Windows build environment is missing: $Venv"
}

New-Item -ItemType Directory -Path $Evidence -Force | Out-Null
Set-Location -LiteralPath $Root
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

Reset-GeneratedDirectory $Work (Join-Path $Root 'build')
Reset-GeneratedDirectory $Distribution $DistParent
$env:RUPA_BUILD_DEBUG = '0'
$env:RUPA_BUILD_NAME = 'RUPA-Evaluation'
$savedPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & $Python -m PyInstaller --noconfirm --clean --distpath $DistParent --workpath $Work (Join-Path $PSScriptRoot 'RUPA.spec') 2>&1 |
        Tee-Object -FilePath (Join-Path $Evidence 'evaluation_build.log')
} finally {
    $ErrorActionPreference = $savedPreference
    Remove-Item Env:RUPA_BUILD_NAME -ErrorAction SilentlyContinue
    Remove-Item Env:RUPA_BUILD_DEBUG -ErrorAction SilentlyContinue
}
Check-Exit 'PyInstaller Evaluation build'

if (-not (Test-Path -LiteralPath $Exe)) { throw 'Expected Evaluation EXE was not produced' }
& $Python (Join-Path $PSScriptRoot 'collect_licenses.py') (Join-Path $Distribution '_internal/third_party_licenses')
Check-Exit 'Collect component license texts'

$BundledApp = Join-Path $Distribution '_internal/demo/app.py'
if (-not (Test-Path -LiteralPath $BundledApp)) { throw 'Bundled demo/app.py is missing' }
$SourceAppHash = (Get-FileHash -LiteralPath (Join-Path $Root 'demo/app.py') -Algorithm SHA256).Hash
$BundledAppHash = (Get-FileHash -LiteralPath $BundledApp -Algorithm SHA256).Hash
if ($SourceAppHash -ne $BundledAppHash) { throw 'Bundled GUI does not match current demo/app.py' }

$bytes = (Get-ChildItem -LiteralPath $Distribution -Recurse -File | Measure-Object Length -Sum).Sum
[PSCustomObject]@{
    mode = 'Evaluation'
    path = $Exe
    exe_sha256 = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash
    exe_bytes = (Get-Item -LiteralPath $Exe).Length
    distribution_bytes = $bytes
    source_app_sha256 = $SourceAppHash
    bundled_app_sha256 = $BundledAppHash
} | ConvertTo-Json | Tee-Object -FilePath (Join-Path $Evidence 'evaluation_build_summary.json')
