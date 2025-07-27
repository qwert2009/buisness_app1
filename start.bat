
@echo off
REM Скрипт запуска Business Manager Premium+ (ASCII only)
chcp 65001 >nul
title Business Manager Premium+ - Start
echo ------------------------------------------------------------
echo BUSINESS MANAGER PREMIUM+ - FINAL START
echo ------------------------------------------------------------
echo  Auto server selection and stable launch
echo  Browser will open automatically after start
echo  If errors occur, you will see detailed hints
echo ------------------------------------------------------------
REM Change to script directory
cd /d "%~dp0"
echo Working directory: %CD%
REM Python check
echo Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed!
    echo Download Python from https://python.org
    echo When installing, check "Add Python to PATH"
    pause
    exit /b 1
)
echo Python found
REM Main file check
echo Checking files...
if not exist "enhanced_app.py" (
    echo File enhanced_app.py not found!
    echo Make sure you are in the correct directory
    pause
    exit /b 1
)
echo enhanced_app.py found
REM Create required directories
if not exist "logs" mkdir logs
if not exist "backups" mkdir backups
if not exist "uploads" mkdir uploads
if not exist "exports" mkdir exports
if not exist "static" mkdir static
echo Directories created
REM Reliable dependency install (up to 3 tries)
set /a DEP_TRY=0
:install_deps
set /a DEP_TRY+=1
if exist "requirements.txt" (
    echo Installing dependencies (try %DEP_TRY%)...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        if %DEP_TRY% lss 3 (
            echo Dependency install failed, retrying...
            goto install_deps
        ) else (
            echo Dependency install failed after 3 tries, continuing...
        )
    ) else (
        echo Dependencies installed
    )
)
echo ------------------------------------------------------------
echo Starting Business Manager Premium+...
echo Please wait, initializing system...
echo ------------------------------------------------------------
REM Parse command line args
if "%1"=="--simple" set MODE=simple
if "%1"=="--auto" set MODE=auto
if "%1"=="--help" goto show_help
if not defined MODE set MODE=auto
REM Launch via auto_launcher.py and get port
for /f "delims=" %%P in ('python auto_launcher.py %MODE% 2^>nul') do set "LAUNCH_OUT=%%P"
echo %LAUNCH_OUT% | findstr /C:"http://localhost:" >nul
if %errorlevel%==0 (
    for /f "tokens=2 delims=: " %%A in ("%LAUNCH_OUT%") do set "PORT=%%A"
    set "PORT=%PORT: =%"
    echo Opening in browser: http://localhost:%PORT%
    start "" "http://localhost:%PORT%"
    goto end
) else (
    echo Error launching via auto_launcher.py
    echo %LAUNCH_OUT%
    goto end
)
:show_help
echo Usage:
echo   start.bat                 # Auto mode (default)
echo   start.bat --auto          # Auto mode
echo   start.bat --simple        # Simple mode
echo   start.bat --help          # This help
pause
exit /b 0
:end
echo.
echo Business Manager Premium+ finished
echo Thank you for using!
pause

