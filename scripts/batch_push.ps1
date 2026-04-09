#!/usr/bin/env pwsh
# batch_push.ps1 - Push commits in small batches to avoid GitHub size limits
param(
    [int]$BatchSize = 8,
    [int]$StartBatch = 0
)

Set-Location $PSScriptRoot\..

$commits = git --no-pager log --format="%H" origin/main..HEAD | ForEach-Object { $_ }
if (-not $commits) {
    Write-Host "Nothing to push - already up to date." -ForegroundColor Green
    exit 0
}
[Array]::Reverse($commits)

$total = $commits.Count
Write-Host "Total commits to push: $total  (batch size: $BatchSize)" -ForegroundColor Cyan

$batchNum = 0
for ($i = 0; $i -lt $total; $i += $BatchSize) {
    $batchNum++
    if ($batchNum -le $StartBatch) {
        Write-Host "Skipping batch $batchNum (already done)" -ForegroundColor DarkGray
        continue
    }

    $end = [Math]::Min($i + $BatchSize - 1, $total - 1)
    $hash = $commits[$end]
    $shortHash = $hash.Substring(0, 7)

    Write-Host ""
    Write-Host "=== Batch $batchNum : commits $($i+1)-$($end+1) / $total (up to $shortHash) ===" -ForegroundColor Yellow

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    git push origin "${hash}:refs/heads/main" 2>&1
    $sw.Stop()
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 0) {
        Write-Host "Batch $batchNum OK  ($([int]$sw.Elapsed.TotalSeconds)s)" -ForegroundColor Green
    } else {
        Write-Host "Batch $batchNum FAILED (exit $exitCode) - stopping." -ForegroundColor Red
        exit 1
    }

    # small pause between batches
    Start-Sleep -Seconds 3
}

Write-Host ""
Write-Host "All $batchNum batches pushed successfully!" -ForegroundColor Green

