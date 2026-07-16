@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "RUN_KEEPALIVE=1"

REM PowerShell: use .\autogate.bat  (not bare autogate.bat)
for %%A in (%*) do (
  if /I "%%~A"=="stop" set "RUN_KEEPALIVE=0"
  if /I "%%~A"=="status" set "RUN_KEEPALIVE=0"
  if /I "%%~A"=="map" set "RUN_KEEPALIVE=0"
  if /I "%%~A"=="logs" set "RUN_KEEPALIVE=0"
  if /I "%%~A"=="help" set "RUN_KEEPALIVE=0"
  if /I "%%~A"=="-h" set "RUN_KEEPALIVE=0"
  if /I "%%~A"=="--help" set "RUN_KEEPALIVE=0"
)

set "WSL_DIR="
for /f "usebackq delims=" %%I in (`wsl -d Ubuntu-24.04 -u root -- wslpath -a "%~dp0." 2^>nul`) do set "WSL_DIR=%%I"
if not defined WSL_DIR (
  echo [!] Khong lay duoc WSL path. Kiem tra: wsl -d Ubuntu-24.04 -u root -- echo ok
  goto after_action
)

echo ============================================
echo   AutoGate Manager  (WSL2 - Ubuntu-24.04)
echo ============================================
echo.
echo Workdir WSL: %WSL_DIR%
echo Args: %*
echo.

wsl -d Ubuntu-24.04 -u root -- env AUTOGATE_DIR="%WSL_DIR%" bash "%WSL_DIR%/autogate.sh" %*
if errorlevel 1 goto after_action

if "%RUN_KEEPALIVE%"=="1" (
  call :keepalive
  goto end
)
goto end

:after_action
echo.
echo --------------------------------------------
echo  PowerShell:  .\autogate.bat ovpn
echo  Cmd:         autogate.bat ovpn
echo.
echo  Vi du:
echo    .\autogate.bat
echo    .\autogate.bat ovpn
echo    .\autogate.bat US,JP 10 ovpn
echo    .\autogate.bat restart KR 5 all
echo    .\autogate.bat stop
echo    .\autogate.bat status
echo    .\autogate.bat map
echo    .\autogate.bat logs haproxy
echo.
echo  EGRESS_MODE: all / ovpn / ovpn+psiphon / ovpn+warp / custom
echo  Chi OpenVPN: them arg ovpn
echo  map: port worker -^> file .ovpn local -^> remote VPN
echo.
echo  Proxy xoay vong : http://localhost:56789
echo  Proxy list UI   : http://localhost:2087  (co bang OVPN map)
echo  Worker proxies  : http://127.0.0.1:56800 ...
echo --------------------------------------------
pause
goto end

:keepalive
echo.
echo AutoGate dang chay. Giu cua so nay mo de WSL/Docker khong tu tat.
echo Nhan Ctrl+C hoac dong cua so khi muon ngat keepalive.
:keepalive_loop
ping -n 3 127.0.0.1 >nul
wsl -d Ubuntu-24.04 -u root -- true >nul 2>nul
goto keepalive_loop

:end
endlocal
exit /b 0
