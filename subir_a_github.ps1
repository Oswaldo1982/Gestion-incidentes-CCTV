[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "Sincronización GitHub - Sistema CCTV"

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "             SISTEMA CCTV - SUBIDA A GITHUB (ORIGIN MAIN)" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Directorio: $PSScriptRoot" -ForegroundColor Gray
Write-Host "1. Iniciando proceso de subida a GitHub..." -ForegroundColor Yellow
Write-Host "2. Si se abre tu navegador web o una ventana emergente, autoriza el acceso con tu cuenta de GitHub." -ForegroundColor Yellow
Write-Host ""
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location -Path $PSScriptRoot

Write-Host "Paso 1: Iniciando sesión de GitHub en el navegador web..." -ForegroundColor Cyan
git credential-manager github login --web

Write-Host ""
Write-Host "Paso 2: Subiendo cambios al repositorio remoto (origin main)..." -ForegroundColor Cyan
git push origin main

Write-Host ""
Write-Host "====================================================================" -ForegroundColor Cyan
if ($LASTEXITCODE -eq 0) {
    Write-Host "[ÉXITO] ¡Los cambios han sido subidos a GitHub correctamente!" -ForegroundColor Green
} else {
    Write-Host "[AVISO] La operación terminó con código: $LASTEXITCODE." -ForegroundColor Yellow
}
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Presiona cualquier tecla para cerrar esta ventana..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
