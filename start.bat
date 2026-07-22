@echo off
echo Starting CivicPulse...
start "CivicPulse Backend" cmd /k "pixi run dev"
start "CivicPulse Frontend" cmd /k "pixi run frontend"
echo.
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
echo API Docs: http://localhost:8000/docs
