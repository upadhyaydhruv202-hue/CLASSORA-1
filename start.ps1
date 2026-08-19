# Start CLASSORA without Streamlit: FastAPI on :8000 and Vite on :5173
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

Write-Host "Starting API at http://127.0.0.1:8000"
Start-Process -FilePath "python" -ArgumentList "-m","uvicorn","main:app","--reload","--port","8000" -WorkingDirectory $root

Set-Location (Join-Path $root "website")
if (-not (Test-Path "node_modules")) {
  npm install
}
Write-Host "Starting website at http://localhost:5173"
npm run dev
