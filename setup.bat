@echo off
echo 🛠️ Starting AI Civic Issue Monitoring - FIRST TIME SETUP...
echo 💡 This project uses a hybrid Mamba + uv workflow.

echo 🐍 1. Checking for Mamba/Conda...
mamba --version >nul 2>&1
if %errorlevel% neq 0 (
    conda --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo ⚠️  Mamba/Conda not found. Proceeding with standalone uv setup.
    ) else (
        echo ✅ Conda detected.
    )
) else (
    echo ✅ Mamba detected.
)

echo 📦 2. Checking for uv (Package Manager)...
uv --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 📥 Installing uv...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
) else (
    echo ✅ uv is already installed.
)

echo 🐍 3. Setting up Python environment...
uv sync

echo 🎨 3. Setting up Frontend dependencies...
cd frontend
call npm install
cd ..

echo 📦 4. Setting up DVC & Pulling Data/Models...
uv pip install dvc dvc-s3
call dvc pull

echo ✅ SETUP COMPLETE!
echo 🚀 You can now run the app by double-clicking 'start.bat'
pause
