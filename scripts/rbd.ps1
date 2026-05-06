#!/usr/bin/env pwsh
# rbd — rebuild and redeploy local stack (frontend + backend + worker)
$root = Split-Path $PSScriptRoot -Parent
$compose = "$root\docker-compose.build.yml"
$env_file = "$root\.env.local"

Write-Host "Stopping services..."
docker compose -f $compose --env-file $env_file stop frontend backend worker

Write-Host "Building images..."
docker compose -f $compose --env-file $env_file build frontend backend
if ($LASTEXITCODE -ne 0) { Write-Host "Build failed." -ForegroundColor Red; exit 1 }

Write-Host "Starting services..."
docker compose -f $compose --env-file $env_file up -d frontend backend worker

Write-Host "Waiting for backend health..."
$timeout = 30
$elapsed = 0
do {
    Start-Sleep -Seconds 2
    $elapsed += 2
    $health = docker inspect --format "{{.State.Health.Status}}" weaving_site_backend 2>$null
} while ($health -ne "healthy" -and $elapsed -lt $timeout)

if ($health -eq "healthy") {
    $resp = docker exec weaving_site_backend wget -qO- http://localhost:8000/health 2>$null
    Write-Host "Health: $resp" -ForegroundColor Green
} else {
    Write-Host "Backend did not become healthy within ${timeout}s" -ForegroundColor Yellow
}
