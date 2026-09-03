@echo off
chcp 65001 >nul
title VoxDub - Cai them AI Subtitle Remover (LaMa ONNX)
cd /d "%~dp0"

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"

if not defined PY (
    echo [LOI] Khong tim thay Python.
    pause
    exit /b 1
)

echo ============================================================
echo   CAI DAT MO HINH AI XOA PHU DE (LAMA ONNX)
echo ============================================================
echo.
%PY% scripts\setup_inpaint.py

echo.
pause
