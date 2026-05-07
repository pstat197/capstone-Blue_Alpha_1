param(
    [string]$Tag = "google",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$demoDir = Join-Path $repoRoot "data\output\03_reports\report\$Tag"
$dashboardPath = Join-Path $demoDir "dashboard.html"

if (-not (Test-Path $dashboardPath)) {
    Write-Host "Dashboard not found: $dashboardPath" -ForegroundColor Red
    Write-Host "Generate it first:" -ForegroundColor Yellow
    Write-Host "python -m src.reporting.make_dashboard --input data/output/02_tables/$Tag/prior_sensitivity_report_input_$Tag.csv --outdir data/output/03_reports/report/$Tag --clean-output"
    exit 1
}

$url = "http://127.0.0.1:$Port/dashboard.html"
Write-Host "Serving demo folder: $demoDir" -ForegroundColor Cyan
Write-Host "Open in browser: $url" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop server." -ForegroundColor DarkGray

Start-Process $url | Out-Null

if (Get-Command python -ErrorAction SilentlyContinue) {
    python -m http.server $Port --directory $demoDir
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    py -m http.server $Port --directory $demoDir
} else {
    Write-Host "Python launcher not found. Open file directly: $dashboardPath" -ForegroundColor Yellow
    exit 1
}
