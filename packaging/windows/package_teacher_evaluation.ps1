$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$Evidence = Join-Path $Root 'artifacts/teacher_evaluation_20261010'
$Distribution = Join-Path $Root 'dist/RUPA-Evaluation'
$Exe = Join-Path $Distribution 'RUPA-Evaluation.exe'
$GatePath = Join-Path $Evidence 'evaluation_acceptance.json'
$Teacher = Join-Path $Root 'artifacts/RUPA_Teacher_Evaluation_0.1.0'
$Zip = Join-Path $Root 'artifacts/RUPA_Teacher_Evaluation_0.1.0.zip'

if (-not (Test-Path -LiteralPath $GatePath)) { throw 'Evaluation acceptance evidence is required before packaging' }
$Gate = Get-Content -LiteralPath $GatePath -Raw | ConvertFrom-Json
$ExeHash = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash
if ($Gate.status -ne 'PASS' -or $Gate.exe_sha256 -ne $ExeHash) {
    throw 'Evaluation acceptance does not match this EXE'
}
if ((Test-Path -LiteralPath $Teacher) -or (Test-Path -LiteralPath $Zip)) {
    throw 'Teacher Evaluation package already exists; refusing to overwrite it'
}

Copy-Item -LiteralPath $Distribution -Destination $Teacher -Recurse
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'teacher/START_HERE.html') -Destination $Teacher
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'teacher/REVIEW_FEEDBACK.md') -Destination $Teacher
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'teacher/NOTICE.txt') -Destination $Teacher

$allowed = @('RUPA-Evaluation.exe', '_internal', 'START_HERE.html', 'REVIEW_FEEDBACK.md', 'NOTICE.txt')
$unknown = @(Get-ChildItem -LiteralPath $Teacher | Where-Object { $_.Name -notin $allowed })
if ($unknown.Count -gt 0) { throw 'Unexpected top-level item in teacher package' }
$bad = @(Get-ChildItem -LiteralPath $Teacher -Recurse -Force | Where-Object {
    $_.Name -eq 'RUPA-debug.exe' -or $_.Extension -eq '.log' -or
    $_.Name -eq '.git' -or $_.Name -eq '.github' -or $_.Name -eq '.internal_audit' -or
    $_.Name -eq 'direct_url.json'
})
if ($bad.Count -gt 0) { throw 'A prohibited development, debug, log, or private-audit item was detected' }

Compress-Archive -LiteralPath $Teacher -DestinationPath $Zip -CompressionLevel Optimal
$folderBytes = (Get-ChildItem -LiteralPath $Teacher -Recurse -File | Measure-Object Length -Sum).Sum
[PSCustomObject]@{
    folder = $Teacher
    folder_bytes = $folderBytes
    zip = $Zip
    zip_bytes = (Get-Item -LiteralPath $Zip).Length
    exe = Join-Path $Teacher 'RUPA-Evaluation.exe'
    exe_bytes = (Get-Item -LiteralPath (Join-Path $Teacher 'RUPA-Evaluation.exe')).Length
    exe_sha256 = (Get-FileHash -LiteralPath (Join-Path $Teacher 'RUPA-Evaluation.exe') -Algorithm SHA256).Hash
    zip_sha256 = (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash
    python_free_clean_machine = 'NOT YET PERFORMED'
} | ConvertTo-Json | Tee-Object -FilePath (Join-Path $Evidence 'teacher_package_summary.json')
