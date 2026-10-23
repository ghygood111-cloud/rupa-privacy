$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$Evidence = Join-Path $Root 'artifacts/windows_packaging_20261009'
$Distribution = Join-Path $Root 'dist/RUPA'
$Exe = Join-Path $Distribution 'RUPA.exe'
$GatePath = Join-Path $Evidence 'release_gui_acceptance.json'
if (-not (Test-Path -LiteralPath $GatePath)) { throw 'Final EXE GUI smoke acceptance is required' }
$Gate = Get-Content -LiteralPath $GatePath -Raw | ConvertFrom-Json
$ExeHash = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash
if ($Gate.status -ne 'PASS' -or $Gate.exe_sha256 -ne $ExeHash) { throw 'Release GUI acceptance does not match this EXE' }
$Teacher = Join-Path $Root 'artifacts/RUPA_Windows_0.1.0'
$Zip = Join-Path $Root 'RUPA_Windows_0.1.0_Evaluation.zip'
if ((Test-Path -LiteralPath $Teacher) -or (Test-Path -LiteralPath $Zip)) {
    throw 'Evaluation package already exists; preserve it and choose an explicitly reviewed new build'
}
Copy-Item -LiteralPath $Distribution -Destination $Teacher -Recurse
$allowed = @('RUPA.exe', '_internal', 'README_Quick_Start.html', 'NOTICE.txt')
$unknown = @(Get-ChildItem -LiteralPath $Teacher | Where-Object { $_.Name -notin $allowed })
if ($unknown.Count -gt 0) { throw 'Unexpected top-level file in teacher distribution' }
$bad = @(Get-ChildItem -LiteralPath $Teacher -Recurse -File | Where-Object {
    $_.Name -eq 'RUPA-debug.exe' -or $_.Extension -eq '.log' -or $_.Name -eq 'direct_url.json'
})
if ($bad.Count -gt 0) { throw 'Debug, development-log or installation-origin files detected' }
Compress-Archive -LiteralPath $Teacher -DestinationPath $Zip -CompressionLevel Optimal
$folderBytes = (Get-ChildItem -LiteralPath $Teacher -Recurse -File | Measure-Object Length -Sum).Sum
[PSCustomObject]@{
    folder=$Teacher; folder_bytes=$folderBytes; zip=$Zip; zip_bytes=(Get-Item -LiteralPath $Zip).Length
    exe_bytes=(Get-Item -LiteralPath $Exe).Length; exe_sha256=$ExeHash
    zip_sha256=(Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash
    python_free_clean_machine='NOT YET PERFORMED'
} | ConvertTo-Json | Tee-Object -FilePath (Join-Path $Evidence 'teacher_package_summary.json')
