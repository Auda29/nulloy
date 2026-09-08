param(
    [Parameter(Mandatory = $true)][string]$ToolchainRoot,
    [string]$BuildDirectory,
    [ValidateSet('windows-x64', 'windows-qt6-x64')][string]$Preset = 'windows-x64',
    [switch]$Package
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if (-not $BuildDirectory) {
    $folder = if ($Preset -eq 'windows-qt6-x64') { '.phase3/build' } else { '.phase2/build' }
    $BuildDirectory = Join-Path $projectRoot $folder
}
$BuildDirectory = [IO.Path]::GetFullPath($BuildDirectory)
$nativeRoot = Join-Path $ToolchainRoot 'mingw64'
$nativeBin = Join-Path $nativeRoot 'bin'
$cmake = Join-Path $nativeBin 'cmake.exe'
$originalPath = $env:PATH
try {
    $env:PATH = "$nativeBin;$originalPath"
    & $cmake --preset $Preset -S $projectRoot -B $BuildDirectory "-DCMAKE_PREFIX_PATH=$nativeRoot"
    if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed' }
    & $cmake --build $BuildDirectory -j 4
    if ($LASTEXITCODE -ne 0) { throw 'CMake build failed' }
    & (Join-Path $nativeBin 'ctest.exe') --test-dir $BuildDirectory --output-on-failure
    $testExit = $LASTEXITCODE
    Get-ChildItem -LiteralPath $BuildDirectory -Filter '*-results.txt' | ForEach-Object { Get-Content -LiteralPath $_.FullName }
    if ($testExit -ne 0) { throw 'CTest failed; see logs above' }
    & (Join-Path $ToolchainRoot 'usr/bin/pacman.exe') -Q | Set-Content -LiteralPath (Join-Path $BuildDirectory 'toolchain.txt') -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw 'Cannot record toolchain versions' }
    if ($Package) {
        & (Join-Path $nativeBin 'python.exe') (Join-Path $PSScriptRoot 'package-windows.py') --prefix $nativeRoot --build $BuildDirectory --source $projectRoot
        if ($LASTEXITCODE -ne 0) { throw 'Package validation failed' }
        & (Join-Path $nativeBin 'python.exe') (Join-Path $PSScriptRoot 'verify-package.py') --prefix $nativeRoot --build $BuildDirectory
        if ($LASTEXITCODE -ne 0) { throw 'Extracted package runtime tests failed' }
    }
} finally {
    $env:PATH = $originalPath
}
