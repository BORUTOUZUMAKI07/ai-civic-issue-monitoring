@echo off
echo 🚀 Starting AI Civic Issue Monitoring...

echo 📦 Starting Backend (FastAPI)...
start cmd /k "uv sync && uv run python src/app/main.py"

echo 🎨 Starting Frontend (Vite)...
cd frontend
start cmd /k "npm install && npm run dev"

echo ✅ Both services are starting in separate windows.
echo 🌐 Backend: http://localhost:8000/docs
echo 🌐 Frontend: Check the terminal for the Vite URL (usually http://localhost:5173)
