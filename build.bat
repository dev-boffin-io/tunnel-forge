@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  TunnelForge - Windows Build Script
::  Usage:  build.bat [DEBUG=1]
:: ============================================================

set APP=tunnel-forge
set SRC=main.py
set ICON=assets\tunnel-forge.png
set BIN_DIR=bin
set VENV=.venv
set DEBUG=%1

echo.
echo  TunnelForge - Windows Build
echo ============================================================

:: ── Find Python ─────────────────────────────────────────────
set PYTHON=
for %%p in (python python3) do (
    if "!PYTHON!"=="" (
        %%p --version >nul 2>&1 && set PYTHON=%%p
    )
)
if "!PYTHON!"=="" (
    echo [ERR] Python not found. Install Python 3.10+ from https://python.org
    exit /b 1
)
for /f "tokens=*" %%v in ('!PYTHON! --version 2^>^&1') do echo [OK]  %%v

:: ── Create virtualenv ────────────────────────────────────────
if not exist "!VENV!\" (
    echo [..]  Creating virtual environment...
    !PYTHON! -m venv !VENV!
    if errorlevel 1 (
        echo [ERR] venv creation failed
        exit /b 1
    )
)

:: ── Install dependencies ─────────────────────────────────────
echo [..]  Installing dependencies...
"!VENV!\Scripts\pip.exe" install --quiet --upgrade pip
"!VENV!\Scripts\pip.exe" install --quiet ^
    pyinstaller ^
    PyQt6>=6.4.0 ^
    PyYAML>=6.0 ^
    psutil>=5.9.0 ^
    colorama>=0.4.6
if errorlevel 1 (
    echo [ERR] pip install failed
    exit /b 1
)
echo [OK]  Dependencies installed

:: ── Create output dir ────────────────────────────────────────
if not exist "!BIN_DIR!\" mkdir "!BIN_DIR!"

:: ── Build with PyInstaller ───────────────────────────────────
echo [..]  Building with PyInstaller...

set EXTRA=
if "!DEBUG!"=="DEBUG=1" set EXTRA=--log-level DEBUG

"!VENV!\Scripts\pyinstaller.exe" ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "!APP!" ^
    --distpath "!BIN_DIR!" ^
    --workpath ".build" ^
    --specpath ".spec" ^
    --add-data "assets;assets" ^
    --add-data "core;core" ^
    --add-data "gui;gui" ^
    --add-data "utils;utils" ^
    !EXTRA! ^
    "!SRC!"

if errorlevel 1 (
    echo.
    echo [ERR] PyInstaller build failed.
    exit /b 1
)

echo.
echo ============================================================
echo [OK]  Binary  : !BIN_DIR!\!APP!.exe
echo [!!]  Place cloudflared.exe in the same folder before running.
echo        Download: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/
echo ============================================================
echo.
