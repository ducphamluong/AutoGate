@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

REM Download PublicVPNList .ovpn into .\ovpn-list
REM NEVER deletes ovpn-list folder or existing files (append/overwrite by name only)
REM Usage:
REM   .\download_publicvpnlist.bat
REM   .\download_publicvpnlist.bat JP 10
REM   .\download_publicvpnlist.bat US,JP 5

set "COUNTRY=all"
set "MAXN=10"

if not "%~1"=="" set "COUNTRY=%~1"
if not "%~2"=="" set "MAXN=%~2"

echo === download_publicvpnlist ===
echo country=%COUNTRY% max=%MAXN%
echo out=%~dp0ovpn-list
echo (existing files kept; no delete)
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [!] python not found in PATH
  exit /b 1
)

python "%~dp0download_publicvpnlist.py" --country "%COUNTRY%" --max %MAXN% --out "%~dp0ovpn-list"
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo [!] download failed code=%ERR%
  exit /b %ERR%
)

echo.
echo Done. Start stack with local list priority:
echo   .\autogate.bat ovpn
exit /b 0