@echo off
cls

:: Build frontend
cd frontend
pyinstaller --noconfirm main.spec
cd ..

:: Build backend
cd backend
pyinstaller --noconfirm server.spec
cd ..

echo Build completed.
pause