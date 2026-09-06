param(
    [Parameter(Mandatory = $true)][string]$ToolchainRoot,
    [string]$BuildDirectory,
    [string]$ReferenceSkinDirectory = '',
    [ValidateSet('windows', 'offscreen')][string]$Platform = 'windows',
    [string]$TestFont = 'C:/Windows/Fonts/arial.ttf'
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if (-not $BuildDirectory) { $BuildDirectory = Join-Path $projectRoot '.phase1/build' }
$nativeRoot = Join-Path $ToolchainRoot 'mingw64'
$nativeBin = Join-Path $nativeRoot 'bin'
$cmake = Join-Path $nativeBin 'cmake.exe'
$ctest = Join-Path $nativeBin 'ctest.exe'
if (-not (Test-Path -LiteralPath $cmake)) { throw "Missing CMake in $nativeBin" }
$originalPath = $env:PATH
try {
    $env:PATH = "$nativeBin;$originalPath"
    & $cmake -S (Join-Path $projectRoot 'experiments/qt6-skins') -B $BuildDirectory -G Ninja `
        -DCMAKE_BUILD_TYPE=Debug "-DCMAKE_PREFIX_PATH=$nativeRoot" `
        "-DSKIN_TEST_PLATFORM=$Platform" "-DSKIN_REFERENCE_DIR=$ReferenceSkinDirectory" `
        "-DSKIN_TEST_FONT=$TestFont"
    if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed' }
    & $cmake --build $BuildDirectory -j 4
    if ($LASTEXITCODE -ne 0) { throw 'Prototype compilation failed' }
    & $ctest --test-dir $BuildDirectory --output-on-failure
    $testExit = $LASTEXITCODE
    foreach ($name in @('bridge', 'resource', 'runtime', 'drop')) {
        $result = Join-Path $BuildDirectory "$name-results.txt"
        if (Test-Path -LiteralPath $result) { Get-Content -LiteralPath $result }
    }
    if ($testExit -ne 0) { throw 'Prototype tests failed; see result files above' }
} finally {
    $env:PATH = $originalPath
}
