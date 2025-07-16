@echo off
cls

:: Build frontend
cd frontend
pyinstaller --noconfirm --log-level=DEBUG main.spec
cd ..

:: Build backend
cd backend
pyinstaller --noconfirm --log-level=DEBUG server.spec
cd ..

echo Build completed.
pause