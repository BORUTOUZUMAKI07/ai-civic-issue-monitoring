@echo off
echo ===================================
echo   CivicPulse - Pixi Setup
echo ===================================

where pixi >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Pixi not found. Install it from https://pixi.sh
    echo Run: powershell -c "irm https://pixi.sh/install.ps1 | iex"
    exit /b 1
)

echo Installing dependencies...
pixi install

echo Installing frontend dependencies...
cd frontend && npm install && cd ..

echo Setting up pre-commit hooks...
pixi run setup

echo.
echo Setup complete! Run 'pixi run dev' to start the backend.
