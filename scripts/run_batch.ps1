$ErrorActionPreference = "Stop"
Set-Location "C:\Users\tigot\Documents\Github\book-editor"

. .\.env.ps1

$logDir = "data\interim\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ("batch_{0}.log" -f (Get-Date -Format "yyyy-MM-dd_HHmmss"))

python scripts\run_batch.py *>&1 | Tee-Object -FilePath $logFile
