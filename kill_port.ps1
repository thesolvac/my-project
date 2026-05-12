$targetPids = @(16560, 16444, 10088, 18028, 24360, 9412)
foreach ($p in $targetPids) {
    try { Stop-Process -Id $p -Force -ErrorAction Stop; Write-Host "Killed $p" }
    catch { Write-Host "Could not kill $p" }
}
Start-Sleep -Seconds 1
$remaining = (Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue).OwningProcess | Sort-Object -Unique
Write-Host "Remaining on port 5000: $remaining"
