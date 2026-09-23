param([switch]$BuildOnly, [string]$StagedPackage = '')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$buildRoot = Join-Path $projectRoot 'build'
$target = Join-Path $projectRoot 'dist\AI_System_Diagnostic'

function Assert-ChildPath([string]$Path, [string]$Parent) {
    $absolute = [IO.Path]::GetFullPath($Path)
    $prefix = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    if (-not $absolute.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside the intended build workspace: $absolute"
    }
    return $absolute
}

if (-not $StagedPackage) {
    $stamp = (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $stage = Assert-ChildPath (Join-Path $buildRoot "release_$stamp") $buildRoot
    New-Item -ItemType Directory -Path $stage | Out-Null
    & python -m PyInstaller --noconfirm --clean --windowed --onedir --name AI_System_Diagnostic `
        --icon (Join-Path $projectRoot 'assets\app-icon.ico') --distpath (Join-Path $stage 'dist') `
        --workpath (Join-Path $stage 'work') --specpath $stage `
        --additional-hooks-dir (Join-Path $PSScriptRoot 'pyinstaller_hooks') `
        --add-data "$(Join-Path $projectRoot 'ui\qml');ui\qml" `
        --add-data "$(Join-Path $projectRoot 'assets');assets" (Join-Path $projectRoot 'main.py')
    if ($LASTEXITCODE -ne 0) { throw 'Packaging failed; the current portable application was not modified.' }
    $StagedPackage = Join-Path $stage 'dist\AI_System_Diagnostic'
    foreach ($runtime in @('MSVCP140.dll','MSVCP140_1.dll','MSVCP140_2.dll','VCRUNTIME140.dll','VCRUNTIME140_1.dll')) {
        $source = Join-Path $StagedPackage "_internal\PySide6\$runtime"
        if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $StagedPackage '_internal') -Force }
    }
    foreach ($conflict in @('icuuc.dll','icudt78.dll')) {
        $conflictPath = Assert-ChildPath (Join-Path $StagedPackage "_internal\$conflict") $stage
        if (Test-Path -LiteralPath $conflictPath) { Remove-Item -LiteralPath $conflictPath }
    }
    foreach ($directory in @('data','logs','reports','config','knowledge')) {
        New-Item -ItemType Directory -Path (Join-Path $StagedPackage $directory) -Force | Out-Null
    }
    foreach ($directory in @('assets','knowledge','docs')) {
        $source = Join-Path $projectRoot $directory
        if (Test-Path -LiteralPath $source) {
            New-Item -ItemType Directory -Path (Join-Path $StagedPackage $directory) -Force | Out-Null
            Get-ChildItem -LiteralPath $source -Force | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $StagedPackage $directory) -Recurse -Force }
        }
    }
    Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination (Join-Path $StagedPackage 'README.txt')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'LICENSE') -Destination (Join-Path $StagedPackage 'LICENSE.txt')
    Copy-Item -LiteralPath (Join-Path $projectRoot '.env.example') -Destination (Join-Path $StagedPackage 'config\.env.example')
}
$StagedPackage = Assert-ChildPath $StagedPackage $buildRoot
$newExe = Join-Path $StagedPackage 'AI_System_Diagnostic.exe'
if (-not (Test-Path -LiteralPath $newExe)) { throw 'No staged executable was produced.' }
Write-Output "STAGED_PACKAGE=$StagedPackage"
if ($BuildOnly) { return }
$target = Assert-ChildPath $target (Join-Path $projectRoot 'dist')
$running = Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq (Join-Path $target 'AI_System_Diagnostic.exe') }
if ($running) { throw 'Close AI System Diagnostic, then rerun with -StagedPackage pointing to the staged package above. Existing data is unchanged.' }
if (Test-Path -LiteralPath $target) {
    foreach ($directory in @('data','logs','reports','config')) {
        $source = Join-Path $target $directory
        if (Test-Path -LiteralPath $source) {
            Get-ChildItem -LiteralPath $source -Force | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $StagedPackage $directory) -Recurse -Force }
        }
    }
    $backupRoot = Join-Path $projectRoot 'release_backups'
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $backup = Assert-ChildPath (Join-Path $backupRoot ('AI_System_Diagnostic_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))) $backupRoot
    Move-Item -LiteralPath $target -Destination $backup
    try { Move-Item -LiteralPath $StagedPackage -Destination $target }
    catch { Move-Item -LiteralPath $backup -Destination $target; throw }
    Write-Output "PREVIOUS_PACKAGE=$backup"
} else {
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Move-Item -LiteralPath $StagedPackage -Destination $target
}
Write-Output "Portable package ready: $(Join-Path $target 'AI_System_Diagnostic.exe')"
