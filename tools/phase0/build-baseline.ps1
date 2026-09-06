param(
    [Parameter(Mandatory = $true)][string]$MsysRoot,
    [Parameter(Mandatory = $true)][string]$StageRoot,
    [string]$SevenZip = 'C:\Program Files\7-Zip\7z.exe',
    [string]$Revision = 'f4eddff8be2538526f3019f57f56c68db3c8c267'
)

# Phase-0 harness, not the future production build system.
# Exports upstream into a NEW directory and leaves tracked application code untouched.
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$stage = [IO.Path]::GetFullPath($StageRoot)
$msys = [IO.Path]::GetFullPath($MsysRoot)
$stageUnix = $stage.Replace('\', '/')
if ($stageUnix -notmatch '^[A-Za-z]:/[A-Za-z0-9_./-]+$') {
    throw 'Use a staging directory without spaces or shell metacharacters.'
}
if (Test-Path -LiteralPath $stage) {
    throw 'StageRoot must not exist. Existing build directories are never deleted.'
}
$bin = Join-Path $msys 'mingw64\bin'
foreach ($file in @("$bin\qmake-qt5.exe", "$bin\lrelease-qt5.exe",
                     "$bin\magick.exe", "$msys\usr\bin\bash.exe", $SevenZip)) {
    if (!(Test-Path -LiteralPath $file)) { throw "Required tool missing: $file" }
}

$oldPath = $env:PATH
$oldMsystem = $env:MSYSTEM
$oldChere = $env:CHERE_INVOKING
try {
    $env:PATH = "$bin;$msys\usr\bin;$(Split-Path $SevenZip);$oldPath"
    $env:MSYSTEM = 'MINGW64'
    $env:CHERE_INVOKING = '1'
    New-Item -ItemType Directory -Path $stage | Out-Null
    & git -c "safe.directory=$repo" -C $repo archive --format=tar "--output=$stage\source.tar" $Revision
    if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }
    & "$env:SystemRoot\System32\tar.exe" -xf "$stage\source.tar" -C $stage
    if ($LASTEXITCODE -ne 0) { throw 'Source extraction failed' }
    New-Item -ItemType Directory -Path "$stage\tmp", "$stage\Skins", "$stage\i18n" | Out-Null

    # Equivalent to configure --tests, with native paths for native qmake/moc.
    # Forced include works around upstream actionManager.cpp's missing Windows include.
    $cache = @"
PROJECT_DIR = $stageUnix
SRC_DIR = $stageUnix/src
TMP_DIR = $stageUnix/tmp
OBJECTS_DIR = $stageUnix/tmp
MOC_DIR = $stageUnix/tmp
RCC_DIR = $stageUnix/tmp
UI_DIR = $stageUnix/tmp
LRELEASE = lrelease-qt5
PKG_CONFIG = pkg-config
CONFIG += release unix_mingw gstreamer taglib tests
DEFINES += _TESTS_
APP_NAME = Nulloy
PREFIX = /usr
LIBDIR = lib
N_CONFIG_SUCCESS = yes
"@
    [IO.File]::WriteAllText("$stage\.qmake.cache", $cache, [Text.UTF8Encoding]::new($false))
    Push-Location $stage
    try {
        # Let qmake inspect the compiler before injecting a Qt-dependent header.
        & "$bin\qmake-qt5.exe" *> "$stage\qmake-initial.log"
        if ($LASTEXITCODE -ne 0) { throw "Compiler probe failed; see $stage\qmake-initial.log" }
        # Compiler/moc probes have no Qt include directories; inject only into real compilations.
        $header = "#if __has_include(<QIcon>)`n#include `"$stageUnix/src/platform/winIcon.h`"`n#endif`n"
        [IO.File]::WriteAllText("$stage\tmp\phase0-winicon.h", $header, [Text.UTF8Encoding]::new($false))
        Add-Content -LiteralPath "$stage\.qmake.cache" -Value "`nQMAKE_CXXFLAGS += -include $stageUnix/tmp/phase0-winicon.h"
        & "$bin\qmake-qt5.exe" -r *> "$stage\qmake.log"
        if ($LASTEXITCODE -ne 0) { throw "qmake failed; see $stage\qmake.log" }

        # Upstream's system() resource commands mix cmd.exe and Unix shell syntax.
        # Generate the same resources explicitly, keeping the forms/scripts/images intact.
        foreach ($skin in @('Metro', 'Silver', 'Slim')) {
            & $SevenZip a -tzip "$stage\Skins\$skin.nzs" "$stage\src\skins\$($skin.ToLower())\*" '-x!design.svg' *> "$stage\skin-$skin.log"
            if ($LASTEXITCODE -ne 0) { throw "Skin packaging failed: $skin" }
        }
        foreach ($ts in Get-ChildItem "$stage\src\i18n" -Filter '*.ts') {
            & "$bin\lrelease-qt5.exe" $ts.FullName -qm "$stage\i18n\$($ts.BaseName).qm" >> "$stage\translations.log"
            if ($LASTEXITCODE -ne 0) { throw "Translation failed: $($ts.Name)" }
        }
        & "$bin\magick.exe" "$stage\src\icons\icon.svg" -define icon:auto-resize "$stage\tmp\icon.ico"
        if ($LASTEXITCODE -ne 0) { throw 'Main icon generation failed; check librsvg' }
        & "$bin\magick.exe" composite '(' "$stage\src\icons\icon.svg" -resize '50%' -gravity center ')' "$stage\src\icons\file.svg" -define icon:auto-resize "$stage\tmp\file.ico"
        if ($LASTEXITCODE -ne 0) { throw 'File icon generation failed' }

        $shellCommand = "cd '$stageUnix' && mingw32-make -j4"
        & "$msys\usr\bin\bash.exe" -lc $shellCommand *> "$stage\build.log"
        if ($LASTEXITCODE -ne 0) { throw "Build failed; see $stage\build.log" }
        foreach ($exe in @('Nulloy.exe', 'testTrackInfoReader.exe', 'testPlaylistWidget.exe')) {
            if (!(Test-Path -LiteralPath "$stage\$exe")) { throw "Missing output: $exe" }
        }
        & "$msys\usr\bin\bash.exe" -lc 'pacman -Q' > "$stage\packages.lock.txt"
        Write-Output "Built upstream $Revision in $stage"
        Write-Output 'The GStreamer plugin uses fakesink for tests. This is not a normal playback package.'
    } finally {
        Pop-Location
    }
} finally {
    $env:PATH = $oldPath
    $env:MSYSTEM = $oldMsystem
    $env:CHERE_INVOKING = $oldChere
}
