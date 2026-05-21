@echo off
setlocal enabledelayedexpansion
title Part-Out Cutter - Build Script

echo ============================================================
echo  Part-Out Cutter - PyInstaller Build Script
echo  Target: Windows 11 (64-bit)
echo ============================================================
echo.

:: ── Explicitly use 64-bit Python 3.13 ────────────────────────────────────────
set PYTHON=C:\Users\rnlwe\AppData\Local\Programs\Python\Python313\python.exe
set PIP=%PYTHON% -m pip
set PYINSTALLER=%PYTHON% -m PyInstaller

if not exist "%PYTHON%" (
    echo ERROR: 64-bit Python not found at:
    echo   %PYTHON%
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('"%PYTHON%" --version') do set PYVER=%%i
echo Using: %PYVER% (64-bit^)
echo Path:  %PYTHON%
echo.

:: ── Install / upgrade PyInstaller ────────────────────────────────────────────
echo [1/4] Installing PyInstaller...
%PIP% install --upgrade pyinstaller >nul 2>&1
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller.
    pause
    exit /b 1
)
echo       Done.
echo.

:: ── Locate rembg via temp file (avoids quoting issues with for /f) ───────────
echo [2/4] Locating rembg package data...
"%PYTHON%" -c "import rembg, os; print(os.path.dirname(rembg.__file__))" > "%TEMP%\rembg_path.txt" 2>nul
if errorlevel 1 (
    echo ERROR: Could not import rembg under 64-bit Python.
    echo Run: "%PYTHON%" -m pip install rembg
    pause
    exit /b 1
)
set /p REMBG_DIR=<"%TEMP%\rembg_path.txt"
del "%TEMP%\rembg_path.txt" >nul 2>&1

if "!REMBG_DIR!"=="" (
    echo ERROR: rembg path came back empty.
    pause
    exit /b 1
)
echo       Found rembg at: !REMBG_DIR!
echo.

:: ── Kill any running instance and clear old dist folder ─────────────────────
echo [3/4] Clearing previous build...
taskkill /f /im PartOutCutter.exe >nul 2>&1
timeout /t 1 /nobreak >nul
if exist "dist\PartOutCutter" (
    rd /s /q "dist\PartOutCutter" >nul 2>&1
)
echo       Done.
echo.

:: ── Run PyInstaller ───────────────────────────────────────────────────────────
echo [4/4] Building executable (this may take 2-5 minutes)...
echo.

%PYINSTALLER% ^
    --name "PartOutCutter" ^
    --windowed ^
    --onedir ^
    --clean ^
    --noconfirm ^
    --add-data "!REMBG_DIR!;rembg" ^
    --hidden-import "rembg" ^
    --hidden-import "rembg.bg" ^
    --hidden-import "rembg.session_base" ^
    --hidden-import "rembg.session_factory" ^
    --hidden-import "rembg.sessions" ^
    --hidden-import "rembg.sessions.u2net" ^
    --hidden-import "rembg.sessions.u2net_human_seg" ^
    --hidden-import "rembg.sessions.silueta" ^
    --hidden-import "rembg.sessions.isnet" ^
    --hidden-import "rembg.sessions.isnet_anime" ^
    --hidden-import "PIL" ^
    --hidden-import "PIL._tkinter_finder" ^
    --hidden-import "onnxruntime" ^
    --hidden-import "onnxruntime.capi" ^
    --hidden-import "onnxruntime.capi.onnxruntime_pybind11_state" ^
    --collect-all "onnxruntime" ^
    --collect-all "rembg" ^
    --collect-all "pooch" ^
    --collect-all "pymatting" ^
    --hidden-import "pooch" ^
    --hidden-import "pymatting" ^
    --hidden-import "pymatting.alpha.estimate_alpha_cf" ^
    --hidden-import "pymatting.foreground.estimate_foreground_ml" ^
    --hidden-import "pymatting.util.util" ^
    --copy-metadata "rembg" ^
    --copy-metadata "pymatting" ^
    --copy-metadata "pillow" ^
    --copy-metadata "numpy" ^
    --copy-metadata "onnxruntime" ^
    --copy-metadata "pooch" ^
    --copy-metadata "scipy" ^
    --copy-metadata "scikit-image" ^
    --copy-metadata "tqdm" ^
    app.py

if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed. See output above for details.
    pause
    exit /b 1
)

:: ── Done ─────────────────────────────────────────────────────────────────────
echo.
echo [5/5] Build complete.
echo.
echo ============================================================
echo  OUTPUT FOLDER:  dist\PartOutCutter\
echo ============================================================
echo.
echo  To share with your colleague:
echo    1. Zip the entire "dist\PartOutCutter" folder
echo    2. Send the zip - it is self-contained, no Python needed
echo.
echo  First run note:
echo    The app will download AI model weights (~170 MB) on first
echo    use and cache them in %%USERPROFILE%%\.u2net\
echo    An internet connection is needed for that first run only.
echo.
pause