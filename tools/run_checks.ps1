# Run every check and leave readable reports under _artifacts/reports/.
# Usage from the repo root:   .\tools\run_checks.ps1

$ErrorActionPreference = "Continue"
$py = ".\.venv\Scripts\python.exe"
$reports = "_artifacts\reports"
New-Item -ItemType Directory -Force $reports | Out-Null

Write-Host "=== tests ===" -ForegroundColor Cyan
& $py -m pytest tests/ -v `
    --html="$reports\tests.html" --self-contained-html `
    --junitxml="$reports\tests.xml"
$testsOk = $?

Write-Host ""
Write-Host "=== lint ===" -ForegroundColor Cyan
& $py -m ruff check src/ tools/ | Tee-Object -FilePath "$reports\lint.txt"

Write-Host ""
Write-Host "=== demo artefacts ===" -ForegroundColor Cyan
& $py tools\make_demo.py | Tee-Object -FilePath "$reports\demo.txt"

Write-Host ""
Write-Host "reports written to $reports" -ForegroundColor Green
Write-Host "  tests.html    - open in a browser, every test with pass/fail"
Write-Host "  tests.xml     - JUnit XML for CI"
Write-Host "  lint.txt      - ruff output"
Write-Host "  demo.txt      - what the demo run printed"
if (-not $testsOk) { exit 1 }
