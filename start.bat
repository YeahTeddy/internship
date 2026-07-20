@echo off
echo ============================================
echo   RSOD Agent Platform - Start All
echo ============================================
echo.

echo [1/3] Starting Docker services...
docker compose up -d
timeout /t 5 /nobreak >nul
echo     PostgreSQL + Redis + MinIO started

echo [2/3] Starting backend (background)...
cd backend
start /b .venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
cd ..

echo [3/3] Starting frontend (foreground)...
cd frontend
echo.
echo ============================================
echo   All services started!
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo   MinIO:    http://localhost:9001
echo ============================================
echo.
npm run dev
cd ..
