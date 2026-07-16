@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

REM Download LIVE PublicVPNList .ovpn into .\ovpn-list
REM Default: TCP live/die precheck ON, never deletes folder
REM Usage:
REM   .\download_publicvpnlist.bat
REM   .\download_publicvpnlist.bat JP 100
REM   .\download_publicvpnlist.bat all 50

set "COUNTRY=all"
set "MAXN=100"
if not "%~1"=="" set "COUNTRY=%~1"
if not "%~2"=="" set "MAXN=%~2"

echo === download_publicvpnlist ===
echo country=%COUNTRY% max=%MAXN%
echo precheck=ON (TCP live/die first)
echo out=%~dp0ovpn-list
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [!] python not found in PATH
  exit /b 1
)

python "%~dp0download_publicvpnlist.py" --country "%COUNTRY%" --max %MAXN% --out "%~dp0ovpn-list" --precheck
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
  echo [!] download failed code=%ERR%
  exit /b %ERR%
)
echo.
echo Done: .\autogate.bat ovpn
exit /b 0