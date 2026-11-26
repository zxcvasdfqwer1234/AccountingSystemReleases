
@echo off
title Accounting System Release Builder
cd /d "%~dp0"

echo =====================================
echo   ACCOUNTING SYSTEM RELEASE BUILDER
echo =====================================
echo.

python build.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED.
    pause
    exit /b 1
)

echo.
echo =====================================
echo   DONE
echo =====================================
pause
