@echo off
echo 🚀 Starting AI Civic Issue Monitoring...
echo 💡 Using hybrid Mamba + uv workflow

echo 📦 Starting Backend (FastAPI)...
start cmd /k "set PYTHONPATH=src && uv sync && uv run python src/app/main.py"

echo ⏳ Waiting for backend to warm up...
timeout /t 5 /nobreak > nul

echo 🎨 Starting Frontend (Vite)...
cd frontend
start cmd /k "npm install && npm run dev"

echo ✅ Both services are starting in separate windows.
echo 🌐 Backend: http://localhost:8000/docs
echo 🌐 Frontend: Check the terminal for the Vite URL (usually http://localhost:5173)
