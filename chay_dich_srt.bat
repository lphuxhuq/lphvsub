@echo off
chcp 65001 >nul
title Gemini SRT Translator Pro - VoxDub Studio

cd /d "%~dp0"

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"

if not defined PY (
    echo.
    echo  [LOI] Khong tim thay Python. Hay chay cai_dat.bat truoc.
    echo.
    pause
    exit /b 1
)

if not exist ".env" (
    if exist ".env.example" copy ".env.example" ".env" >nul
)

echo.
echo  ============================================================
echo    Gemini SRT Translator Pro - VoxDub Studio
echo  ============================================================
echo.
echo  Dang mo trinh dich phu de Gemini tren trinh duyet...
echo.

%PY% -m autodub.tools.gemini_srt_ui
if errorlevel 1 (
    echo.
    echo  [LOI] Co su co xay ra khi chay trinh dich Gemini SRT.
    echo.
    pause
)
