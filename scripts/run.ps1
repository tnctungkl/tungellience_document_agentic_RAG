$ErrorActionPreference = "Stop"
$hostAddress = if ($env:API_HOST) { $env:API_HOST } else { "127.0.0.1" }
$port = if ($env:API_PORT) { $env:API_PORT } else { "8000" }

Write-Host "Starting Tungelligence on http://$hostAddress`:$port (local-only by default)."
python -m uvicorn app.api.main:app --host $hostAddress --port $port
