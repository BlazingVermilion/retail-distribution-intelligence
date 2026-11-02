# Run from the repository root. Never publish a partial export as valid training input.
$ErrorActionPreference = 'Stop'
$dir = 'artifacts/store_tcn'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$tmp = Join-Path $dir ('weekly-' + [guid]::NewGuid() + '.partial.csv')
$dest = Join-Path $dir 'store_weekly.csv'
try {
    Get-Content -Raw warehouse/postgres/store_weekly_export.sql |
        docker compose exec -T postgres psql -X -q -v ON_ERROR_STOP=1 -U postgres -d retail_analytics |
        Out-File -Encoding utf8 -FilePath $tmp
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL export failed.' }
    $sample = @(Get-Content $tmp -TotalCount 2)
    if ($sample.Count -lt 2 -or $sample[0] -ne 'month,week,store,records,observed,bottles,control_records,control_bottles') {
        throw 'Missing export header or no store-week rows.'
    }
    Move-Item -Force $tmp $dest
    Write-Host "Ready: $dest"
} finally {
    if (Test-Path $tmp) { Remove-Item $tmp }
}
