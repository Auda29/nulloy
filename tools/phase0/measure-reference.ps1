param(
    [Parameter(Mandatory = $true)][string]$RunName,
    [switch]$ColdWaveform
)

# Measures the existing private reference copy, never the installed original.
$ErrorActionPreference = 'Stop'
if ($RunName -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Invalid run name' }
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$reference = Join-Path $repo '.phase0\reference\installed-0.9.9'
$exe = Join-Path $reference 'Nulloy.exe'
$cache = Join-Path $reference 'Nulloy.peaks'
$log = Join-Path $repo ".phase0\logs\timing-$RunName.json"
if (Test-Path -LiteralPath $log) { throw 'Run log already exists' }
if (Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $exe }) {
    throw 'Close the reference copy before measuring'
}
if ($ColdWaveform -and (Test-Path -LiteralPath $cache)) {
    $archive = Join-Path $repo ".phase0\private\peaks-before-$RunName.bin"
    if (Test-Path -LiteralPath $archive) { throw 'Cache backup already exists' }
    Move-Item -LiteralPath $cache -Destination $archive
}
$watch = [Diagnostics.Stopwatch]::StartNew()
$startedUtc = [DateTime]::UtcNow
$process = Start-Process -FilePath $exe -WorkingDirectory $reference -PassThru
$idle = $process.WaitForInputIdle(10000)
$idleMs = $watch.Elapsed.TotalMilliseconds
$cacheReadyMs = $null
if ($ColdWaveform) {
    while ($watch.Elapsed.TotalSeconds -lt 30 -and !$process.HasExited) {
        if (Test-Path -LiteralPath $cache) {
            try {
                $bytes = [IO.File]::ReadAllBytes($cache)
                if ($bytes.Length -gt 8) { $cacheReadyMs = $watch.Elapsed.TotalMilliseconds; break }
            } catch [IO.IOException] { }
        }
        Start-Sleep -Milliseconds 20
    }
}
$record = [ordered]@{
    RunName = $RunName
    ColdNulloyWaveformCache = [bool]$ColdWaveform
    OSFileCacheCleared = $false
    StartIssuedUtc = $startedUtc.ToString('o')
    ProcessId = $process.Id
    InputIdle = $idle
    StartToInputIdleMs = $idleMs
    StartToNonemptyPeaksFileMs = $cacheReadyMs
    ExitUtc = $null
    Note = 'InputIdle is not first paint. Peaks-file timing is a cache-completion proxy, not a rendered-frame timestamp. Close through the normal UI within 60 seconds.'
}
$record | ConvertTo-Json | Set-Content -LiteralPath $log
Write-Output ($record | ConvertTo-Json)
if ($process.WaitForExit(60000)) {
    $record.ExitUtc = $process.ExitTime.ToUniversalTime().ToString('o')
    $record | ConvertTo-Json | Set-Content -LiteralPath $log
} else {
    Write-Output 'Observation ended; reference copy remains running.'
}
